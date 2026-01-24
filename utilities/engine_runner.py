import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service

from utilities.ai_engine import AIAutomationFramework


def run_ai_discovery():
    """
    Enterprise Accelerator Runner:
    - Sets up a clean automation session.
    - Bridges the BDD Feature with the Framework Page Objects.
    - Generates Inherited, Action-Based Page Objects.
    """
    # 1. Browser Configuration
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])

    driver = webdriver.Chrome()

    try:
        # 2. Navigate to Application Under Test (AUT)
        target_url = "https://opensource-demo.orangehrmlive.com/web/index.php/auth/login"
        print(f"--- Step 1: Navigating to {target_url} ---")
        driver.get(target_url)

        # 3. Stability Buffer
        # Wait for the DOM to be fully 'Actionable'
        time.sleep(5)

        # 4. Initialize AI Discovery Utility
        utility = AIAutomationFramework(driver)

        # 5. Project Path Orchestration
        # Using relative paths so the project works on any machine/environment
        base_dir = os.getcwd()
        feature_file = os.path.join(base_dir, "features", "login_features", "login.feature")
        page_name = "LoginPage"
        output_dir = os.path.join(base_dir, "features", "pages")

        print(f"--- Step 2: Analyzing Feature File ---")
        print(f"Target: {os.path.basename(feature_file)}")

        # 6. Generate Inherited POM
        # 'use_base_page=True' ensures it connects to your framework's BasePage
        utility.generate_pom(
            feature_file,
            page_name,
            output_dir=output_dir,
            use_base_page=True
        )

        print(f"\n✅ REUSABLE LIBRARY CREATED: {page_name}.py")
        print(f"✅ VISUAL AUDIT MAP SAVED in: {output_dir}")

    except Exception as e:
        print(f"\n❌ DISCOVERY FAILED: {str(e)}")

    finally:
        # Final pause to inspect the 'Green Highlights' on the browser
        print("--- Discovery Complete. Closing session in 3 seconds... ---")
        time.sleep(3)
        driver.quit()


if __name__ == "__main__":
    run_ai_discovery()
