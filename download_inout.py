import os
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright

COMPANY_CODE = os.environ["SB_COMPANY_CODE"]
USER_ID = os.environ["SB_USER_ID"]
PASSWORD = os.environ["SB_PASSWORD"]


def login(page):
    page.goto("https://wms02.sbfulfillment.co.kr/login")
    page.wait_for_load_state("networkidle")
    inputs = page.locator("input:visible")
    inputs.nth(0).fill(COMPANY_CODE)
    inputs.nth(1).fill(USER_ID)
    inputs.nth(2).fill(PASSWORD)
    page.get_by_role("button", name="로그인").click()
    page.wait_for_timeout(4000)


def download_inout_report(page, start_date=None, end_date=None):
    # 기본값: 어제 ~ 오늘
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")

    # 좌측 메뉴 "재고" -> "입출고내역조회"
    page.get_by_text("재고", exact=True).first.click()
    page.wait_for_timeout(800)
    page.get_by_text("입출고내역조회", exact=True).click()
    page.wait_for_timeout(2000)

    # 조회기간 입력
    date_fields = page.locator(".flatpickr-input")
    date_fields.nth(0).fill(start_date)
    date_fields.nth(1).fill(end_date)
    # 달력 팝업 닫기 (빈 공간 클릭)
    page.mouse.click(1700, 400)
    page.wait_for_timeout(500)

    # 검색 버튼 클릭 (bg-primary + 돋보기 아이콘)
    page.locator("button.bg-primary:has(i.fi-ico-search)").first.click()
    page.wait_for_timeout(2500)
    page.screenshot(path="inout_1_search_result.png", full_page=True)

    # 검색 결과가 0건이면 다운로드할 게 없으므로 조용히 종료
    body_text = page.locator("body").inner_text()
    if ("데이터가 없습니다" in body_text) or ("조회된 데이터가 없" in body_text) or ("검색 결과가 없" in body_text):
        print("입출고 데이터 0건 - 다운로드 건너뜀")
        return None

    # "엑셀받기" 클릭 -> 팝업 없이 바로 다운로드
    try:
        with page.expect_download(timeout=30000) as download_info:
            page.get_by_role("button", name="엑셀받기", exact=True).click()
        download = download_info.value
    except Exception:
        print("입출고 다운로드가 시작되지 않음 (0건으로 추정) - 건너뜀")
        return None

    filename = f"inout_report_{start_date}_to_{end_date}.xlsx"
    download.save_as(filename)

    print("다운로드 완료:", filename)
    return filename


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        login(page)
        download_inout_report(page)
        browser.close()


if __name__ == "__main__":
    run()
