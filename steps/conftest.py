import os
import pytest
import re
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from selenium import webdriver
from utilities.ai_engine import AIAutomationFramework
from utilities.spark_assist import SparkAssist

# --- Global State ---
test_results = {}


# --- Pytest Configuration & Options ---
def pytest_addoption(parser):
    parser.addoption("--generate", action="store_true", help="Run AI discovery for tagged steps")


# --- Fixtures ---
@pytest.fixture()
def setup(request):
    driver = webdriver.Chrome()
    driver.maximize_window()
    yield {'driver': driver}
    driver.quit()


@pytest.fixture(scope="function")
def ai_context():
    """State manager for the current scenario's AI data."""
    return {
        "prompt": "",
        "buffer": [],
        "scenario_name": ""
    }


# --- Hooks: BDD Orchestration ---


@pytest.hookimpl
def pytest_bdd_before_scenario(request, feature, scenario):
    """
    Extracts the # prompt from the feature file before scenario starts.
    Retrieves ai_context via request.getfixturevalue.
    """
    ai_context = request.getfixturevalue("ai_context")

    if "ai_prompt" in scenario.tags:
        ai_context["scenario_name"] = scenario.name
        try:
            with open(feature.filename, 'r') as f:
                content = f.read()
                # Matches the comment line directly above the @ai_prompt tag
                match = re.search(r'#(.*)\n\s*@ai_prompt', content)
                if match:
                    ai_context["prompt"] = match.group(1).strip()
                    print(f"ℹ️ Found AI Prompt: {ai_context['prompt']}")
        except Exception as e:
            print(f"⚠️ Error reading feature metadata: {e}")


@pytest.hookimpl
def pytest_bdd_after_step(request, feature, scenario, step, step_func):
    """
    Intercepts [AI] steps and buffers locator metadata.
    Uses request.getfixturevalue to access shared state.
    """
    # Check if --generate flag is used and if the step is an AI step
    if request.config.getoption("--generate") and "[ai]" in step.name.lower():
        ai_context = request.getfixturevalue("ai_context")

        # Unpack driver from your setup fixture
        setup_data = request.getfixturevalue("setup")
        driver = setup_data['driver']

        # Initialize Engine and Discover Metadata
        ai_engine = AIAutomationFramework(driver)
        print(f"--- 🔍 AI Discovery: {step.name} ---")
        step_metadata = ai_engine.get_step_metadata(step.name)

        if step_metadata:
            # Add results to the shared buffer
            ai_context["buffer"].extend(step_metadata)
            print(f"✔ [AI] Cached {len(step_metadata)} elements for: {step.name}")


@pytest.hookimpl
def pytest_bdd_after_scenario(request, feature, scenario):
    """
    Sends buffered data to Spark Assist for final Page Object generation.
    """
    ai_context = request.getfixturevalue("ai_context")

    # Only trigger if the scenario is tagged and we actually captured UI data
    if "ai_prompt" in scenario.tags and ai_context["buffer"]:
        print(f"\n--- ⚡ Spark Assist: Generating Page Object for '{scenario.name}' ---")

        payload = {
            "instruction": ai_context["prompt"] or "Generate a standard Page Object",
            "scenario": ai_context["scenario_name"],
            "mappings": ai_context["buffer"]
        }

        try:
            # Use the SparkAssist utility we updated with the signature scanner
            spark = SparkAssist()
            generated_code = spark.generate_page_object(payload)

            # Define output directory and file path
            output_dir = "generated_pages"
            os.makedirs(output_dir, exist_ok=True)

            # Sanitize file name
            clean_name = scenario.name.replace(' ', '_').replace('-', '_').lower()
            file_path = os.path.join(output_dir, f"{clean_name}.py")

            with open(file_path, "w") as f:
                f.write(generated_code)

            print(f"✅ SUCCESS: Page Object saved to {file_path}")

        except Exception as e:
            print(f"❌ Spark Assist Call Failed: {e}")


# --- Reporting Hooks (Existing Logic) ---

def pytest_runtest_makereport(item, call):
    if call.when == 'call':
        pattern = re.compile(r"__(\d+)$")
        match = pattern.search(item.name)
        if match:
            test_case_id = match.group(1)
            test_results[test_case_id] = {
                'outcome': 'Fail' if call.excinfo is not None else 'Pass',
                'duration': call.stop - call.start
            }


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
