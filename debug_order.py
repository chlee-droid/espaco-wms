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


def dump_all(page, filename):
    buttons = page.locator("button:visible")
    count = buttons.count()
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"=== 버튼 {count}개 ===\n\n")
        for i in range(count):
            btn = buttons.nth(i)
            try:
                text = btn.inner_text().strip()
            except Exception:
                text = "(텍스트 없음)"
            try:
                outer = btn.evaluate("el => el.outerHTML")
            except Exception:
                outer = "(실패)"
            f.write(f"[버튼 {i}] 텍스트='{text}'\n{outer}\n\n")

        selects = page.locator("select:visible")
        scount = selects.count()
        f.write(f"\n=== select 태그 {scount}개 ===\n\n")
        for i in range(scount):
            sel = selects.nth(i)
            try:
                outer = sel.evaluate("el => el.outerHTML")
            except Exception:
                outer = "(실패)"
            f.write(f"[select {i}]\n{outer}\n\n")

        combo = page.locator("[role='combobox']:visible, .v-select:visible")
        ccount = combo.count()
        f.write(f"\n=== combobox/v-select {ccount}개 ===\n\n")
        for i in range(ccount):
            c = combo.nth(i)
            try:
                text = c.inner_text().strip()
            except Exception:
                text = ""
            try:
                outer = c.evaluate("el => el.outerHTML.slice(0, 800)")
            except Exception:
                outer = "(실패)"
            f.write(f"[combo {i}] 텍스트='{text}'\n{outer}\n\n")


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1920, "height": 1080})

        login(page)

        page.get_by_text("발주", exact=True).first.click()
        page.wait_for_timeout(800)
        page.get_by_text("발주조회", exact=True).click()
        page.wait_for_timeout(2000)

        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        today = datetime.now().strftime("%Y-%m-%d")
        date_fields = page.locator(".flatpickr-input")
        date_fields.nth(0).fill(yesterday)
        date_fields.nth(1).fill(today)
        page.mouse.click(1700, 400)
        page.wait_for_timeout(500)

        page.locator("button.bg-primary:has(i.fi-ico-search)").first.click()
        page.wait_for_timeout(2500)
        page.screenshot(path="l1_search_result.png", full_page=True)

        page.get_by_role("button", name="엑셀받기", exact=True).click()
        page.wait_for_timeout(1500)
        page.screenshot(path="l2_excel_popup.png", full_page=True)

        dump_all(page, "l3_popup_dump.txt")

        print("디버그 완료")

        browser.close()


if __name__ == "__main__":
    run()
