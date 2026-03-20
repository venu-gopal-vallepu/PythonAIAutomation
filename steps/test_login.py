import pytest
from pytest_bdd import scenario, given, when, then, parsers

# 1. Bind to the specific Scenario Outline
@scenario(
    'C:/venu/AutomatiotionLearnings/PythonAIAutomation/features/login_features/login.feature',
    'Verify login details'
)
def test_login_outline_debug():
    """Entry point for debugging the Scenario Outline."""
    pass

# --- STEP DEFINITIONS ---

@given('User is navigated to application')
def navigate_to_app(setup):
    driver = setup['driver']
    driver.get("https://opensource-demo.orangehrmlive.com/web/index.php/auth/login")

# 2. Updated Parser to handle [ai] prefix and two parameters
@when(parsers.cfparse('[ai] user enters {username}, {password}'))
def enter_credentials(setup, username, password):
    """
    This matches: When [ai] user enters <username>, <password>
    Parameters from the Examples table are injected here.
    """
    print(f"DEBUG: AI Discovery for User: {username} and Pass: {password}")
    # Note: username and password will be strings from your Examples table

@when('user clicks on login button')
def click_login_button():
    print("DEBUG: Clicking login button")

@then('Login should be successful')
def verify_login_success(setup):
    print(f"DEBUG: Current URL is {setup['driver'].current_url}")