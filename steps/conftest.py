import os
import pytest
import re
import json
import time
from selenium import webdriver
from utilities.ai_engine import AIAutomationFramework
from utilities.spark_assist import SparkAssist

# --- Global State for De-duplication ---
test_results = {}
processed_scenarios = set()


# --- Pytest Configuration ---
def pytest_addoption(parser):
    parser.addoption("--generate", action="store_true", help="Run AI discovery for tagged steps")
    parser.addoption("--page-file", action="store", default=None,
                     help="Target file name in feature/page/ to append or create")


# --- Fixtures ---

@pytest.fixture(scope="session")
def ai_engine():
    """
    🚀 P2 PERSISTENCE:
    Initialized once per session to keep SpaCy NLP model in memory.
    Handles the 'ai_ui_memory.json' for Self-Healing.
    """
    # We pass None for driver initially; it gets injected per-test
    return AIAutomationFramework(driver=None)


@pytest.fixture()
def setup(request, ai_engine):
    """
    🔧 BROWSER SETUP:
    Injects the active driver into the AI Engine for real-time healing.
    """
    driver = webdriver.Chrome()
    driver.maximize_window()

    # 🛰️ P2 Injection: Tell the AI Engine which browser to 'watch'
    ai_engine.driver = driver

    yield {'driver': driver}
    driver.quit()


@pytest.fixture(scope="function")
def ai_context():
    """State manager for discovered metadata during --generate runs."""
    return {"prompt": "", "buffer": {}, "scenario_name": ""}


# --- Hooks: BDD Orchestration ---

@pytest.hookimpl
def pytest_bdd_before_scenario(request, feature, scenario):
    ai_ctx = request.getfixturevalue("ai_context")
    if "ai_prompt" in scenario.tags:
        ai_ctx["scenario_name"] = scenario.name
        try:
            with open(feature.filename, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            scenario_idx = next((i for i, line in enumerate(lines) if
                                 f"Scenario: {scenario.name}" in line or f"Scenario Outline: {scenario.name}" in line),
                                -1)
            if scenario_idx != -1:
                prompt_lines = []
                for j in range(scenario_idx - 1, -1, -1):
                    curr = lines[j].strip()
                    if "@ai_prompt" in curr: break
                    clean_line = curr.lstrip('#').strip()
                    if clean_line: prompt_lines.insert(0, clean_line)
                ai_ctx["prompt"] = " ".join(prompt_lines)
        except Exception as e:
            print(f"⚠️ Error reading feature metadata: {e}")


@pytest.hookimpl
def pytest_bdd_before_step(request, feature, scenario, step):
    """
    🚀 MASTER ARCHITECT: Enhanced AI Discovery & Metadata Sync.
    Triggers during --generate to build the 'Memory' DNA for Spark.
    """
    if "[ai]" in step.name.lower() and request.config.getoption("--generate"):
        ai_ctx = request.getfixturevalue("ai_context")
        setup_data = request.getfixturevalue("setup")
        engine = request.getfixturevalue("ai_engine")

        # Sync driver again just in case
        engine.driver = setup_data['driver']

        try:
            # Extract RAW Gherkin to find placeholders
            scenario_def = next((s for s in feature.scenarios.values() if s.name in scenario.name), None)
            raw_step = next(s for s in scenario_def.steps if s.line_number == step.line_number)
            raw_text = raw_step.name
        except Exception:
            raw_text = step.name

        print(f"\n🤖 [AI Discovery]: Scanning UI for Intent: '{raw_text}'")

        # 🎯 Use the Engine to find Metadata
        metadata_list = engine.get_step_metadata(raw_text)

        if metadata_list:
            for meta in metadata_list:
                intent_key = meta['intent'].lower().replace(" ", "_").strip(":")

                # Sync metadata for Spark POM generation
                ai_ctx["buffer"][intent_key] = {
                    "intent": meta['intent'],
                    "component_type": meta['component_type'],
                    "xpath": meta['xpath'],
                    "tag": meta.get('tag'),
                    "class": meta.get('class'),
                    "is_parameterized": True if any(x in raw_text for x in ["{", "<", "'", '"']) else False
                }
            print(f"✅ AI Context Synced: {len(metadata_list)} items captured.")


@pytest.hookimpl
def pytest_bdd_after_scenario(request, feature, scenario):
    """
    ✨ SPARK ASSIST: Generates the POM file based on captured AI metadata.
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

        base_source = ""
        try:
            with open("utilities/base_page.py", "r", encoding='utf-8') as bf:
                base_source = bf.read()
        except Exception:
            pass

        payload = {
            "prompt": ai_ctx.get("prompt"),
            "scenario": scenario.name,
            "mappings": list(ai_ctx["buffer"].values()),
            "base_page_source": base_source,
            "is_append": is_append
        }

        try:
            spark = SparkAssist()
            generated_code = spark.generate_page_object(payload)

            mode = "a" if is_append else "w"
            with open(file_path, mode, encoding='utf-8') as f:
                if is_append:
                    f.write(f"\n\n    # --- Actions for: {scenario.name} ---\n")
                    indented = "\n".join([f"    {l}" if l.strip() else l for l in generated_code.splitlines()])
                    f.write(indented)
                else:
                    f.write(generated_code)

            print(f"✅ Success: Page Object logic written to {file_path}")
            processed_scenarios.add(scenario.name)
        except Exception as e:
            print(f"❌ Spark Error: {e}")
        finally:
            ai_ctx["buffer"] = {}


# --- Reporting Hooks ---
@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when == 'call':
        test_results[item.name] = {'outcome': report.outcome, 'duration': report.duration}


def pytest_sessionfinish(session, exitstatus):
    print("\n--- 🏁 AI Session Finished ---")
