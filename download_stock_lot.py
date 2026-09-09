"""유효기간별 재고 다운로드 (재고 > 재고조회(유통기한))

재고조회(기본)은 상품코드 단위 합계만 준다. 유효기간을 나눠 보려면 이 화면을 따로 받아야 한다.

화면 흐름
  로그인 → 좌측 '재고' → '재고조회(유통기한)' → 돋보기(조회)
  → '엑셀받기' → 팝업에서 '받기'

엑셀받기 팝업이 재고조회(기본)과 다르다.
기본 화면은 열을 고르는 '전체선택' 체크박스가 있지만, 이 화면은
[다운로드 범위 선택] 라디오(전체 / 현재 페이지 / 선택 항목)와
[다운로드 서식 선택] 드롭다운만 있다. 둘 다 기본값이 우리가 원하는 값이라
건드리지 않고 '받기'만 누른다.
"""
import os
from datetime import datetime
from playwright.sync_api import sync_playwright

COMPANY_CODE = os.environ["SB_COMPANY_CODE"]
USER_ID = os.environ["SB_USER_ID"]
PASSWORD = os.environ["SB_PASSWORD"]

MENU_NAME = "재고조회(유통기한)"


def login(page):
    page.goto("https://wms02.sbfulfillment.co.kr/login")
    page.wait_for_load_state("networkidle")
    inputs = page.locator("input:visible")
    inputs.nth(0).fill(COMPANY_CODE)
    inputs.nth(1).fill(USER_ID)
    inputs.nth(2).fill(PASSWORD)
    page.get_by_role("button", name="로그인").click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)


def open_menu(page):
    """좌측 '재고'를 펼치고 '재고조회(유통기한)'을 연다"""
    target = page.get_by_text(MENU_NAME, exact=True)

    # 재고 메뉴가 접혀 있으면 펼친다. 이미 펼쳐져 있으면 누르지 않는다
    # (누르면 도로 접히기 때문)
    if target.count() == 0:
        page.get_by_text("재고", exact=True).first.click()
        page.wait_for_timeout(1000)
        target = page.get_by_text(MENU_NAME, exact=True)

    if target.count() == 0:
        page.screenshot(path="stocklot_menu_notfound.png", full_page=True)
        try:
            texts = page.locator("a:visible, li:visible").all_inner_texts()
            seen, uniq = set(), []
            for t in texts:
                t = t.strip()
                if t and t not in seen and len(t) < 40:
                    seen.add(t)
                    uniq.append(t)
            print("보이는 메뉴 목록:", uniq[:80])
        except Exception:
            pass
        raise Exception(f"'{MENU_NAME}' 메뉴를 못 찾았습니다. 스크린샷과 위 목록을 확인해 주세요.")

    target.first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1200)


def click_receive_button(page):
    """팝업의 '받기' 버튼을 누른다

    '엑셀받기'에도 '받기'가 들어 있어서 부분 일치로 찾으면 잘못 누른다.
    글자가 정확히 '받기'인 버튼만 고른다. (앞의 체크 표시는 아이콘이라 글자에 안 잡힘)
    """
    buttons = page.locator("button:visible")
    for i in range(buttons.count()):
        btn = buttons.nth(i)
        try:
            text = btn.inner_text().strip()
        except Exception:
            continue
        if text.replace("✓", "").strip() == "받기":
            return btn
    raise Exception("팝업에서 '받기' 버튼을 못 찾았습니다.")


def download_report(page):
    open_menu(page)

    # 돋보기(조회)
    search_btn = page.locator("button:has(i.fi-ico-search)").first
    search_btn.wait_for(state="visible", timeout=60000)
    search_btn.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)
    page.screenshot(path="stocklot_1_search_result.png", full_page=True)

    # 조회된 건수를 로그에 남긴다 (0건이면 뭔가 잘못된 것)
    try:
        body = page.locator("body").inner_text()
        for ln in body.split("\n"):
            if "총" in ln and "상품 검색" in ln:
                print("조회 결과:", ln.strip())
                break
    except Exception:
        pass

    # 엑셀받기
    excel_btn = page.locator("button:has-text('엑셀받기')").first
    excel_btn.wait_for(state="visible", timeout=30000)
    excel_btn.click()
    page.wait_for_timeout(1500)
    page.screenshot(path="stocklot_2_excel_popup.png", full_page=True)

    # 팝업의 기본값이 [범위: 전체] + [서식: 기본서식] 이라 그대로 받는다
    with page.expect_download(timeout=120000) as download_info:
        click_receive_button(page).click()
    download = download_info.value

    today = datetime.now().strftime("%Y%m%d")
    filename = f"stock_lot_report_{today}.xlsx"
    download.save_as(filename)
    print("다운로드 완료:", filename)
    return filename


def run():
    last_error = None
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for attempt in range(1, 4):
            page = browser.new_page(viewport={"width": 1920, "height": 1080})
            try:
                print(f"[시도 {attempt}/3] 유효기간별 재고 수집 시작")
                login(page)
                download_report(page)
                page.close()
                browser.close()
                print(f"[시도 {attempt}/3] 성공")
                return
            except Exception as e:
                last_error = e
                print(f"[시도 {attempt}/3] 실패: {e}")
                try:
                    page.screenshot(path=f"stocklot_error_attempt{attempt}.png", full_page=True)
                except Exception:
                    pass
                page.close()
                if attempt < 3:
                    print("5초 후 재시도...")
                    import time
                    time.sleep(5)
        browser.close()
    raise last_error


if __name__ == "__main__":
    run()
