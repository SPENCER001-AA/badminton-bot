import json
import time
import re
from pathlib import Path
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from config import CONFIG
from auth import ensure_logged_in


TASKS_FILE = Path("tasks.json")


# =========================
# 基础工具
# =========================

def parse_target_date(target_date_text: str) -> datetime:
    return datetime.strptime(target_date_text, "%b %d, %Y")


def calculate_prepare_and_run_time(target_date_text: str):
    """
    根据目标日期计算：
    - 预热时间：前两天 09:55
    - 执行时间：前两天 10:00
    """
    target_date = parse_target_date(target_date_text)
    booking_day = target_date - timedelta(days=2)

    prepare_time = booking_day.replace(hour=9, minute=55, second=0, microsecond=0)
    run_time = booking_day.replace(hour=10, minute=0, second=0, microsecond=0)

    return prepare_time, run_time


def load_tasks():
    if not TASKS_FILE.exists():
        return []

    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_tasks(tasks):
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)


def parse_task_time(time_str: str) -> datetime:
    return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")


def task_signature(task: dict):
    return (
        task["center_index"],
        task["target_date_text"],
        task["target_time"],
        task["participant_name"],
    )


def create_task(center_index: int, target_date_text: str, target_time: str, participant_name: str):
    prepare_time, run_time = calculate_prepare_and_run_time(target_date_text)
    center = CONFIG["centers"][center_index]

    tasks = load_tasks()
    new_sig = (center_index, target_date_text, target_time, participant_name)

    for task in tasks:
        if task_signature(task) == new_sig and task["status"] in [
            "pending", "preparing", "prepared", "running"
        ]:
            return None

    task = {
        "id": datetime.now().strftime("%Y%m%d%H%M%S"),
        "center_index": center_index,
        "center_name": center["short"],
        "target_date_text": target_date_text,
        "target_time": target_time,
        "participant_name": participant_name,
        "prepare_time": prepare_time.strftime("%Y-%m-%d %H:%M:%S"),
        "run_time": run_time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "pending",
        "prepare_result": None,
        "final_result": None,
    }

    tasks.append(task)
    save_tasks(tasks)
    return task


def print_task(task):
    print("\n=== 任务已创建 ===")
    print(f"任务ID：{task['id']}")
    print(f"社区：{task['center_name']}")
    print(f"目标日期：{task['target_date_text']}")
    print(f"目标时间：{task['target_time']}")
    print(f"参与人：{task['participant_name']}")
    print(f"预热时间：{task['prepare_time']}")
    print(f"执行时间：{task['run_time']}")
    print(f"状态：{task['status']}")


def list_tasks():
    tasks = load_tasks()
    if not tasks:
        print("当前没有任何任务。")
        return

    print("\n=== 当前任务列表 ===")
    for i, task in enumerate(tasks, start=1):
        print(f"\n--- 任务 {i} ---")
        print(f"任务ID：{task['id']}")
        print(f"社区：{task['center_name']}")
        print(f"目标日期：{task['target_date_text']}")
        print(f"目标时间：{task['target_time']}")
        print(f"参与人：{task['participant_name']}")
        print(f"预热时间：{task['prepare_time']}")
        print(f"执行时间：{task['run_time']}")
        print(f"状态：{task['status']}")
        if task.get("prepare_result") is not None:
            print(f"预热结果：{task['prepare_result']}")
        if task.get("final_result") is not None:
            print(f"最终结果：{task['final_result']}")


def mark_duplicate_tasks(tasks):
    groups = {}
    for task in tasks:
        sig = task_signature(task)
        groups.setdefault(sig, []).append(task)

    changed = False

    for _, group in groups.items():
        active = [t for t in group if t["status"] in ["pending", "preparing", "prepared", "running"]]
        if len(active) <= 1:
            continue

        active_sorted = sorted(active, key=lambda x: x["id"])
        for task in active_sorted[1:]:
            if task["status"] in ["pending", "preparing", "prepared", "running"]:
                task["status"] = "duplicate_skipped"
                task["final_result"] = {
                    "success": False,
                    "reason": "duplicate_skipped"
                }
                changed = True

    return changed


# =========================
# 页面操作工具
# =========================

def safe_goto(page, url: str, verbose: bool = True, max_retries: int = 3):
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            if verbose:
                print(f"打开页面，第 {attempt} 次尝试")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1500)
            return
        except PlaywrightTimeoutError as e:
            last_error = e
            if verbose:
                print(f"第 {attempt} 次打开超时，准备重试...")
            page.wait_for_timeout(1500)

    raise last_error


def page_body_text(page) -> str:
    try:
        return (page.text_content("body") or "").lower()
    except Exception:
        return ""


def detect_page_reason(page):
    text = page_body_text(page)

    if "already registered" in text or "already enrolled" in text or "you are already registered" in text:
        return "already_registered"

    if "full" in text or "no vacancy" in text:
        return "full"

    if "opens at" in text or "enrollment opens" in text or "opens on" in text:
        return "not_open_yet"

    return None


def switch_to_day_view(page):
    page.get_by_role("button", name="Day view").click()
    page.wait_for_timeout(800)


def open_date_picker(page):
    date_button = page.get_by_role(
        "button",
        name=re.compile(
            r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s[A-Z][a-z]{2}\s\d{1,2},\s\d{4}$"
        )
    ).first
    date_button.wait_for(timeout=10000)
    date_button.click()
    page.wait_for_timeout(800)


def select_target_day(page, target_date_text: str):
    dt = parse_target_date(target_date_text)
    day_str = str(dt.day)
    page.get_by_text(day_str, exact=True).first.click()
    page.wait_for_timeout(1200)


def open_center_filter(page):
    page.get_by_role("button", name=re.compile(r"Filter.*Center.*selected")).click()
    page.wait_for_timeout(800)


def switch_center(page, target_center_short: str):
    menu = page.get_by_label("multiple menu")

    bonsor = menu.get_by_text("Bonsor Recreation Complex (")
    if bonsor.count() > 0:
        bonsor.first.click()
        page.wait_for_timeout(300)

    menu.get_by_text(target_center_short).click()
    page.wait_for_timeout(300)

    page.get_by_role("button", name="Apply").click()
    page.wait_for_timeout(2500)


def extract_time(aria_label: str):
    pattern = r"\b\d{1,2}:\d{2}\s?[AP]M\s-\s\d{1,2}:\d{2}\s?[AP]M\b"
    match = re.search(pattern, aria_label)
    return match.group(0) if match else None


def find_activity_button_by_time(page, target_time: str):
    buttons = page.get_by_role("button").all()

    for btn in buttons:
        try:
            text = btn.inner_text().strip()
        except Exception:
            continue

        if "Badminton" not in text:
            continue

        try:
            aria = btn.get_attribute("aria-label") or ""
            aria = aria.strip()
        except Exception:
            aria = ""

        time_range = extract_time(aria)
        if time_range == target_time:
            return btn

    return None


def get_enroll_button(page):
    return page.get_by_role("button", name="Enroll Now").first


def is_final_enrollment_stage(page) -> bool:
    try:
        finish_button = page.get_by_role("button", name="Finish")
        fee_summary = page.get_by_role("button", name=re.compile(r"Fee summary", re.I))
        return finish_button.count() > 0 or fee_summary.count() > 0
    except Exception:
        return False


def select_participant(page, participant_name: str, verbose=True):
    page.wait_for_timeout(800)

    if verbose:
        print(f"选择参与人：{participant_name}")

    candidates = [
        page.get_by_text(participant_name, exact=True),
        page.locator("div").filter(has_text=re.compile(rf"^{re.escape(participant_name)}$")),
        page.locator("label").filter(has_text=re.compile(rf"{re.escape(participant_name)}")),
        page.locator("span").filter(has_text=re.compile(rf"{re.escape(participant_name)}")),
        page.locator("button").filter(has_text=re.compile(rf"{re.escape(participant_name)}")),
    ]

    for locator in candidates:
        try:
            if locator.count() > 0:
                locator.first.click(timeout=3000)
                page.wait_for_timeout(800)
                return True
        except Exception:
            continue

    return False


def complete_final_enrollment(page, participant_name: str, verbose=True):
    page.wait_for_timeout(800)

    reason = detect_page_reason(page)
    if reason:
        if verbose:
            print(f"检测到状态：{reason}")
        return {
            "success": False,
            "reason": reason
        }

    if not select_participant(page, participant_name, verbose=verbose):
        return {
            "success": False,
            "reason": "participant_not_found"
        }

    page.wait_for_timeout(800)

    reason = detect_page_reason(page)
    if reason:
        return {
            "success": False,
            "reason": reason
        }

    try:
        fee_summary = page.get_by_role("button", name=re.compile(r"Fee summary", re.I))
        if fee_summary.count() > 0:
            if verbose:
                print("展开 Fee summary")
            fee_summary.first.click(timeout=2000)
            page.wait_for_timeout(500)
    except Exception:
        pass

    if verbose:
        print("尝试勾选协议")

    try:
        checkbox = page.get_by_role("checkbox")
        if checkbox.count() > 0:
            checkbox.first.check(timeout=2000)
            page.wait_for_timeout(500)
    except Exception:
        if verbose:
            print("没有 checkbox，跳过")

    finish_button = page.get_by_role("button", name="Finish")
    if finish_button.count() == 0:
        reason = detect_page_reason(page)
        return {
            "success": False,
            "reason": reason or "finish_not_found"
        }

    if verbose:
        print("点击 Finish")

    try:
        finish_button.first.click(timeout=3000)
        page.wait_for_timeout(3000)
    except Exception:
        return {
            "success": False,
            "reason": "finish_click_failed"
        }

    reason = detect_page_reason(page)
    if reason:
        return {
            "success": False,
            "reason": reason
        }

    return {
        "success": True,
        "reason": "completed"
    }


def navigate_to_activity_detail(page, task, verbose=True):
    if verbose:
        print("进入预约页面")
    safe_goto(page, CONFIG["reserve_url"], verbose=verbose)

    if verbose:
        print("切换 Day view")
    switch_to_day_view(page)

    if verbose:
        print("选择日期")
    open_date_picker(page)
    select_target_day(page, task["target_date_text"])

    if verbose:
        print("切换中心")
    open_center_filter(page)
    switch_center(page, task["center_name"])

    if verbose:
        print(f"查找目标时间活动：{task['target_time']}")
    activity_button = find_activity_button_by_time(page, task["target_time"])
    if activity_button is None:
        return False

    if verbose:
        print("点击活动")
    activity_button.click()
    page.wait_for_timeout(1200)

    return True


# =========================
# 预热 / 执行
# =========================

def prepare_task_session(playwright, task, verbose=True):
    """
    09:55 预热：
    - 打开浏览器
    - 登录
    - 进入目标活动详情页
    - 保留页面等待 10:00
    """
    if verbose:
        print(f"\n[预热] 开始处理任务 {task['id']}")

    browser = playwright.chromium.launch(headless=CONFIG["headless"])
    context = browser.new_context(storage_state="state.json")
    page = context.new_page()

    try:
        safe_goto(page, CONFIG["reserve_url"], verbose=verbose)

        if verbose:
            print("[预热] 检查登录状态")
        ensure_logged_in(page, context, verbose=verbose)
        page.wait_for_timeout(1200)

        if is_final_enrollment_stage(page):
            if verbose:
                print("[预热] 已经在最后报名阶段")
            return {
                "ok": True,
                "browser": browser,
                "context": context,
                "page": page,
                "stage": "final"
            }

        ok = navigate_to_activity_detail(page, task, verbose=verbose)
        if not ok:
            browser.close()
            return {
                "ok": False,
                "reason": "activity_not_found"
            }

        if verbose:
            print("[预热] 活动详情页已打开，等待执行时间")
        return {
            "ok": True,
            "browser": browser,
            "context": context,
            "page": page,
            "stage": "detail"
        }

    except Exception as e:
        try:
            browser.close()
        except Exception:
            pass
        return {
            "ok": False,
            "reason": f"prepare_exception: {str(e)}"
        }


def wait_until_run_time(run_time: datetime, page=None):
    """
    分阶段等待到执行时间：
    - 距离 > 10 秒：低频等待
    - 距离 <= 10 秒：高频等待
    """
    while True:
        now = datetime.now()
        seconds_left = (run_time - now).total_seconds()

        if seconds_left <= 0:
            return

        if seconds_left > 10:
            sleep_s = min(0.5, max(0.1, seconds_left - 9.5))
            time.sleep(sleep_s)
            if page:
                try:
                    page.wait_for_timeout(50)
                except Exception:
                    pass
        else:
            time.sleep(0.05)
            if page:
                try:
                    page.wait_for_timeout(20)
                except Exception:
                    pass


def run_prepared_task(session, task, verbose=True):
    """
    10:00 正式执行：
    - 复用预热页面
    - 等到 run_time
    - 到点后直接点 Enroll Now
    - 不做刷新
    """
    page = session["page"]
    context = session["context"]
    browser = session["browser"]

    try:
        if verbose:
            print(f"\n[执行] 开始处理任务 {task['id']}")

        ensure_logged_in(page, context, verbose=verbose)
        page.wait_for_timeout(500)

        if is_final_enrollment_stage(page):
            if verbose:
                print("[执行] 已在最后报名阶段，直接继续")
            return complete_final_enrollment(page, task["participant_name"], verbose=verbose)

        run_time = parse_task_time(task["run_time"])

        if verbose:
            print("[执行] 保持当前页面不动，等待到执行时刻")
        wait_until_run_time(run_time, page=page)

        reason = detect_page_reason(page)
        if reason in ["already_registered", "full"]:
            return {
                "success": False,
                "reason": reason
            }

        enroll_button = get_enroll_button(page)
        if enroll_button.count() == 0:
            return {
                "success": False,
                "reason": "enroll_not_found"
            }

        try:
            if not enroll_button.is_enabled():
                reason = detect_page_reason(page)
                return {
                    "success": False,
                    "reason": reason or "enroll_not_enabled"
                }
        except Exception:
            return {
                "success": False,
                "reason": "enroll_check_failed"
            }

        if verbose:
            print("[执行] 到点，直接点击 Enroll Now")
        enroll_button.click(timeout=3000)
        page.wait_for_timeout(1200)

        ensure_logged_in(page, context, verbose=verbose)
        page.wait_for_timeout(800)

        if is_final_enrollment_stage(page):
            return complete_final_enrollment(page, task["participant_name"], verbose=verbose)

        reason = detect_page_reason(page)
        if reason:
            return {
                "success": False,
                "reason": reason
            }

        return {
            "success": False,
            "reason": "final_stage_not_reached"
        }

    finally:
        try:
            browser.close()
        except Exception:
            pass


# =========================
# 调度主逻辑
# =========================

def process_tasks_once_with_sessions(playwright, prepared_sessions):
    tasks = load_tasks()
    if not tasks:
        print("当前没有任务。")
        return

    changed = mark_duplicate_tasks(tasks)
    now = datetime.now()

    for task in tasks:
        status = task.get("status", "pending")
        prepare_time = parse_task_time(task["prepare_time"])
        run_time = parse_task_time(task["run_time"])
        task_id = task["id"]

        if status == "pending" and now >= prepare_time and now < run_time:
            print(f"\n检测到任务 {task_id} 到达预热时间")
            task["status"] = "preparing"
            save_tasks(tasks)

            session = prepare_task_session(playwright, task, verbose=True)
            if session["ok"]:
                prepared_sessions[task_id] = session
                task["status"] = "prepared"
                task["prepare_result"] = {
                    "success": True,
                    "reason": "prepared"
                }
            else:
                task["status"] = "failed"
                task["prepare_result"] = {
                    "success": False,
                    "reason": session["reason"]
                }

            changed = True
            save_tasks(tasks)

        elif status in ["pending", "prepared"] and now >= run_time:
            print(f"\n检测到任务 {task_id} 到达执行时间")
            task["status"] = "running"
            save_tasks(tasks)

            session = prepared_sessions.get(task_id)

            if session is None:
                # 如果进程重启，session 丢了，只能临时重建
                session = prepare_task_session(playwright, task, verbose=True)
                if not session["ok"]:
                    task["status"] = "failed"
                    task["final_result"] = {
                        "success": False,
                        "reason": session["reason"]
                    }
                    changed = True
                    save_tasks(tasks)
                    continue

            result = run_prepared_task(session, task, verbose=True)
            task["final_result"] = result

            if result.get("success"):
                task["status"] = "completed"
            else:
                task["status"] = "failed"

            if task_id in prepared_sessions:
                prepared_sessions.pop(task_id, None)

            changed = True
            save_tasks(tasks)

    if changed:
        save_tasks(tasks)


def scheduler_loop(interval_seconds: int = 5):
    print("=== 调度器已启动 ===")
    print(f"轮询间隔：{interval_seconds} 秒")
    print("按 Ctrl+C 停止\n")

    prepared_sessions = {}

    with sync_playwright() as playwright:
        try:
            while True:
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"[{now}] 开始检查任务...")
                process_tasks_once_with_sessions(playwright, prepared_sessions)
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            print("\n调度器已停止。")
        finally:
            for _, session in prepared_sessions.items():
                try:
                    session["browser"].close()
                except Exception:
                    pass


# =========================
# 交互入口
# =========================

if __name__ == "__main__":
    print("请选择模式：")
    print("1. 创建测试任务")
    print("2. 查看任务列表")
    print("3. 启动调度器")

    choice = input("\n请输入编号: ").strip()

    if choice == "1":
        task = create_task(
            center_index=CONFIG["default_center_index"],
            target_date_text=CONFIG["target_date_text"],
            target_time="10:30 AM - 12:30 PM",
            participant_name=CONFIG["default_participant"]
        )
        if task is None:
            print("已有相同的未完成任务，本次不重复创建。")
        else:
            print_task(task)

    elif choice == "2":
        list_tasks()

    elif choice == "3":
        scheduler_loop(interval_seconds=5)

    else:
        print("输入无效。")