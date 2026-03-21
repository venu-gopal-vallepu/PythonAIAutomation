import os
import pytest
import re
from selenium import webdriver
from utilities.ai_engine import AIAutomationFramework
from utilities.spark_assist import SparkAssist

# --- Global State Management ---
# Ensures we don't double-generate code for Scenario Outlines/Data-driven rows
processed_scenarios = set()


# --- Pytest Configuration ---
def pytest_addoption(parser):
    """Adds command-line flags for the AI Generator."""
    parser.addoption("--generate", action="store_true", help="Run AI discovery for tagged steps")
    parser.addoption("--page-file", action="store", default=None,
                     help="Target filename (e.g., login_page.py) to create or append")


# --- Fixtures ---
@pytest.fixture()
def setup(request):
    """Standard WebDriver initialization."""
    driver = webdriver.Chrome()
    driver.maximize_window()
    yield {'driver': driver}
    driver.quit()


@pytest.fixture(scope="session")
def ai_engine():
    """Persistent AI Engine: Keeps the Spacy NLP model in memory for the whole run."""
    return AIAutomationFramework(None)


@pytest.fixture(scope="function")
def ai_context():
    """Temporary storage for a single scenario's prompt and discovered locators."""
    return {"prompt": "", "buffer": {}, "scenario_name": ""}


# --- Hooks: BDD Orchestration ---

@pytest.hookimpl
def pytest_bdd_before_scenario(request, feature, scenario):
    """
    Extracts the # comment-based prompt block above the @ai_prompt tag.
    """
    ai_ctx = request.getfixturevalue("ai_context")
    if "ai_prompt" in scenario.tags:
        ai_ctx["scenario_name"] = scenario.name
        try:
            with open(feature.filename, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # Find where the scenario starts in the file
            idx = next((i for i, line in enumerate(lines)
                        if f"Scenario: {scenario.name}" in line
                        or f"Scenario Outline: {scenario.name}" in line), -1)

            if idx != -1:
                prompt_lines = []
                # Scan upwards from the scenario header to find the prompt
                for j in range(idx - 1, -1, -1):
                    line = lines[j].strip()
                    if "@ai_prompt" in line: break
                    clean = line.lstrip('#').strip()
                    if clean: prompt_lines.insert(0, clean)

                ai_ctx["prompt"] = " ".join(prompt_lines)
                print(f"\n[AI-PROMPT] Context Loaded: {ai_ctx['prompt']}")
        except Exception as e:
            print(f"⚠️ Error reading feature file prompt: {e}")


@pytest.hookimpl
def pytest_bdd_after_step(request, feature, scenario, step, step_func):
    """
    The Discovery Hook: Intercepts [ai] steps and scrapes React metadata.
    """
    if "[ai]" in step.name.lower() and request.config.getoption("--generate"):
        ai_ctx = request.getfixturevalue("ai_context")
        setup_data = request.getfixturevalue("setup")
        engine = request.getfixturevalue("ai_engine")

        engine.driver = setup_data['driver']

        # Get the raw Gherkin template (e.g. 'I enter <username>')
        try:
            raw_text = step.template if hasattr(step, 'template') else step.name
        except:
            raw_text = step.name

        print(f"--- 🔍 AI Scanning: {raw_text} ---")
        metadata_list = engine.get_step_metadata(raw_text)

        if metadata_list:
            # De-duplicate by 'intent' to keep the Page Object clean
            for meta in metadata_list:
                ai_ctx["buffer"][meta['intent']] = meta
            print(f"✔ [AI] Cached elements: {list(ai_ctx['buffer'].keys())}")


@pytest.hookimpl
def pytest_bdd_after_scenario(request, feature, scenario):
    """
    The Assembler: Sends the de-duplicated buffer to SparkAssist for POM generation.
    """
    ai_ctx = request.getfixturevalue("ai_context")

    # Validation: Should we trigger Spark?
    is_gen_mode = request.config.getoption("--generate")
    has_ai_tag = "ai_prompt" in scenario.tags
    is_new = scenario.name not in processed_scenarios

    if is_gen_mode and has_ai_tag and ai_ctx["buffer"] and is_new:
        output_dir = "feature/page"
        os.makedirs(output_dir, exist_ok=True)

        # File Naming Logic
        target_arg = request.config.getoption("--page-file")
        file_name = target_arg if target_arg else f"{scenario.name.replace(' ', '_').lower()}.py"
        file_path = os.path.join(output_dir, file_name)
        is_append = os.path.exists(file_path)

        # Provide BasePage context so Spark matches your method names
        base_source = ""
        try:
            with open("utilities/base_page.py", "r", encoding='utf-8') as bf:
                base_source = bf.read()
        except:
            pass

        spark = SparkAssist()
        generated_code = spark.generate_page_object({
            "scenario": scenario.name,
            "mappings": list(ai_ctx["buffer"].values()),
            "base_page_source": base_source,
            "is_append": is_append
        })

        try:
            if is_append:
                # Append with a header and proper Python indentation (4 spaces)
                header = f"\n\n    # --- Actions for: {scenario.name} ---\n"
                indented = "\n".join([f"    {l}" if l.strip() else l for l in generated_code.splitlines()])
                content = header + indented
            else:
                content = generated_code

            with open(file_path, "a" if is_append else "w", encoding='utf-8') as f:
                f.write(content)

            print(f"✅ PRODUCT-READY POM UPDATED: {file_path}")
            processed_scenarios.add(scenario.name)
        except Exception as e:
            print(f"❌ Write Error: {e}")
        finally:
            ai_ctx["buffer"] = {}  # Clear for the next scenario in the session


def pytest_sessionfinish(session, exitstatus):
    print("\n--- 🚀 AI Generation Session Complete ---")