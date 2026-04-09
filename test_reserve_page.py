from playwright.sync_api import sync_playwright
from config import CONFIG

def open_reserve_page():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=CONFIG["headless"])
        context = browser.new_context(storage_state="state.json")
        page = context.new_page()

        print("1. 打开预约页")
        page.goto(CONFIG["reserve_url"])

        print("当前页面标题：", page.title())
        input("请观察是否已经直接进入预约页面，按回车关闭浏览器...")

        browser.close()

if __name__ == "__main__":
    open_reserve_page()