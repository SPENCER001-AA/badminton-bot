import re
from playwright.sync_api import sync_playwright
from config import CONFIG
from auth import ensure_logged_in


# ===== 工具函数 =====

def safe_goto(page, url, verbose=True):
    if verbose:
        print("打开页面")
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2000)


def detect_page_reason(page):
    text = (page.text_content("body") or "").lower()

    if "already registered" in text or "already enrolled" in text:
        return "already_registered"

    if "full" in text or "no vacancy" in text:
        return "full"

    if "opens at" in text or "enrollment opens" in text:
        return "not_open_yet"

    return None


def is_final_stage(page):
    try:
        return page.get_by_role("button", name="Finish").count() > 0
    except:
        return False


def select_participant(page, name, verbose=True):
    try:
        locator = page.get_by_text(name)
        if locator.count() > 0:
            locator.first.click()
            return True
    except:
        pass

    if verbose:
        print("未找到参与人")

    return False


# ===== 核心流程 =====

def complete_final(page, participant_name, verbose=True):

    reason = detect_page_reason(page)
    if reason:
        return {"success": False, "reason": reason}

    if verbose:
        print("选择参与人")

    if not select_participant(page, participant_name):
        return {"success": False, "reason": "participant_not_found"}

    page.wait_for_timeout(1000)

    reason = detect_page_reason(page)
    if reason:
        return {"success": False, "reason": reason}

    # 勾选（不强依赖）
    try:
        checkbox = page.get_by_role("checkbox")
        if checkbox.count() > 0:
            checkbox.first.check(timeout=2000)
    except:
        pass

    if verbose:
        print("点击 Finish")

    finish = page.get_by_role("button", name="Finish")
    if finish.count() == 0:
        return {"success": False, "reason": "finish_not_found"}

    finish.first.click()
    page.wait_for_timeout(4000)

    reason = detect_page_reason(page)
    if reason:
        return {"success": False, "reason": reason}

    return {"success": True, "reason": "completed"}


# ===== 主函数 =====

def reserve(center_index, target_date_text, target_time, participant_name, verbose=True):

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=CONFIG["headless"])
        context = browser.new_context(storage_state="state.json")
        page = context.new_page()

        try:
            safe_goto(page, CONFIG["reserve_url"], verbose)

            if verbose:
                print("检查登录状态")
            ensure_logged_in(page, context, verbose=verbose)

            # ===== 如果已经在最终页面 =====
            if is_final_stage(page):
                return complete_final(page, participant_name, verbose)

            # ===== 进入预约流程 =====
            page.get_by_role("button", name="Day view").click()
            page.wait_for_timeout(1000)

            # 日期
            page.get_by_role("button", name=re.compile(r",")).first.click()
            page.get_by_text(target_date_text.split()[1], exact=True).click()
            page.wait_for_timeout(1500)

            # 中心
            page.get_by_role("button", name=re.compile("Center")).click()
            page.get_by_text("Bonsor").click()
            page.get_by_text(CONFIG["centers"][center_index]["short"]).click()
            page.get_by_role("button", name="Apply").click()
            page.wait_for_timeout(3000)

            # 找活动
            buttons = page.get_by_role("button").all()

            target_btn = None
            for b in buttons:
                try:
                    aria = b.get_attribute("aria-label") or ""
                    if target_time in aria and "Badminton" in aria:
                        target_btn = b
                        break
                except:
                    continue

            if not target_btn:
                return {"success": False, "reason": "activity_not_found"}

            target_btn.click()
            page.wait_for_timeout(1500)

            ensure_logged_in(page, context, verbose=verbose)

            # ===== Enroll =====
            enroll = page.get_by_role("button", name="Enroll Now")

            if enroll.count() == 0 or not enroll.first.is_enabled():
                reason = detect_page_reason(page)
                return {"success": False, "reason": reason or "not_available"}

            enroll.first.click()
            page.wait_for_timeout(2000)

            ensure_logged_in(page, context, verbose=verbose)

            # ===== 最终阶段 =====
            if is_final_stage(page):
                return complete_final(page, participant_name, verbose)

            return {"success": False, "reason": "unknown"}

        finally:
            browser.close()