-- 에스파코 물류 대시보드 - BigQuery 테이블 만들기
--
-- 새 GCP 프로젝트 espaco-wms-data 를 만든 뒤, BigQuery 콘솔에서 이 SQL을 그대로 실행하세요.
-- 데이터셋 이름은 wms_data 입니다. (Apps Script 의 BQ_DATASET 값과 같아야 합니다)
--
-- 먼저 데이터셋을 만듭니다:
--   bq --location=asia-northeast3 mk --dataset espaco-wms-data:wms_data

-- ── 재고 스냅샷 (하루 한 세트, 그날 파티션을 통째로 교체) ─────────────
CREATE TABLE IF NOT EXISTS `espaco-wms-data.wms_data.inventory_history`
(
  history_date          DATE,
  product_code          STRING,
  release_product_name  STRING,
  simple_product_name   STRING,
  management_keyword_1  STRING,
  total_inventory       INT64,
  available_for_release INT64
)
PARTITION BY history_date;

-- ── 유효기간별 재고 (재고 > 재고조회(유통기한) 화면) ──────────────
-- 엑셀 한 줄이 한 줄입니다. 한 상품이 유통기한별로, 또 출고가능/불량으로 나뉘어
-- 여러 줄이 될 수 있습니다. 유통기한이 없는 재고도 그대로 들어갑니다.
CREATE TABLE IF NOT EXISTS `espaco-wms-data.wms_data.inventory_lot`
(
  history_date    DATE,
  product_code    STRING,
  product_name    STRING,
  item_type       STRING,   -- 구분: 일반 / 부자재
  barcode         STRING,
  location_type   STRING,   -- 로케이션 구분명: 출고가능 / 불량
  expiration_date STRING,   -- 'YYYY-MM-DD', 유통기한 없는 재고는 ''
  quantity        INT64
)
PARTITION BY history_date;

-- ── 입출고 로그 (날짜별 파티션 교체) ──────────────────────────────
CREATE TABLE IF NOT EXISTS `espaco-wms-data.wms_data.inout_log`
(
  inout_day           DATE,
  inout_date          STRING,
  product_code        STRING,
  product_name        STRING,
  simple_product_name STRING,
  move_type           STRING,
  quantity            INT64,
  expiration_date     STRING,
  memo                STRING
)
PARTITION BY inout_day;

-- ── 발주 로그 (일일정산에서 마감할 때 쌓임) ────────────────────────
-- shipping_address 는 등록된 거래처 건만 채워집니다.
-- 거래처명이 '온라인'인 일반 주문은 주소를 남기지 않습니다.
CREATE TABLE IF NOT EXISTS `espaco-wms-data.wms_data.order_logs`
(
  order_code          STRING,
  order_date          STRING,   -- 'YYYY-MM-DD HH:MM:SS'
  customer_group      STRING,
  customer_name       STRING,
  receiver_name       STRING,
  phone_number        STRING,
  product_code        STRING,
  product_name        STRING,
  simple_product_name STRING,
  quantity            INT64,
  status              STRING,
  shipping_address    STRING
);

-- ── 수집 시각 기록 ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `espaco-wms-data.wms_data.collect_log`
(
  collected_at TIMESTAMP,
  type         STRING    -- 'stock', 'stock_lot'
);
