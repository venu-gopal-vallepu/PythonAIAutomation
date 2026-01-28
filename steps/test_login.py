from pytest_bdd import scenarios, given, when, then, parsers

# Load scenarios from the feature file
# The path is relative to the project root (where pytest is usually run)
scenarios('../features/login_features/login.feature')


@given('User is navigated to application')
def navigate_to_app():
    # TODO: Add driver.get("url") logic here
    pass


@when(parsers.parse('user enters username "{username}"'))
def enter_username(username):
    # TODO: Add logic to find username field and send_keys(username)
    print(f"Username entered: {username}")


@when(parsers.parse('user enters password "{password}"'))
def enter_password(password):
    # TODO: Add logic to find password field and send_keys(password)
    print(f"Password entered: {password}")


@when('user clicks on login button')
def click_login_button():
    # TODO: Add logic to click the login button
    pass


@then('Login should be successful')
def verify_login_success():
    # TODO: Add assertion logic (e.g., check URL or dashboard element)
    pass
