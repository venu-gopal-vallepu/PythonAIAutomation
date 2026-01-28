import re
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pytest
from selenium import webdriver
from utilities.ai_engine import AIAutomationFramework

# --- Global State ---
test_results = {}


# --- Pytest Configuration & Options ---
def pytest_addoption(parser):
    """Adds the --generate flag to your pytest command."""
    parser.addoption(
        "--generate",
        action="store_true",
        help="Run AI discovery for tagged steps"
    )


# --- Fixtures ---
@pytest.fixture()
def setup(request):
    """Initializes the Chrome WebDriver."""
    driver = webdriver.Chrome()
    driver.maximize_window()
    yield {'driver': driver}
    driver.quit()


@pytest.fixture(scope="function")
def ai_utility(driver):
    """Fixture to provide the AI utility to hooks or tests."""
    return AIAutomationFramework(driver)


# --- Hooks: Test Reporting & Interception ---
def pytest_runtest_makereport(item, call):
    """Captures test results and durations for reporting."""
    if call.when == 'call':
        # Extract test case ID from the test name (e.g., test_login__123)
        pattern = re.compile(r"__(\d+)$")
        match = pattern.search(item.name)

        if match:
            test_case_id = match.group(1)
            outcome = 'Fail' if call.excinfo is not None else 'Pass'

            test_results[test_case_id] = {
                'outcome': outcome,
                'duration': call.stop - call.start
            }


def pytest_bdd_before_step(request, feature, scenario, step, step_func):
    """The Interceptor: Wakes up the AI before a BDD step starts."""
    if request.config.getoption("--generate") and "ai_generate" in step.tags:
        print(f"\n🚀 [AI INTERCEPTOR] Analyzing Step: {step.name}")

        # Access the live driver from the setup fixture
        driver_fixture = request.getfixturevalue("setup")
        driver = driver_fixture['driver'] if isinstance(driver_fixture, dict) else driver_fixture

        # Initialize AI and run Composite Discovery
        ai_engine = AIAutomationFramework(driver)
        generated_code = ai_engine.discover_composite_logic(step.name)

        print("\n" + "=" * 40)
        print("PROPOSED PAGE OBJECT METHOD:")
        print(generated_code)
        print("=" * 40 + "\n")


# --- Session Finish: Report Generation & Email ---
def pytest_sessionfinish(session, exitstatus):
    """Generates HTML report and sends it via email at the end of the run."""
    print("\nTest Results:")
    for test_id, res in test_results.items():
        print(f"ID: {test_id}, Outcome: {res['outcome']}, Duration: {res['duration']:.2f}s")

    # Generate HTML Table Rows
    table_rows = []
    for test_id, res in test_results.items():
        color = "red" if res['outcome'] == "Fail" else "blue"
        row = (
            f"<tr>"
            f"<td>{test_id}</td>"
            f"<td style='color: {color}'><b>{res['outcome']}</b></td>"
            f"<td>{res['duration']:.2f} seconds</td>"
            f"</tr>"
        )
        table_rows.append(row)

    html_content = f"""
    <html>
    <head>
        <style>
            table {{ width: 100%; border-collapse: collapse; font-family: sans-serif; }}
            th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
            tr:nth-child(even) {{ background-color: #fafafa; }}
        </style>
    </head>
    <body>
        <h2>Test Execution Summary</h2>
        <table>
            <tr><th>Test Case ID</th><th>Outcome</th><th>Duration</th></tr>
            {''.join(table_rows)}
        </table>
    </body>
    </html>
    """

    # Email Configuration
    sender = "xxx"
    receiver = "xxx"
    app_password = "xxx"  # Note: Use environment variables for security!

    msg = MIMEMultipart()
    msg['From'] = sender
    msg['To'] = receiver
    msg['Subject'] = "Automated Test Report"
    msg.attach(MIMEText(html_content, 'html'))

    # Retry Logic for Sending Email
    for attempt in range(3):
        try:
            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(sender, app_password)
                server.send_message(msg)
            print("✅ Email report sent successfully.")
            break
        except Exception as e:
            print(f"⚠️ Attempt {attempt + 1} failed: {e}")
            if attempt < 2:
                time.sleep(5)
            else:
                print("❌ Final: Failed to send email report.")