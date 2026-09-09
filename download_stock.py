import os
from datetime import datetime
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
    # 로그인 후 메인 화면이 로드될 때까지 대기 (고정 대기 대신 네트워크 안정화)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)


def download_stock_report(page):
    # 좌측 메뉴 "재고" -> "재고조회(기본)" 클릭
    page.get_by_text("재고", exact=True).first.click()
    page.wait_for_timeout(800)
    page.get_by_text("재고조회(기본)", exact=True).click()
    # 재고조회 화면이 완전히 뜰 때까지 대기
    page.wait_for_load_state("networkidle")

    # 돋보기(검색) 버튼이 나타날 때까지 명시적으로 대기 (최대 60초)
    search_btn = page.locator("button:has(i.fi-ico-search)").first
    search_btn.wait_for(state="visible", timeout=60000)
    search_btn.click()

    # 조회 결과가 로드될 때까지 대기
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1500)
    page.screenshot(path="stock_1_search_result.png", full_page=True)

    # "엑셀받기" 버튼 클릭
    excel_btn = page.locator("button:has-text('엑셀받기')").first
    excel_btn.wait_for(state="visible", timeout=30000)
    excel_btn.click()
    page.wait_for_timeout(1000)

    # 팝업에서 "전체선택" 체크박스 클릭
    select_all = page.locator("input[aria-label='전체선택']")
    select_all.wait_for(state="visible", timeout=15000)
    select_all.click(force=True)
    page.wait_for_timeout(500)
    page.screenshot(path="stock_2_excel_popup.png", full_page=True)

    # "받기" 버튼 클릭 -> 다운로드 발생
    with page.expect_download(timeout=60000) as download_info:
        page.get_by_role("button", name="받기", exact=True).click()
    download = download_info.value

    today = datetime.now().strftime("%Y%m%d")
    filename = f"stock_report_{today}.xlsx"
    download.save_as(filename)
    print("다운로드 완료:", filename)
    return filename


def run():
    last_error = None
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # 최대 3회 재시도
        for attempt in range(1, 4):
            page = browser.new_page(viewport={"width": 1920, "height": 1080})
            try:
                print(f"[시도 {attempt}/3] 재고 수집 시작")
                login(page)
                download_stock_report(page)
                page.close()
                browser.close()
                print(f"[시도 {attempt}/3] 성공")
                return
            except Exception as e:
                last_error = e
                print(f"[시도 {attempt}/3] 실패: {e}")
                # 실패 시 디버깅용 스크린샷
                try:
                    page.screenshot(path=f"stock_error_attempt{attempt}.png", full_page=True)
                except Exception:
                    pass
                page.close()
                if attempt < 3:
                    print("5초 후 재시도...")
                    import time
                    time.sleep(5)
        browser.close()
    # 3회 모두 실패하면 에러 발생시켜 워크플로우가 실패로 기록되게
    raise last_error


if __name__ == "__main__":
    run()
