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

# --- Global State for Reporting ---
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


@pytest.fixture(scope="session")
def ai_engine():
    """Persistent AI Engine to keep SpaCy loaded in memory."""
    return AIAutomationFramework(None)


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
    ai_ctx = request.getfixturevalue("ai_context")
    if "ai_prompt" in scenario.tags:
        ai_ctx["scenario_name"] = scenario.name
        try:
            with open(feature.filename, 'r', encoding='utf-8') as f:
                content = f.read()
                match = re.search(r'#(.*)\n\s*@ai_prompt', content)
                if match:
                    ai_ctx["prompt"] = match.group(1).strip()
                    print(f"\nℹ️ AI Prompt Loaded: {ai_ctx['prompt']}")
        except Exception as e:
            print(f"⚠️ Error reading feature metadata: {e}")


@pytest.hookimpl
def pytest_bdd_after_step(request, feature, scenario, step, step_func):
    """Intercepts [AI] steps and extracts metadata from the RAW step text."""
    if request.config.getoption("--generate") and "[ai]" in step.name.lower():
        ai_ctx = request.getfixturevalue("ai_context")
        setup_data = request.getfixturevalue("setup")
        engine = request.getfixturevalue("ai_engine")

        engine.driver = setup_data['driver']

        # In Pytest-BDD, step.name is the best source for the raw template string
        print(f"--- 🔍 AI Discovery: {step.name} ---")
        step_metadata_list = engine.get_step_metadata(step.name)

        if step_metadata_list:
            ai_ctx["buffer"].extend(step_metadata_list)
            print(f"✔ [AI] Cached {len(step_metadata_list)} interactions.")


@pytest.hookimpl
def pytest_bdd_after_scenario(request, feature, scenario):
    ai_ctx = request.getfixturevalue("ai_context")

    if "ai_prompt" in scenario.tags and ai_ctx.get("buffer"):
        target_file = request.config.getoption("--page-file")
        output_dir = "feature/page"
        os.makedirs(output_dir, exist_ok=True)

        # File Determination Logic
        clean_name = scenario.name.replace(' ', '_').replace('-', '_').lower()
        file_name = target_file if target_file else f"{clean_name}.py"
        file_path = os.path.join(output_dir, file_name)
        is_append = os.path.exists(file_path)

        instruction = ai_ctx.get("prompt", "Generate Page Object methods")

        # --- MODIFICATION: Read BasePage Source ---
        base_source = ""
        try:
            # Update path to your actual base_page.py
            with open("utilities/base_page.py", "r", encoding='utf-8') as bf:
                base_source = bf.read()
        except Exception as e:
            print(f"⚠️ Warning: Could not read BasePage source: {e}")

        payload = {
            "instruction": instruction,
            "scenario": scenario.name,
            "mappings": ai_ctx["buffer"],
            "base_page_source": base_source,  # NEW: Provide the 'Library of Truth'
            "format_preference": "SELENIUM_POM",
            "is_append": is_append
        }

        try:
            spark = SparkAssist()
            generated_code = spark.generate_page_object(payload)

            if is_append:
                indented_code = "\n".join([f"    {line}" if line.strip() else line
                                           for line in generated_code.splitlines()])
                mode = "a"
                header = f"\n\n    # --- Actions for Scenario: {scenario.name} ---\n"
                content_to_write = header + indented_code
            else:
                mode = "w"
                content_to_write = generated_code

            with open(file_path, mode, encoding='utf-8') as f:
                f.write(content_to_write)

            print(f"✅ Code written to {file_path}")

        except Exception as e:
            print(f"❌ Spark Error: {e}")
        finally:
            # --- MODIFICATION: Always clear buffer after scenario attempt ---
            ai_ctx["buffer"] = []


# --- Existing Reporting Hooks ---
@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when == 'call':
        test_results[item.name] = {
            'outcome': report.outcome,
            'duration': report.duration
        }


def pytest_sessionfinish(session, exitstatus):
    # (Preserve your existing Email logic here)
    print("Test Session Finished.")