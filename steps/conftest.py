import os
import pytest
import re
from selenium import webdriver
from utilities.ai_engine import AIAutomationFramework
from utilities.spark_assist import SparkAssist

# --- Global State for De-duplication ---
# Prevents Scenario Outlines from generating code for every row in the Examples table
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
    """Standard Selenium Setup."""
    # Note: You can add ChromeOptions here for headless mode in CI/CD
    driver = webdriver.Chrome()
    driver.maximize_window()
    yield {'driver': driver}
    driver.quit()

@pytest.fixture(scope="session")
def ai_engine():
    """Persistent AI Engine to keep Spacy NLP model loaded in memory."""
    return AIAutomationFramework(None)

@pytest.fixture(scope="function")
def ai_context():
    """State manager for the current scenario's AI prompts and discovered metadata."""
    return {"prompt": "", "buffer": {}, "scenario_name": ""}

# --- Hooks: BDD Orchestration ---

@pytest.hookimpl
def pytest_bdd_before_scenario(request, feature, scenario):
    """
    Reads the feature file to extract the multi-line # prompt block
    located between the @ai_prompt tag and the Scenario header.
    """
    ai_ctx = request.getfixturevalue("ai_context")
    if "ai_prompt" in scenario.tags:
        ai_ctx["scenario_name"] = scenario.name
        try:
            with open(feature.filename, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # Locate the Scenario line (Handles both Scenario and Scenario Outline)
            scenario_idx = -1
            for i, line in enumerate(lines):
                if f"Scenario: {scenario.name}" in line or f"Scenario Outline: {scenario.name}" in line:
                    scenario_idx = i
                    break

            if scenario_idx != -1:
                prompt_lines = []
                for j in range(scenario_idx - 1, -1, -1):
                    curr = lines[j].strip()
                    if "@ai_prompt" in curr:
                        break
                    clean_line = curr.lstrip('#').strip()
                    if clean_line:
                        prompt_lines.insert(0, clean_line)

                ai_ctx["prompt"] = " ".join(prompt_lines)
                print(f"\nℹ️ AI Prompt matched: {ai_ctx['prompt']}")
        except Exception as e:
            print(f"⚠️ Error reading feature metadata: {e}")

@pytest.hookimpl
def pytest_bdd_after_step(request, feature, scenario, step, step_func):
    """
    Captures the RAW template (e.g., <Regions>) so the AI searches
    for the label 'Regions' instead of the runtime data value.
    """
    if "[ai]" in step.name.lower() and request.config.getoption("--generate"):
        ai_ctx = request.getfixturevalue("ai_context")
        setup_data = request.getfixturevalue("setup")
        engine = request.getfixturevalue("ai_engine")
        engine.driver = setup_data['driver']

        # UPDATED: Robust lookup to handle Scenario Outlines
        try:
            # We find the scenario definition where the name matches OR is a substring (for Outlines)
            scenario_def = next((s for s in feature.scenarios.values() if s.name in scenario.name), None)
            raw_step = next(s for s in scenario_def.steps if s.line_number == step.line_number)
            raw_text = raw_step.name
        except Exception:
            raw_text = step.name

        print(f"--- 🔍 AI Discovery (Semantic): {raw_text} ---")
        metadata_list = engine.get_step_metadata(raw_text)

        if metadata_list:
            for meta in metadata_list:
                # Cache by Intent (e.g., 'Regions', 'Sex') to avoid duplicates
                ai_ctx["buffer"][meta['intent']] = meta
            print(f"✔ [AI] Cached Semantic Locators: {list(ai_ctx['buffer'].keys())}")

@pytest.hookimpl
def pytest_bdd_after_scenario(request, feature, scenario):
    """
    Collects the buffer and triggers Spark Assist to generate the Page Object code.
    """
    ai_ctx = request.getfixturevalue("ai_context")

    # Only run if --generate is on, tag is present, buffer isn't empty, and we haven't done this scenario yet
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

        # BasePage context for Spark to match method signatures
        base_source = ""
        try:
            with open("utilities/base_page.py", "r", encoding='utf-8') as bf:
                base_source = bf.read()
        except:
            pass

        # UPDATED: Payload keys matched to SparkAssist expectations
        payload = {
            "prompt": ai_ctx.get("prompt"), # Changed from 'instruction' to 'prompt'
            "scenario": scenario.name,
            "mappings": list(ai_ctx["buffer"].values()),
            "base_page_source": base_source,
            "is_append": is_append
        }

        try:
            spark = SparkAssist()
            generated_code = spark.generate_page_object(payload)

            if is_append:
                header = f"\n\n    # --- Actions for: {scenario.name} ---\n"
                # Preserve 4-space indentation for class methods
                indented = "\n".join([f"    {l}" if l.strip() else l for l in generated_code.splitlines()])
                content = header + indented
                mode = "a"
            else:
                content = generated_code
                mode = "w"

            with open(file_path, mode, encoding='utf-8') as f:
                f.write(content)

            print(f"✅ Success: Page Object logic written to {file_path}")
            processed_scenarios.add(scenario.name)
        except Exception as e:
            print(f"❌ Spark Error: {e}")
        finally:
            ai_ctx["buffer"] = {} # Flush buffer for the next scenario

# --- Reporting Hooks ---
@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when == 'call':
        test_results[item.name] = {'outcome': report.outcome, 'duration': report.duration}

def pytest_sessionfinish(session, exitstatus):
    print("\n--- 🚀 AI Generation Session Finished ---")