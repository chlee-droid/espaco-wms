import os
import json
from datetime import datetime, timedelta, timezone
import openpyxl
import requests
from google.cloud import bigquery

WEBHOOK_URL = os.environ["SHEET_WEBHOOK_URL"]
WEBHOOK_SECRET = os.environ["SHEET_WEBHOOK_SECRET"]

GCP_PROJECT_ID = "adp-wms-data"
BQ_DATASET = "wms_data"

# 한국 표준시 (GitHub Actions 서버는 UTC라서 명시적으로 KST를 써야 함)
KST = timezone(timedelta(hours=9))

# GitHub Actions가 Workload Identity Federation(OIDC)으로 이미 인증되어 있으므로
# 별도 키 파일 없이 Application Default Credentials로 BigQuery에 접근합니다.
bq_client = bigquery.Client(project=GCP_PROJECT_ID)


def now_kst():
    return datetime.now(KST)


def safe_int(value, default=0):
    """엑셀 숫자가 '1,055'처럼 콤마 포함 텍스트로 올 때도 안전하게 정수 변환"""
    if value is None or value == "":
        return default
    if isinstance(value, (int, float)):
        return int(value)
    try:
        cleaned = str(value).replace(",", "").strip()
        return int(float(cleaned)) if cleaned else default
    except (ValueError, TypeError):
        return default


def read_excel_as_dicts(filepath):
    wb = openpyxl.load_workbook(filepath, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    headers = [str(h).strip() if h is not None else "" for h in rows[0]]
    result = []
    for row in rows[1:]:
        if all(v is None or str(v).strip() == "" for v in row):
            continue
        item = dict(zip(headers, row))
        result.append(item)
    return result


def send_to_sheet(payload_type, headers, rows, extra=None):
    """구글 시트 웹훅으로 전송 (사람이 손대야 하는 발주 로그만 여기로 옴)"""
    payload = {
        "secret": WEBHOOK_SECRET,
        "type": payload_type,
        "headers": headers,
        "rows": rows,
    }
    if extra:
        payload.update(extra)

    body = json.dumps(payload)

    last_err = None
    for attempt in range(1, 4):  # 최대 3회 시도
        try:
            resp = requests.post(WEBHOOK_URL, data=body, timeout=180)
            try:
                result = resp.json()
            except Exception:
                print(f"[{payload_type}] 응답이 JSON이 아님! status_code={resp.status_code}")
                print(f"[{payload_type}] 응답 내용 (앞 1000자): {resp.text[:1000]}")
                raise Exception(f"시트 전송 실패 ({payload_type}): JSON 응답이 아님, 위 로그 참고")

            if not result.get("ok"):
                raise Exception(f"시트 전송 실패 ({payload_type}): {result.get('error')}")
            print(f"[{payload_type}] {result.get('count')}건 전송 완료")
            return
        except requests.exceptions.Timeout as e:
            last_err = e
            print(f"[{payload_type}] 응답 지연으로 타임아웃 (시도 {attempt}/3) - 재시도")
        except requests.exceptions.RequestException as e:
            last_err = e
            print(f"[{payload_type}] 통신 오류 (시도 {attempt}/3): {e} - 재시도")

    raise Exception(f"시트 전송 실패 ({payload_type}): {last_err}")


def send_to_bigquery(table_name, rows_json):
    """빅쿼리에 로그 데이터를 스트리밍으로 누적 저장 (입출고 로그용 - 계속 쌓임)"""
    if not rows_json:
        print(f"[BigQuery] {table_name} - 전송할 데이터 없음, 건너뜀")
        return

    table_id = f"{GCP_PROJECT_ID}.{BQ_DATASET}.{table_name}"
    errors = bq_client.insert_rows_json(table_id, rows_json)
    if errors == []:
        print(f"[BigQuery] {table_name}에 {len(rows_json)}건 누적 저장 완료")
    else:
        print(f"[BigQuery] 에러 발생: {errors}")
        raise Exception(f"빅쿼리 전송 실패: {table_name}")


def log_collection(collect_type):
    """수집 완료 시각을 collect_log 테이블에 기록"""
    table_id = f"{GCP_PROJECT_ID}.{BQ_DATASET}.collect_log"
    row = [{
        "collected_at": now_kst().isoformat(),  # KST 시각 (오프셋 포함)
        "type": collect_type,
    }]
    try:
        errors = bq_client.insert_rows_json(table_id, row)
        if errors == []:
            print(f"[BigQuery] collect_log 기록 완료 ({collect_type})")
        else:
            print(f"[BigQuery] collect_log 기록 오류: {errors}")
    except Exception as e:
        # 로그 기록 실패가 전체 수집을 막지 않도록 예외를 삼킴
        print(f"[BigQuery] collect_log 기록 실패(무시): {e}")


def replace_stock_for_today(rows_json, today):
    """
    재고는 '날짜별 최종 스냅샷 1세트'만 유지한다.
    하루 여러 번 수집돼도 그날 파티션을 통째로 최신 것으로 교체.

    - inventory_history 는 history_date 기준 '일별 파티션 테이블'이어야 함.
    - 오늘 날짜 파티션($YYYYMMDD)에 WRITE_TRUNCATE 로 로드하면,
      그 파티션만 통째로 교체됨. DELETE 를 안 쓰므로 스트리밍 버퍼 제약이 없음.
    """
    if not rows_json:
        print("[BigQuery] inventory_history - 삽입할 재고 데이터 없음, 건너뜀")
        return

    # 파티션 데코레이터: 테이블명$YYYYMMDD (오늘 파티션만 지정)
    partition_id = today.replace("-", "")  # '2026-07-19' -> '20260719'
    table_ref = f"{GCP_PROJECT_ID}.{BQ_DATASET}.inventory_history${partition_id}"

    schema = [
        bigquery.SchemaField("history_date", "DATE"),
        bigquery.SchemaField("product_code", "STRING"),
        bigquery.SchemaField("release_product_name", "STRING"),
        bigquery.SchemaField("simple_product_name", "STRING"),
        bigquery.SchemaField("management_keyword_1", "STRING"),
        bigquery.SchemaField("total_inventory", "INTEGER"),
        bigquery.SchemaField("available_for_release", "INTEGER"),
    ]
    job_config = bigquery.LoadJobConfig(
        schema=schema,
        write_disposition="WRITE_TRUNCATE",  # 오늘 파티션만 통째 교체
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        time_partitioning=bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="history_date",
        ),
    )
    load_job = bq_client.load_table_from_json(rows_json, table_ref, job_config=job_config)
    load_job.result()  # 완료 대기
    print(f"[BigQuery] inventory_history - {today} 파티션을 {len(rows_json)}건으로 교체 완료")


def process_stock(filepath):
    """재고 히스토리 -> BigQuery(inventory_history). 날짜별 최종 스냅샷 1세트만 유지(그날 것 교체)."""
    items = read_excel_as_dicts(filepath)
    today = now_kst().strftime("%Y-%m-%d")

    rows_bq = []
    for it in items:
        rows_bq.append({
            "history_date": today,
            "product_code": str(it.get("상품코드", "") or ""),
            "release_product_name": str(it.get("출고상품명", "") or ""),
            "simple_product_name": "",
            "management_keyword_1": str(it.get("관리키워드1", "") or ""),
            "total_inventory": safe_int(it.get("총재고", 0)),
            "available_for_release": safe_int(it.get("출고가능", 0)),
        })
    replace_stock_for_today(rows_bq, today)
    log_collection('stock')



# ===== 유효기간별 재고 =====
# 재고 > 재고조회(유통기한) 엑셀의 실제 열
#   회사명 | 상품코드 | 공급사 | 출고상품명 | 구분 | 바코드 | 로케이션 구분명 | 유통기한/제조일자 | 수량
# 로케이션 구분명은 '출고가능' 또는 '불량'. 유통기한은 없는 줄이 꽤 있다.
LOT_COLS = {
    "product_code": ["상품코드", "고유코드", "품목코드"],
    "product_name": ["출고상품명", "상품명", "판매상품명", "품목명"],
    "item_type": ["구분"],
    "barcode": ["바코드"],
    "location_type": ["로케이션 구분명", "로케이션구분명", "로케이션 구분", "재고상태"],
    "expiration": ["유통기한/제조일자", "유통기한", "유효기간", "소비기한", "만료일"],
    "quantity": ["수량", "재고수량", "총재고"],
}

# 출고할 수 있는 상태를 가리키는 값 (이 외는 불량으로 본다)
LOT_AVAILABLE = "출고가능"


def pick(item, keys, default=""):
    """후보 열 이름 중 실제로 있는 것의 값을 돌려준다"""
    for k in keys:
        if k in item and item[k] is not None and str(item[k]).strip() != "":
            return item[k]
    return default


def normalize_date(value):
    """'2027-03-01', '2027/03/01', '20270301', 날짜셀 → 'YYYY-MM-DD' (못 읽으면 빈 문자열)"""
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    s = str(value).strip()
    if not s:
        return ""
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) >= 8:
        y, m, d = digits[0:4], digits[4:6], digits[6:8]
        try:
            datetime(int(y), int(m), int(d))
            return f"{y}-{m}-{d}"
        except ValueError:
            return ""
    return ""


def replace_lot_for_today(rows_json, today):
    """유효기간별 재고도 날짜별 최종 스냅샷 1세트만 유지 (그날 파티션 교체)

    하루 두 번 돌아도 그날 파티션이 최신 것으로 갈릴 뿐 쌓이지 않는다.
    """
    if not rows_json:
        print("[BigQuery] inventory_lot - 삽입할 데이터 없음, 건너뜀")
        return

    partition_id = today.replace("-", "")
    table_ref = f"{GCP_PROJECT_ID}.{BQ_DATASET}.inventory_lot${partition_id}"

    schema = [
        bigquery.SchemaField("history_date", "DATE"),
        bigquery.SchemaField("product_code", "STRING"),
        bigquery.SchemaField("product_name", "STRING"),
        bigquery.SchemaField("item_type", "STRING"),
        bigquery.SchemaField("barcode", "STRING"),
        bigquery.SchemaField("location_type", "STRING"),
        bigquery.SchemaField("expiration_date", "STRING"),
        bigquery.SchemaField("quantity", "INTEGER"),
    ]
    job_config = bigquery.LoadJobConfig(
        schema=schema,
        write_disposition="WRITE_TRUNCATE",
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        time_partitioning=bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="history_date",
        ),
    )
    load_job = bq_client.load_table_from_json(rows_json, table_ref, job_config=job_config)
    load_job.result()
    print(f"[BigQuery] inventory_lot - {today} 파티션을 {len(rows_json)}건으로 교체 완료")


def process_stock_lot(filepath):
    """유효기간별 재고 -> BigQuery(inventory_lot)

    엑셀 한 줄이 그대로 한 줄로 들어간다.
    상품 하나가 유통기한별로, 또 출고가능/불량으로 나뉘어 여러 줄이 될 수 있다.
    유통기한이 없는 재고는 expiration_date 를 빈 문자열로 둔다.
    """
    items = read_excel_as_dicts(filepath)
    today = now_kst().strftime("%Y-%m-%d")

    if items:
        print("[유효기간별 재고] 엑셀 열:", list(items[0].keys()))

    rows_bq = []
    for it in items:
        code = str(pick(it, LOT_COLS["product_code"]) or "")
        if not code:
            continue
        rows_bq.append({
            "history_date": today,
            "product_code": code,
            "product_name": str(pick(it, LOT_COLS["product_name"]) or ""),
            "item_type": str(pick(it, LOT_COLS["item_type"]) or ""),
            "barcode": str(pick(it, LOT_COLS["barcode"]) or ""),
            "location_type": str(pick(it, LOT_COLS["location_type"]) or ""),
            "expiration_date": normalize_date(pick(it, LOT_COLS["expiration"])),
            "quantity": safe_int(pick(it, LOT_COLS["quantity"], 0)),
        })

    with_exp = sum(1 for r in rows_bq if r["expiration_date"])
    avail = sum(r["quantity"] for r in rows_bq if r["location_type"] == LOT_AVAILABLE)
    defect = sum(r["quantity"] for r in rows_bq if r["location_type"] != LOT_AVAILABLE)
    codes = len({r["product_code"] for r in rows_bq})
    print(f"[유효기간별 재고] {len(rows_bq)}줄 / 상품 {codes}종")
    print(f"[유효기간별 재고] 유통기한 있는 줄 {with_exp}개, 없는 줄 {len(rows_bq) - with_exp}개")
    print(f"[유효기간별 재고] 출고가능 {avail}개, 그 외(불량 등) {defect}개")

    replace_lot_for_today(rows_bq, today)
    log_collection("stock_lot")


def replace_inout_by_day(rows_json):
    """
    입출고는 '날짜별 파티션 교체' 방식.
    수집해온 데이터에 포함된 각 날짜(inout_day)에 대해, 그 날짜 파티션을
    통째로 최신 데이터로 교체(WRITE_TRUNCATE). 여러 번 수집해도 중복 안 쌓임.
    """
    if not rows_json:
        print("[BigQuery] inout_log - 전송할 데이터 없음, 건너뜀")
        return

    # 수집 데이터에 들어있는 날짜 목록 추출
    days = sorted(set(r["inout_day"] for r in rows_json if r.get("inout_day")))

    schema = [
        bigquery.SchemaField("inout_day", "DATE"),
        bigquery.SchemaField("inout_date", "STRING"),
        bigquery.SchemaField("product_code", "STRING"),
        bigquery.SchemaField("product_name", "STRING"),
        bigquery.SchemaField("simple_product_name", "STRING"),
        bigquery.SchemaField("move_type", "STRING"),
        bigquery.SchemaField("quantity", "INTEGER"),
        bigquery.SchemaField("expiration_date", "STRING"),
        bigquery.SchemaField("memo", "STRING"),
    ]

    # 날짜별로 그 파티션만 교체
    for day in days:
        day_rows = [r for r in rows_json if r.get("inout_day") == day]
        partition_id = day.replace("-", "")  # '2026-07-20' -> '20260720'
        table_ref = f"{GCP_PROJECT_ID}.{BQ_DATASET}.inout_log${partition_id}"
        job_config = bigquery.LoadJobConfig(
            schema=schema,
            write_disposition="WRITE_TRUNCATE",
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            time_partitioning=bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY,
                field="inout_day",
            ),
        )
        load_job = bq_client.load_table_from_json(day_rows, table_ref, job_config=job_config)
        load_job.result()
        print(f"[BigQuery] inout_log - {day} 파티션을 {len(day_rows)}건으로 교체 완료")


def process_inout(filepath):
    """입출고 로그 -> BigQuery(inout_log). 날짜별 파티션 교체(중복 방지)."""
    items = read_excel_as_dicts(filepath)

    rows_bq = []
    for it in items:
        raw_date = str(it.get("날짜", "") or "")
        inout_day = raw_date[:10] if len(raw_date) >= 10 else None  # 'YYYY-MM-DD'
        rows_bq.append({
            "inout_day": inout_day,
            "inout_date": raw_date,
            "product_code": str(it.get("상품코드", "") or ""),
            "product_name": str(it.get("상품명", "") or ""),
            "simple_product_name": "",
            "move_type": str(it.get("이동 구분", it.get("이동구분", "")) or ""),
            "quantity": safe_int(it.get("수량", 0)),
            "expiration_date": str(it.get("유통기한", "") or ""),
            "memo": str(it.get("메모", "") or ""),
        })
    replace_inout_by_day(rows_bq)


# 발주 엑셀의 주소 열 이름 후보 (앞에서부터 찾는다)
ADDR_COLS = ["주소", "수취인주소", "수령인주소", "배송지주소", "배송주소", "받는분 주소", "받는분주소"]
ADDR_DETAIL_COLS = ["상세주소", "주소상세", "나머지주소"]


def build_address(item):
    """기본주소 + 상세주소를 합쳐 하나의 출고주소로"""
    base = str(pick(item, ADDR_COLS) or "").strip()
    detail = str(pick(item, ADDR_DETAIL_COLS) or "").strip()
    if base and detail and detail not in base:
        return f"{base} {detail}"
    return base or detail


def process_order(filepath):
    """발주 로그 -> 새 스프레드시트의 미처리_발주_대기열 탭으로 전송 (사람이 거래처 입력 필요)"""
    items = read_excel_as_dicts(filepath)
    if items:
        print("[발주조회] 엑셀 열:", list(items[0].keys()))
    headers = [
        "오더코드", "발주일자", "거래처그룹", "거래처명", "받는분 이름",
        "전화번호", "고유코드", "판매상품명", "간단상품명", "수량", "진행상태", "주소",
    ]
    rows = []
    for it in items:
        rows.append([
            it.get("오더코드", ""),
            str(it.get("발주일자", "") or ""),
            "",  # 거래처그룹 - 전화번호로 자동 매칭, 없으면 온라인
            "",  # 거래처명 - 전화번호로 자동 매칭, 없으면 온라인
            it.get("받는분 이름", ""),
            it.get("전화번호1", it.get("전화번호", "")),
            it.get("고유코드", ""),
            it.get("판매 상품명", it.get("판매상품명", "")),
            "",
            it.get("수량", 0),
            it.get("진행상태", ""),
            build_address(it),
        ])
    send_to_sheet("order_log", headers, rows)


def run():
    import glob

    stock_files = sorted(glob.glob("stock_report_*.xlsx"))
    lot_files = sorted(glob.glob("stock_lot_report_*.xlsx"))
    inout_files = sorted(glob.glob("inout_report_*.xlsx"))
    order_files = sorted(glob.glob("order_report_*.xlsx"))

    if stock_files:
        process_stock(stock_files[-1])
    else:
        print("재고조회 파일 없음 - 건너뜀")

    if lot_files:
        process_stock_lot(lot_files[-1])
    else:
        print("유효기간별 재고 파일 없음 - 건너뜀")

    if inout_files:
        process_inout(inout_files[-1])
    else:
        print("입출고내역 파일 없음 - 건너뜀")

    if order_files:
        process_order(order_files[-1])
    else:
        print("발주조회 파일 없음 - 건너뜀")


if __name__ == "__main__":
    run()
