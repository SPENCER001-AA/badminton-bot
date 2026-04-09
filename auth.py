from config import CONFIG


def is_login_page(page) -> bool:
    """
    判断当前页面是否是登录页。
    """
    try:
        email_box = page.get_by_role("textbox", name="Email address Required")
        password_box = page.get_by_role("textbox", name="Password Required")
        sign_in_button = page.get_by_role("button", name="Sign in")

        return (
            email_box.count() > 0 and
            password_box.count() > 0 and
            sign_in_button.count() > 0
        )
    except Exception:
        return False


def do_login(page, context, verbose: bool = True):
    """
    执行自动登录，并更新 state.json
    """
    if verbose:
        print("检测到未登录，开始自动登录")

    page.wait_for_timeout(2000)

    page.get_by_role("textbox", name="Email address Required").fill(CONFIG["username"])
    page.get_by_role("textbox", name="Password Required").fill(CONFIG["password"])
    page.get_by_role("button", name="Sign in").click()

    page.wait_for_timeout(5000)

    if verbose:
        print("登录完成，更新 state.json")

    context.storage_state(path="state.json")


def ensure_logged_in(page, context, verbose: bool = True):
    """
    确保当前页面处于已登录状态。
    如果发现跳到了登录页，就自动登录。
    """
    page.wait_for_timeout(2000)

    if is_login_page(page):
        do_login(page, context, verbose=verbose)
    else:
        if verbose:
            print("当前已登录，无需重新登录")