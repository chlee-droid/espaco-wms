import os
from playwright.sync_api import sync_playwright

COMPANY_CODE = os.environ["SB_COMPANY_CODE"]
USER_ID = os.environ["SB_USER_ID"]
PASSWORD = os.environ["SB_PASSWORD"]


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto("https://wms02.sbfulfillment.co.kr/login")
        page.wait_for_load_state("networkidle")

        # 로그인 폼의 입력창을 화면에 보이는 순서대로 가져옵니다.
        # (회사코드 -> 아이디 -> 비밀번호 순서라고 가정)
        inputs = page.locator("input:visible")
        count = inputs.count()
        print(f"발견된 입력창 수: {count}")

        inputs.nth(0).fill(COMPANY_CODE)
        inputs.nth(1).fill(USER_ID)
        inputs.nth(2).fill(PASSWORD)

        page.screenshot(path="1_before_login.png")

        page.get_by_role("button", name="로그인").click()
        page.wait_for_timeout(4000)

        page.screenshot(path="2_after_login.png")
        print("로그인 시도 후 현재 URL:", page.url)

        browser.close()


if __name__ == "__main__":
    run()
