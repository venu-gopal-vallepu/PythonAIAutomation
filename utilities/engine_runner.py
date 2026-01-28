import time
from selenium import webdriver
from utilities.ai_engine import AIAutomationFramework


def run_accelerated_discovery():
    """Standalone mode to build Page Objects via hardcoded navigation."""
    driver = webdriver.Chrome()
    driver.maximize_window()

    try:
        # Step 1: Manual Navigation
        url = "https://opensource-demo.orangehrmlive.com/web/index.php/auth/login"
        print(f"--- 1. Navigating to {url} ---")
        driver.get(url)
        time.sleep(5)

        # Step 2: Define the BDD requirement
        # This example uses one hardcoded value and one placeholder
        bdd_step = 'user enters username "Admin" and password <user-password>'

        print(f"--- 2. Analyzing Requirement: {bdd_step} ---")
        ai = AIAutomationFramework(driver)

        # Step 3: Trigger Generation
        generated_code = ai.discover_composite_logic(bdd_step)

        print("\n✅ POM CODE GENERATED:")
        print("-" * 50)
        print(generated_code)
        print("-" * 50)
        print("\n💡 Elements are highlighted in GREEN in the browser.")
        time.sleep(10)

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        driver.quit()


if __name__ == "__main__":
    run_accelerated_discovery()
