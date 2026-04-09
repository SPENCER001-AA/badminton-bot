from datetime import datetime
from config import CONFIG
from query import query_open_times
from reserve import reserve


def normalize_date_input(date_str: str) -> str | None:
    """
    支持两种输入格式：
    1. 2026-04-08
    2. Apr 8, 2026

    返回统一格式：
    Apr 8, 2026
    """
    date_str = date_str.strip()

    if not date_str:
        return None

    # 格式 1：2026-04-08
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{dt.strftime('%b')} {dt.day}, {dt.year}"
    except ValueError:
        pass

    # 格式 2：Apr 8, 2026
    try:
        dt = datetime.strptime(date_str, "%b %d, %Y")
        return f"{dt.strftime('%b')} {dt.day}, {dt.year}"
    except ValueError:
        pass

    return None


def choose_center():
    centers = CONFIG["centers"]

    print("可选社区：")
    for i, center in enumerate(centers, start=1):
        print(f"{i}. {center['short']}")

    default_index = CONFIG["default_center_index"] + 1
    user_input = input(f"\n请输入社区编号（直接回车默认 {default_index}）: ").strip()

    if not user_input:
        return CONFIG["default_center_index"]

    try:
        choice = int(user_input)
        if 1 <= choice <= len(centers):
            return choice - 1
    except ValueError:
        pass

    print("输入无效，使用默认社区。")
    return CONFIG["default_center_index"]


def choose_date():
    default_date = CONFIG["target_date_text"]

    print("\n日期输入格式示例：")
    print("1. 2026-04-08")
    print("2. Apr 8, 2026")

    user_input = input(f"\n请输入目标日期（直接回车默认 {default_date}）: ").strip()

    if not user_input:
        return default_date

    normalized = normalize_date_input(user_input)
    if normalized:
        return normalized

    print("日期格式无效，使用默认日期。")
    return default_date


def choose_participant():
    participants = CONFIG["participants"]
    default_participant = CONFIG["default_participant"]

    print("\n可选参与人：")
    for i, p in enumerate(participants, start=1):
        default_mark = "（默认）" if p == default_participant else ""
        print(f"{i}. {p} {default_mark}")

    default_index = participants.index(default_participant) + 1
    user_input = input(f"\n请输入参与人编号（直接回车默认 {default_index}）: ").strip()

    if not user_input:
        return default_participant

    try:
        choice = int(user_input)
        if 1 <= choice <= len(participants):
            return participants[choice - 1]
    except ValueError:
        pass

    print("输入无效，使用默认参与人。")
    return default_participant


def choose_time_from_results(results):
    valid_results = [item for item in results if item.get("time")]

    if not valid_results:
        return None

    print("\n查询到的开放时间：")
    for i, item in enumerate(valid_results, start=1):
        print(f"{i}. {item['time']}")

    user_input = input("\n请输入你想预约的时间编号: ").strip()

    try:
        choice = int(user_input)
        if 1 <= choice <= len(valid_results):
            return valid_results[choice - 1]["time"]
    except ValueError:
        pass

    print("输入无效。")
    return None


def main():
    print("=== 羽毛球预约程序 ===\n")

    # 1. 选社区
    center_index = choose_center()
    center_name = CONFIG["centers"][center_index]["short"]

    # 2. 选日期（现在支持输入）
    target_date_text = choose_date()

    print(f"\n目标日期：{target_date_text}")
    print(f"目标社区：{center_name}")

    # 3. 查询开放时间
    print("\n开始查询开放时间...\n")
    results = query_open_times(
        center_index=center_index,
        target_date_text=target_date_text,
        verbose=True
    )

    if not results:
        print("\n没有查询到任何活动，程序结束。")
        return

    # 4. 选择时间
    target_time = choose_time_from_results(results)
    if not target_time:
        print("\n没有选择有效时间，程序结束。")
        return

    print(f"\n你选择的时间：{target_time}")

    # 5. 选择参与人
    participant_name = choose_participant()
    print(f"\n你选择的参与人：{participant_name}")

    # 6. 确认执行
    confirm = input("\n确认开始执行预约吗？(y/n): ").strip().lower()
    if confirm != "y":
        print("已取消预约。")
        return

    # 7. 执行预约
    print("\n开始执行预约...\n")
    result = reserve(
        center_index=center_index,
        target_date_text=target_date_text,
        target_time=target_time,
        participant_name=participant_name,
        verbose=True
    )

    # 8. 输出最终结果
    print("\n=== 最终结果 ===")
    print(result)


if __name__ == "__main__":
    main()