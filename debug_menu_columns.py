"""사방넷 메뉴와 엑셀 열 이름 조사

새 수집 항목(유효기간별 재고)을 붙이려면 두 가지를 알아야 한다.

1. 재고 메뉴 아래에 어떤 화면들이 있는지 - 유효기간이 붙어 나오는 화면 이름
2. 엑셀받기 팝업에서 고를 수 있는 열 이름 - 유통기한, 주소가 있는지

결과는 전부 화면(로그)에 찍는다. 아티팩트를 내려받지 않아도
GitHub Actions 로그만 보고 바로 알 수 있게 하려는 것이다.
스크린샷은 따로 저장된다.
"""
import os
from playwright.sync_api import sync_playwright

COMPANY_CODE = os.environ["SB_COMPANY_CODE"]
USER_ID = os.environ["SB_USER_ID"]
PASSWORD = os.environ["SB_PASSWORD"]


def line(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


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


def visible_texts(page):
    """화면에 보이는 짧은 글자들을 모아 집합으로 (메뉴 항목 찾기용)"""
    out = set()
    for sel in ["a:visible", "li:visible", "span:visible", "div[role='menuitem']:visible"]:
        try:
            for t in page.locator(sel).all_inner_texts():
                t = t.strip()
                # 여러 줄이 뭉쳐 오는 경우가 있어 줄 단위로 쪼갠다
                for part in t.split("\n"):
                    part = part.strip()
                    if part and len(part) <= 30:
                        out.add(part)
        except Exception:
            pass
    return out


def dump_menu(page, menu_name):
    """메뉴를 눌러 새로 나타난 항목만 뽑는다"""
    line(f"[{menu_name}] 메뉴를 눌렀을 때 새로 나타나는 항목")
    before = visible_texts(page)
    try:
        page.get_by_text(menu_name, exact=True).first.click()
        page.wait_for_timeout(1200)
    except Exception as e:
        print(f"  메뉴 '{menu_name}' 를 못 눌렀습니다: {e}")
        return []
    after = visible_texts(page)
    new_items = sorted(after - before)
    if new_items:
        for t in new_items:
            print(f"  - {t}")
    else:
        print("  새로 나타난 항목이 없습니다. 아래 전체 목록을 보세요.")
        for t in sorted(after):
            print(f"  · {t}")
    page.screenshot(path=f"menu_{menu_name}.png", full_page=True)
    return new_items


def dump_excel_columns(page, screen_name, label):
    """화면을 열고 조회 → 엑셀받기 팝업의 열 목록을 뽑는다 (받기는 누르지 않음)"""
    line(f"[{label}] '{screen_name}' 화면의 엑셀받기 팝업에서 고를 수 있는 열")
    try:
        page.get_by_text(screen_name, exact=True).first.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)
    except Exception as e:
        print(f"  화면 '{screen_name}' 을 못 열었습니다: {e}")
        return

    try:
        btn = page.locator("button:has(i.fi-ico-search)").first
        btn.wait_for(state="visible", timeout=30000)
        btn.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)
    except Exception as e:
        print(f"  조회 버튼을 못 눌렀습니다: {e}")

    # 조회 결과 표의 열 머리글 (엑셀 열과 대개 같다)
    try:
        heads = [t.strip() for t in page.locator("th:visible").all_inner_texts() if t.strip()]
        if heads:
            print("  화면 표의 열 머리글:")
            print("    " + " | ".join(heads))
    except Exception:
        pass

    page.screenshot(path=f"cols_{label}_1_result.png", full_page=True)

    try:
        page.locator("button:has-text('엑셀받기')").first.click()
        page.wait_for_timeout(1500)
    except Exception as e:
        print(f"  엑셀받기를 못 눌렀습니다: {e}")
        return

    page.screenshot(path=f"cols_{label}_2_popup.png", full_page=True)

    # 팝업의 체크박스 옆 글자 = 고를 수 있는 열 이름
    try:
        boxes = page.locator("input[type='checkbox']:visible")
        n = boxes.count()
        names = []
        for i in range(n):
            cb = boxes.nth(i)
            name = ""
            try:
                name = cb.get_attribute("aria-label") or ""
            except Exception:
                pass
            if not name:
                try:
                    name = cb.evaluate(
                        "el => (el.closest('label') || el.parentElement)?.innerText || ''"
                    ).strip()
                except Exception:
                    name = ""
            if name:
                names.append(name.replace("\n", " ").strip())
        print(f"  체크박스 {n}개, 이름을 읽은 것 {len(names)}개:")
        for nm in names:
            print(f"    - {nm}")
        # 우리가 찾는 열이 있는지 바로 알려준다
        joined = " ".join(names)
        for keyword in ["유통기한", "유효기간", "소비기한", "주소", "상세주소", "전화"]:
            if keyword in joined:
                print(f"  >> '{keyword}' 열이 있습니다")
    except Exception as e:
        print(f"  열 목록을 못 읽었습니다: {e}")

    # 팝업 닫기
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(600)
    except Exception:
        pass


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        try:
            login(page)
            page.screenshot(path="menu_0_after_login.png", full_page=True)

            # 1) 재고 메뉴 아래 화면들
            stock_items = dump_menu(page, "재고")

            # 2) 재고조회(기본) 의 엑셀 열 - 유통기한이 여기 있는지 확인
            dump_excel_columns(page, "재고조회(기본)", "재고조회기본")

            # 3) 재고 메뉴의 다른 화면들도 열 머리글만 훑는다
            line("[재고] 메뉴의 다른 화면들 - 표 열 머리글만 확인")
            skip = {"재고조회(기본)", "재고"}
            for item in stock_items:
                if item in skip:
                    continue
                try:
                    page.get_by_text("재고", exact=True).first.click()
                    page.wait_for_timeout(700)
                    page.get_by_text(item, exact=True).first.click()
                    page.wait_for_load_state("networkidle")
                    page.wait_for_timeout(1200)
                    heads = [t.strip() for t in page.locator("th:visible").all_inner_texts() if t.strip()]
                    mark = ""
                    for keyword in ["유통기한", "유효기간", "소비기한"]:
                        if any(keyword in hh for hh in heads):
                            mark = f"   << '{keyword}' 있음"
                            break
                    print(f"  [{item}]{mark}")
                    print("    " + (" | ".join(heads) if heads else "(열 머리글 없음)"))
                except Exception as e:
                    print(f"  [{item}] 열어보지 못함: {e}")

            # 4) 발주 메뉴 - 주소 열 확인
            dump_menu(page, "발주")
            dump_excel_columns(page, "발주조회", "발주조회")

        finally:
            page.screenshot(path="menu_9_last.png", full_page=True)
            browser.close()

    line("조사 끝")
    print("위 목록에서 유효기간이 붙어 나오는 화면 이름과, 발주조회의 주소 열 이름을 알려주세요.")


if __name__ == "__main__":
    run()
