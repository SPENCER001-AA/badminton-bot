from playwright.sync_api import sync_playwright
from config import CONFIG

def login_and_save_state():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=CONFIG["headless"])
        context = browser.new_context()
        page = context.new_page()

        print("1. 打开登录页")
        page.goto(CONFIG["login_url"])

        print("2. 等待用户名输入框出现")
        page.get_by_role("textbox", name="Email address Required").wait_for(timeout=10000)

        print("3. 输入用户名")
        page.get_by_role("textbox", name="Email address Required").fill(CONFIG["username"])

        print("4. 输入密码")
        page.get_by_role("textbox", name="Password Required").fill(CONFIG["password"])

        print("5. 点击登录")
        page.get_by_role("button", name="Sign in").click()

        print("6. 等待登录完成")
        page.wait_for_timeout(5000)

        print("7. 保存登录状态到 state.json")
        context.storage_state(path="state.json")

        input("如果已经登录成功，请按回车关闭浏览器...")
        browser.close()

if __name__ == "__main__":
    login_and_save_state()