import re
from datetime import datetime
from playwright.sync_api import sync_playwright
from config import CONFIG
from auth import ensure_logged_in


def switch_to_day_view(page):
    """切换到 Day view。"""
    print("切换到 Day view")
    page.get_by_role("button", name="Day view").click()
    page.wait_for_timeout(1000)


def open_date_picker(page):
    """
    点击当前显示的日期按钮（例如：Wed, Apr 8, 2026）
    打开日期选择器。
    """
    print("打开日期选择器")

    date_button = page.get_by_role(
        "button",
        name=re.compile(
            r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s[A-Z][a-z]{2}\s\d{1,2},\s\d{4}$"
        )
    ).first

    date_button.wait_for(timeout=10000)
    date_button.click()
    page.wait_for_timeout(1000)


def select_target_day(page, target_date_text: str):
    """
    在日期选择器中点击目标日期数字。
    例如：
    Apr 8, 2026 -> 点击 8
    """
    dt = datetime.strptime(target_date_text, "%b %d, %Y")
    day_str = str(dt.day)

    print(f"选择目标日期：{day_str}")
    page.get_by_text(day_str, exact=True).first.click()
    page.wait_for_timeout(1500)


def open_center_filter(page):
    """打开中心筛选器。"""
    print("打开中心筛选器")
    page.get_by_role("button", name=re.compile(r"Filter.*Center.*selected")).click()
    page.wait_for_timeout(1000)


def switch_center(page, target_center_short: str):
    """
    当前网页默认选中 Bonsor。
    当前已知逻辑：
    1. 取消 Bonsor
    2. 选择目标中心
    3. 点击 Apply
    """
    menu = page.get_by_label("multiple menu")

    print("取消 Bonsor")
    menu.get_by_text("Bonsor Recreation Complex (").click()
    page.wait_for_timeout(500)

    print(f"选择中心：{target_center_short}")
    menu.get_by_text(target_center_short).click()
    page.wait_for_timeout(500)

    print("点击 Apply")
    page.get_by_role("button", name="Apply").click()
    page.wait_for_timeout(3000)


def extract_time(aria_label: str):
    """
    从 aria-label 提取时间段，例如：
    10:30 AM - 12:30 PM
    """
    pattern = r"\b\d{1,2}:\d{2}\s?[AP]M\s-\s\d{1,2}:\d{2}\s?[AP]M\b"
    match = re.search(pattern, aria_label)
    return match.group(0) if match else None


def query_open_times(center_index: int, target_date_text: str, verbose: bool = True):
    """
    查询指定中心、指定日期的羽毛球开放时间。

    返回：
    [
        {
            "name": "...",
            "time": "10:30 AM - 12:30 PM",
            "aria": "..."
        },
        ...
    ]
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=CONFIG["headless"])
        context = browser.new_context(storage_state="state.json")
        page = context.new_page()

        center = CONFIG["centers"][center_index]
        center_short = center["short"]

        if verbose:
            print("1. 打开页面")
        page.goto(CONFIG["reserve_url"])
        page.wait_for_timeout(2000)

        if verbose:
            print("2. 检查登录状态")
        ensure_logged_in(page, context, verbose=verbose)

        # 登录后，有些网站不会自动回到原目标页，所以再打开一次预约页更稳
        if verbose:
            print("3. 进入预约页面")
        page.goto(CONFIG["reserve_url"])
        page.wait_for_timeout(3000)

        if verbose:
            print("4. 切换 Day view")
        switch_to_day_view(page)

        if verbose:
            print("5. 选择日期")
        open_date_picker(page)
        select_target_day(page, target_date_text)

        if verbose:
            print("6. 切换中心")
        open_center_filter(page)
        switch_center(page, center_short)

        if verbose:
            print("7. 查找活动")

        buttons = page.get_by_role("button").all()
        activities = []

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

            activities.append({
                "name": text,
                "time": time_range,
                "aria": aria
            })

        # 去重
        unique = []
        seen = set()

        for item in activities:
            key = item["aria"] or item["name"]
            if key not in seen:
                seen.add(key)
                unique.append(item)

        if verbose:
            print("\n查询结果：")
            if not unique:
                print("没有找到活动")
            else:
                for i, item in enumerate(unique, start=1):
                    print(f"\n--- 活动 {i} ---")
                    print("名称:", item["name"])
                    print("时间:", item["time"] if item["time"] else "未识别")

                print("\n最终时间列表：")
                time_list = [item["time"] for item in unique if item["time"]]
                time_list = list(dict.fromkeys(time_list))

                if not time_list:
                    print("没有提取到时间")
                else:
                    for i, t in enumerate(time_list, start=1):
                        print(f"{i}. {t}")

        browser.close()
        return unique


if __name__ == "__main__":
    results = query_open_times(
        center_index=CONFIG["default_center_index"],
        target_date_text=CONFIG["target_date_text"],
        verbose=True
    )

    print("\n返回的数据对象：")
    print(results)