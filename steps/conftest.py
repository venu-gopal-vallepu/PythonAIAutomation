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
    ai_ctx, setup_data = request.getfixturevalue("ai_context"), request.getfixturevalue("setup")
    if request.config.getoption("--generate") and ai_ctx["buffer"] and scenario.name not in processed_scenarios:
        target = request.config.getoption("--page-file") or f"{setup_data['feature_name']}_page.py"
        path = os.path.join("feature/page", target)
        os.makedirs("feature/page", exist_ok=True)

        spark = SparkAssist()
        code = spark.generate_page_object({
            "page_name": setup_data['feature_name'], "scenario": scenario.name,
            "mappings": list(ai_ctx["buffer"].values()), "is_append": os.path.exists(path),
            "prompt": ai_ctx["prompt"]
        })
        with open(path, "a" if os.path.exists(path) else "w") as f: f.write(code)
        processed_scenarios.add(scenario.name)
