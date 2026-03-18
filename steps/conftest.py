import os
import pytest
import re
from selenium import webdriver
from utilities.ai_engine import AIAutomationFramework
from utilities.spark_assist import SparkAssist

# --- Global State for De-duplication ---
# Ensures Scenario Outlines only call the AI once per scenario name
test_results = {}
processed_scenarios = set()


# --- Pytest Configuration ---
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
    return {"prompt": "", "buffer": [], "scenario_name": ""}


# --- Hooks: BDD Orchestration ---

@pytest.hookimpl
def pytest_bdd_before_scenario(request, feature, scenario):
    """
    Finds the multi-line prompt for the current scenario.
    Collects all text between @ai_prompt and the Scenario header,
    even if only the first line has a '#'.
    """
    ai_ctx = request.getfixturevalue("ai_context")
    if "ai_prompt" in scenario.tags:
        ai_ctx["scenario_name"] = scenario.name
        try:
            with open(feature.filename, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # 1. Locate the exact Scenario line index
            scenario_idx = -1
            for i, line in enumerate(lines):
                if f"Scenario: {scenario.name}" in line or f"Scenario Outline: {scenario.name}" in line:
                    scenario_idx = i
                    break

            if scenario_idx != -1:
                prompt_lines = []
                # 2. Search upwards to collect the multi-line prompt block
                for j in range(scenario_idx - 1, -1, -1):
                    curr = lines[j].strip()
                    # Stop if we hit the tag or another scenario
                    if "@ai_prompt" in curr:
                        break

                    # Clean leading hashes if they exist, otherwise grab raw text
                    clean_line = curr.lstrip('#').strip()
                    if clean_line:
                        prompt_lines.insert(0, clean_line)

                ai_ctx["prompt"] = " ".join(prompt_lines)
                print(f"\nℹ️ AI Prompt matched for [{scenario.name}]: {ai_ctx['prompt']}")
        except Exception as e:
            print(f"⚠️ Error reading feature metadata: {e}")


@pytest.hookimpl
def pytest_bdd_after_step(request, feature, scenario, step, step_func):
    """
    Intercepts the step and passes the RAW text (template) to the engine.
    This allows the engine to find multiple locators in a single string
    by identifying anchors near <parameters> or "quotes".
    """
    if request.config.getoption("--generate") and "[ai]" in step.name.lower():
        ai_ctx = request.getfixturevalue("ai_context")
        setup_data = request.getfixturevalue("setup")
        engine = request.getfixturevalue("ai_engine")

        engine.driver = setup_data['driver']

        # step.name contains the raw template (e.g., enters username <user>)
        print(f"--- 🔍 AI Discovery (Raw Step): {step.name} ---")

        step_metadata_list = engine.get_step_metadata(step.name)
        if step_metadata_list:
            ai_ctx["buffer"].extend(step_metadata_list)
            print(f"✔ [AI] Cached {len(step_metadata_list)} interaction(s).")


@pytest.hookimpl
def pytest_bdd_after_scenario(request, feature, scenario):
    """
    Sends the gathered metadata to Spark Assist to generate the Page Object.
    Uses the 'Duplicate Guard' to skip subsequent rows in Scenario Outlines.
    """
    ai_ctx = request.getfixturevalue("ai_context")

    should_run = (
            request.config.getoption("--generate") and
            "ai_prompt" in scenario.tags and
            ai_ctx.get("buffer") and
            scenario.name not in processed_scenarios
    )

    if should_run:
        target_file = request.config.getoption("--page-file")
        output_dir = "feature/page"
        os.makedirs(output_dir, exist_ok=True)

        clean_name = scenario.name.replace(' ', '_').replace('-', '_').lower()
        file_name = target_file if target_file else f"{clean_name}.py"
        file_path = os.path.join(output_dir, file_name)
        is_append = os.path.exists(file_path)

        # Extract BasePage source for context
        base_source = ""
        try:
            with open("utilities/base_page.py", "r", encoding='utf-8') as bf:
                base_source = bf.read()
        except:
            pass

        payload = {
            "instruction": ai_ctx.get("prompt"),
            "scenario": scenario.name,
            "mappings": ai_ctx["buffer"],
            "base_page_source": base_source,
            "is_append": is_append
        }

        try:
            spark = SparkAssist()
            generated_code = spark.generate_page_object(payload)

            if is_append:
                # Append mode: add header and indent code to stay within the class scope
                header = f"\n\n    # --- Actions for: {scenario.name} ---\n"
                indented = "\n".join([f"    {l}" if l.strip() else l for l in generated_code.splitlines()])
                content = header + indented
                mode = "a"
            else:
                content = generated_code
                mode = "w"

            with open(file_path, mode, encoding='utf-8') as f:
                f.write(content)

            print(f"✅ Success: Code written to {file_path}")
            processed_scenarios.add(scenario.name)  # Mark as done

        except Exception as e:
            print(f"❌ Spark Error: {e}")
        finally:
            ai_ctx["buffer"] = []


# --- Reporting Hooks ---
@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when == 'call':
        test_results[item.name] = {'outcome': report.outcome, 'duration': report.duration}


def pytest_sessionfinish(session, exitstatus):
    print("\n--- AI Generation Session Finished ---")