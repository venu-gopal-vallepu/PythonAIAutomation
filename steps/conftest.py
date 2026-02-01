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
    parser.addoption("--page-file", action="store", default=None,
                     help="Target file name in feature/page/ to append or create")


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
    Finalizes the AI Code Generation flow.
    Handles 'Smart Append' vs 'New File' and ensures correct Python indentation.
    """
    ai_context = request.getfixturevalue("ai_context")

    # Check if scenario is tagged for generation and we have captured UI metadata
    if "ai_prompt" in scenario.tags and ai_context.get("buffer"):
        target_file = request.config.getoption("--page-file")
        output_dir = "feature/page"
        os.makedirs(output_dir, exist_ok=True)

        # 1. Determine target file path and mode
        file_path = None
        is_append = False

        if target_file:
            file_path = os.path.join(output_dir, target_file)
            is_append = os.path.exists(file_path)
        else:
            # Default: sanitize scenario name for filename (e.g. "User Login" -> "user_login.py")
            clean_name = scenario.name.replace(' ', '_').replace('-', '_').lower()
            file_path = os.path.join(output_dir, f"{clean_name}.py")

        # 2. Adjust instruction for Spark Assist
        instruction = ai_context.get("prompt", "Generate Page Object")
        if is_append:
            instruction += (
                " (STRICT: This is an APPEND. Do not include imports or class header. "
                "Provide ONLY class-level locators and methods.)"
            )

        payload = {
            "instruction": instruction,
            "scenario": scenario.name,
            "mappings": ai_context["buffer"],
            "format_preference": "LOCATORS_AT_TOP"  # Tells Spark to use btn_ / txt_ variables
        }

        try:
            spark = SparkAssist()
            generated_code = spark.generate_page_object(payload)

            # 3. Handle Indentation for Appends
            # If appending, we must indent the AI's code by 4 spaces to stay inside the class
            if is_append:
                final_output = "\n".join([f"    {line}" if line.strip() else line
                                          for line in generated_code.splitlines()])
                mode = "a"
                header = f"\n\n    # --- Methods for Scenario: {scenario.name} ---\n"
            else:
                final_output = generated_code
                mode = "w"
                header = ""

            # 4. Write to disk
            with open(file_path, mode) as f:
                f.write(header + final_output)

            print(f"✅ Framework Path Maintained: Code {'appended to' if is_append else 'created in'} {file_path}")

            # 5. CRITICAL: Clear buffer so the next scenario starts with a clean slate
            ai_context["buffer"] = []

        except Exception as e:
            print(f"❌ Generation Error for scenario '{scenario.name}': {e}")


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
