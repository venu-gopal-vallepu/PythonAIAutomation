import time
import os
from selenium import webdriver
from utilities.ai_engine import AIAutomationFramework
from utilities.engine_runner import SparkAssistRunner


def run_accelerated_discovery():
    """
    Standalone mode: Captures UI locators and uses Spark Assist
    to generate a complete Page Object class.
    """
    # Initialize driver
    driver = webdriver.Chrome()
    driver.maximize_window()

    # Initialize our AI components
    ai_engine = AIAutomationFramework(driver)
    spark_runner = SparkAssistRunner()

    try:
        # Step 1: Manual Navigation
        url = "https://opensource-demo.orangehrmlive.com/web/index.php/auth/login"
        print(f"--- 1. Navigating to {url} ---")
        driver.get(url)
        time.sleep(5)

        # Step 2: Define the BDD requirement and the Prompt
        # In standalone mode, we manually define the # prompt you'd usually have in the feature file
        system_prompt = "Please provide methods with observed locators to login to the OrangeHRM application"
        bdd_steps = [
            '[ai] user click on testaccount button',
            '[ai] user enters username "Admin"',
            '[ai] user enters password "admin123"',
            '[ai] clicks on login button'
        ]

        print(f"--- 2. Analyzing {len(bdd_steps)} steps and discovering locators ---")

        all_mappings = []
        for step in bdd_steps:
            print(f"Discovering: {step}")
            # get_step_metadata returns a list of dictionaries for each element found
            metadata = ai_engine.get_step_metadata(step)
            if metadata:
                all_mappings.extend(metadata)
            time.sleep(1)  # Brief pause for visual highlight audit

        # Step 3: Send consolidated data to Spark Assist
        print(f"--- 3. Connecting to Spark Assist for final code generation ---")

        payload = {
            "instruction": system_prompt,
            "scenario": "OrangeHRM Login",
            "mappings": all_mappings
        }

        generated_code = spark_runner.generate_page_object(payload)

        # Step 4: Save and Print
        file_path = spark_runner.save_code(generated_code, "OrangeHRM_Login")

        print("\n" + "🚀" * 10 + " POM CODE GENERATED " + "🚀" * 10)
        print(f"Saved to: {file_path}")
        print("-" * 60)
        print(generated_code)
        print("-" * 60)

        print("\n💡 Check the 'logs' folder for visual audit screenshots.")
        time.sleep(5)

    except Exception as e:
        print(f"❌ Error during discovery: {e}")
    finally:
        driver.quit()


if __name__ == "__main__":
    run_accelerated_discovery()