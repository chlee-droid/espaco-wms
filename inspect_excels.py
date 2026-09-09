"""받아온 엑셀들의 구조를 로그에 찍는다

수집이 잘 됐는지, 열 이름이 우리가 기대한 것과 맞는지 확인하는 용도.
BigQuery 없이 돌아간다.

발주조회에는 받는분 이름·전화번호·주소 같은 개인정보가 있어서,
그 파일은 열 이름과 건수만 찍고 값은 가린다.
"""
import glob
import openpyxl

# process_and_upload.py 가 찾는 열 후보와 같은 목록
LOT_EXPECT = {
    "상품코드": ["상품코드", "고유코드", "품목코드"],
    "상품명": ["출고상품명", "상품명", "판매상품명", "품목명"],
    "구분": ["구분"],
    "로케이션": ["로케이션 구분명", "로케이션구분명", "로케이션 구분", "재고상태"],
    "유통기한": ["유통기한/제조일자", "유통기한", "유효기간", "소비기한", "만료일"],
    "수량": ["수량", "재고수량", "총재고"],
}
ADDR_EXPECT = {
    "주소": ["주소", "수취인주소", "수령인주소", "배송지주소", "배송주소", "받는분 주소", "받는분주소"],
    "상세주소": ["상세주소", "주소상세", "나머지주소"],
    "전화번호": ["전화번호1", "전화번호"],
    "받는분": ["받는분 이름", "받는분이름", "수취인명"],
}

FILES = [
    ("stock_report_*.xlsx", "재고조회(기본)", None),
    ("stock_lot_report_*.xlsx", "재고조회(유통기한)", LOT_EXPECT),
    ("inout_report_*.xlsx", "입출고내역", None),
    ("order_report_*.xlsx", "발주조회", ADDR_EXPECT),
]

# 개인정보가 있어 값을 찍지 않을 파일
SECRET_FILES = {"발주조회"}


def mask(v):
    s = str(v)
    if len(s) <= 4:
        return s[:1] + "*" * (len(s) - 1)
    return s[:4] + "*" * min(len(s) - 4, 8)


def report(pattern, label, expect):
    print("\n" + "=" * 70)
    print(label)
    print("=" * 70)

    found = sorted(glob.glob(pattern))
    if not found:
        print("  파일 없음 - 다운로드가 실패했거나 건너뛴 것입니다")
        return False

    path = found[-1]
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        print(f"  {path} - 빈 파일")
        return False

    headers = [str(h).strip() if h is not None else "" for h in rows[0]]
    body = [r for r in rows[1:] if any(v is not None and str(v).strip() != "" for v in r)]

    print(f"  파일: {path}")
    print(f"  {len(body)}줄 / 열 {len(headers)}개")
    print("  열 이름:")
    for i, hh in enumerate(headers):
        print(f"    [{i}] {hh}")

    if label in SECRET_FILES:
        print("  (개인정보가 있어 값은 가립니다)")
        if body:
            print("    " + " | ".join(mask(v) if v is not None else "" for v in body[0]))
    else:
        print("  샘플 2줄:")
        for r in body[:2]:
            print("    " + " | ".join("" if v is None else str(v) for v in r))

    # 우리가 찾는 열이 실제로 있는지 확인
    if expect:
        print("  열 찾기 결과:")
        for want, candidates in expect.items():
            hit = next((c for c in candidates if c in headers), None)
            if hit:
                print(f"    O {want:8s} -> '{hit}'")
            else:
                print(f"    X {want:8s} -> 못 찾음. 후보: {candidates}")
                print(f"      >> 위 열 이름 목록에서 맞는 것을 찾아 알려 주세요")
    return True


def run():
    ok, missing = [], []
    for pattern, label, expect in FILES:
        if report(pattern, label, expect):
            ok.append(label)
        else:
            missing.append(label)

    print("\n" + "=" * 70)
    print(f"받은 것 {len(ok)}개: {', '.join(ok) if ok else '없음'}")
    if missing:
        print(f"못 받은 것 {len(missing)}개: {', '.join(missing)}")
    print("=" * 70)


if __name__ == "__main__":
    run()
