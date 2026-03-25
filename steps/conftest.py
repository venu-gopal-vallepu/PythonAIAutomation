import os, pytest, re, json, time
from selenium import webdriver
from utilities.ai_engine import AIAutomationFramework
from utilities.spark_assist import SparkAssist

processed_scenarios = set()


def pytest_addoption(parser):
    parser.addoption("--generate", action="store_true")
    parser.addoption("--page-file", action="store", default=None)


@pytest.fixture(scope="session")
def ai_engine(): return AIAutomationFramework(driver=None)


@pytest.fixture()
def setup(request, ai_engine):
    driver = webdriver.Chrome()
    driver.maximize_window()
    feature_name = request.node.fspath.purebasename
    ai_engine.driver = driver
    ai_engine.set_context(feature_name)
    yield {'driver': driver, 'feature_name': feature_name}
    driver.quit()


@pytest.fixture(scope="function")
def ai_context(): return {"prompt": "", "buffer": {}}


@pytest.hookimpl
def pytest_bdd_before_scenario(request, feature, scenario):
    ai_ctx = request.getfixturevalue("ai_context")
    if "ai_prompt" in scenario.tags:
        try:
            with open(os.path.abspath(feature.filename), 'r', encoding='utf-8') as f:
                lines = f.readlines()
            idx = next(i for i, l in enumerate(lines) if f"Scenario: {scenario.name}" in l)
            prompts = []
            for j in range(idx - 1, -1, -1):
                if "@ai_prompt" in lines[j]: continue
                if lines[j].strip().startswith("#"):
                    prompts.insert(0, lines[j].lstrip('#').strip())
                else:
                    break
            ai_ctx["prompt"] = " ".join(prompts)
        except:
            pass


@pytest.hookimpl
def pytest_bdd_before_step(request, feature, scenario, step):
    """
    🚀 MASTER ARCHITECT: Enhanced AI Discovery & Metadata Sync.
    Extracts RAW Gherkin to find placeholders (<param> or {param}).
    """
    if "[ai]" in step.name.lower() and request.config.getoption("--generate"):
        ai_ctx = request.getfixturevalue("ai_context")
        setup_data = request.getfixturevalue("setup")
        engine = request.getfixturevalue("ai_engine")

        # Sync driver to the current browser state
        engine.driver = setup_data['driver']

        # --- 🔍 RAW DATA TEXT EXTRACTION ---
        try:
            # Find the actual scenario definition in the feature object
            scenario_def = next((s for s in feature.scenarios.values() if s.name == scenario.name), None)
            # Find the specific step by matching the line number
            raw_step = next(s for s in scenario_def.steps if s.line_number == step.line_number)
            raw_text = raw_step.name  # This is the "Raw Data Text" (e.g., "Enter {user}")
        except Exception:
            raw_text = step.name  # Fallback to the executed text if lookup fails

        print(f"\n🤖 [AI Discovery]: Intent: '{raw_text}'")

        # 🎯 Resolve metadata
        metadata_list = engine.get_step_metadata(raw_text, page_context=setup_data['feature_name'])

        if metadata_list:
            for meta in metadata_list:
                intent_key = meta['intent'].lower().replace(" ", "_").strip(":")

                # 🧬 SYNC DNA: We pass 'is_parameterized' so Spark knows to add an argument
                ai_ctx["buffer"][intent_key] = {
                    "intent": meta['intent'],
                    "component_type": meta['component_type'],
                    "xpath": meta['xpath'],
                    "tag": meta.get('tag'),
                    "class": meta.get('class'),
                    "is_parameterized": True if any(x in raw_text for x in ["{", "<", "'", '"']) else False
                }
            print(f"✅ AI Context Synced for Page: {setup_data['feature_name']}")


@pytest.hookimpl
def pytest_bdd_after_scenario(request, feature, scenario):
    """
    ✨ SPARK ASSIST: Smart POM Generation with Context & BasePage Injection.
    Combines Namespace logic with Source-Code Style Guide.
    """
    ai_ctx = request.getfixturevalue("ai_context")
    setup_data = request.getfixturevalue("setup")

    # 🎯 GATEKEEPER: Only run if --generate is on and we have captured metadata
    should_run = (
            request.config.getoption("--generate") and
            ai_ctx.get("buffer") and
            scenario.name not in processed_scenarios
    )

    if should_run:
        # 📂 FOLDER LOGIC: Target feature/page/
        target_file = request.config.getoption("--page-file")
        output_dir = "feature/page"
        os.makedirs(output_dir, exist_ok=True)

        # Use --page-file if provided, else default to feature_name_page.py
        file_name = target_file if target_file else f"{setup_data['feature_name']}_page.py"
        file_path = os.path.join(output_dir, file_name)
        is_append = os.path.exists(file_path)

        # 📖 STYLE GUIDE: Read BasePage so Spark knows the parent class methods
        base_source = ""
        try:
            with open("utilities/base_page.py", "r", encoding='utf-8') as bf:
                base_source = bf.read()
        except Exception:
            pass

        # 📦 THE COMPLETE PAYLOAD: Everything Spark needs to be "brilliant"
        payload = {
            "page_name": setup_data['feature_name'],
            "scenario": scenario.name,
            "mappings": list(ai_ctx["buffer"].values()),
            "base_page_source": base_source,  # Gives AI the 'Smart Action' signature
            "is_append": is_append,
            "prompt": ai_ctx.get("prompt")  # Your # comments from Gherkin
        }

        try:
            spark = SparkAssist()
            generated_code = spark.generate_page_object(payload)

            if is_append:
                # 🛠️ SMART APPEND: Ensure methods are properly indented under the class
                with open(file_path, "a", encoding='utf-8') as f:
                    f.write(f"\n\n    # --- Actions for Scenario: {scenario.name} ---\n")
                    # Indent 4 spaces to keep Python class structure valid
                    indented_code = "\n".join([f"    {line}" if line.strip() else line
                                               for line in generated_code.splitlines()])
                    f.write(indented_code)
            else:
                # 🆕 NEW FILE: Write full class with imports
                with open(file_path, "w", encoding='utf-8') as f:
                    f.write(generated_code)

            print(f"✅ Success: Spark logic written to {file_path}")
            processed_scenarios.add(scenario.name)

        except Exception as e:
            print(f"❌ Spark Error: {e}")
        finally:
            # 🧹 CLEANUP: Clear buffer for the next scenario in the session
            ai_ctx["buffer"] = {}
