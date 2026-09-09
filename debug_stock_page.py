import os
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


def dump_buttons(page, filename):
    buttons = page.locator("button:visible")
    count = buttons.count()
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"화면에 보이는 버튼 개수: {count}\n\n")
        for i in range(count):
            btn = buttons.nth(i)
            try:
                text = btn.inner_text().strip()
            except Exception:
                text = "(텍스트 없음)"
            try:
                outer = btn.evaluate("el => el.outerHTML")
            except Exception:
                outer = "(가져오기 실패)"
            f.write(f"[버튼 {i}] 텍스트='{text}'\n{outer}\n\n")

    inputs_all = page.locator("input[type='checkbox']:visible")
    count2 = inputs_all.count()
    with open(filename.replace(".txt", "_checkboxes.txt"), "w", encoding="utf-8") as f:
        f.write(f"체크박스 개수: {count2}\n\n")
        for i in range(count2):
            cb = inputs_all.nth(i)
            try:
                outer = cb.evaluate("el => el.outerHTML")
            except Exception:
                outer = "(실패)"
            try:
                parent_text = cb.evaluate("el => el.closest('div')?.innerText || ''")
            except Exception:
                parent_text = ""
            f.write(f"[체크박스 {i}] 주변텍스트='{parent_text.strip()}'\n{outer}\n\n")


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1920, "height": 1080})

        login(page)

        page.get_by_text("재고", exact=True).first.click()
        page.wait_for_timeout(800)

        page.get_by_text("재고조회(기본)", exact=True).click()
        page.wait_for_timeout(2000)

        page.locator("button:has(i.fi-ico-search)").first.click()
        page.wait_for_timeout(2000)
        page.screenshot(path="g1_after_search.png", full_page=True)

        page.locator("button:has-text('엑셀받기')").first.click()
        page.wait_for_timeout(1500)
        page.screenshot(path="g2_excel_popup.png", full_page=True)

        dump_buttons(page, "g3_popup_buttons.txt")

        print("디버그 정보 저장 완료")

        browser.close()


if __name__ == "__main__":
    run()
