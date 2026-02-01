import requests
import os
import re


class SparkAssist:
    def __init__(self):
        # Configuration - Use environment variables for security
        self.api_url = os.getenv("SPARK_API_URL", "https://your-spark-instance.ai/v1/chat")
        self.api_key = os.getenv("SPARK_API_KEY", "your_api_key_here")
        # Ensure this path is correct relative to your project root
        self.base_page_path = "feature/page/base_page.py"

    def _get_base_page_signatures(self):
        """
        Scans the local BasePage.py and extracts full method signatures
        to tell the AI exactly how to call your methods.
        """
        if os.path.exists(self.base_page_path):
            try:
                with open(self.base_page_path, 'r') as f:
                    content = f.read()
                    # Regex to capture the method name and its parameters
                    # e.g., 'enter_text(self, locator, text)'
                    signatures = re.findall(r'def\s+([a-zA-Z_]\w*\s*\(.*?\)):', content)

                    # Filter out internal methods and constructor
                    valid_signatures = [s for s in signatures if not s.startswith("_")]

                    if valid_signatures:
                        return f"The available methods in BasePage are: {', '.join(valid_signatures)}."
            except Exception as e:
                print(f"⚠️ Warning: Could not parse BasePage: {e}")

        # Robust Fallback if file is missing or unreadable
        return "The available methods in BasePage are: click_element(self, locator), enter_text(self, locator, text)."

    def generate_page_object(self, payload):
        """
        Orchestrates the context injection and calls Spark Assist to generate code.
        """
        # 1. Dynamically read the 'capabilities' of your BasePage
        local_context = self._get_base_page_signatures()

        # 2. Build the System Instruction (The Architect's Rules)
        system_instruction = (
            f"You are a Senior Automation Architect. {local_context} "
            "Your task is to generate a Python Page Object class based on UI mappings."
            "\n\nSTRICT INSTRUCTIONS:\n"
            "1. INHERITANCE: Inherit from 'BasePage'.\n"
            "2. IMPORT: Use 'from feature.page.base_page import BasePage' and 'from selenium.webdriver.common.by import By'.\n"
            "3. METHOD CALLS: Use the signatures provided above. If an action involves text input, use the method that accepts a 'text' argument.\n"
            "4. LOCATORS: Format all locators as Selenium Tuples: (By.ID, 'value'), (By.XPATH, 'value'), etc.\n"
            "5. OUTPUT: Return ONLY the raw Python code. No conversation, no markdown backticks."
        )

        # 3. Construct the Payload for the AI
        user_content = f"""
        ### GOAL
        {payload.get('instruction', 'Generate a Page Object.')}

        ### PAGE CLASS NAME
        {payload.get('scenario', 'GeneratedPage')}

        ### UI ELEMENT METADATA
        {payload.get('mappings', [])}
        """

        # 4. Execute the API Request
        try:
            print(f"--- 📡 Connecting to Spark Assist for: {payload.get('scenario')} ---")

            response = requests.post(
                self.api_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": "spark-pro-v2",
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": user_content}
                    ],
                    "temperature": 0.1  # Low creativity for high-precision code
                },
                timeout=60
            )

            response.raise_for_status()
            result_code = response.json()['choices'][0]['message']['content']

            # Final cleaning of the code block
            clean_code = re.sub(r'```python|```', '', result_code).strip()
            return clean_code

        except Exception as e:
            error_msg = f"# ❌ Error in Spark Generation: {str(e)}"
            print(error_msg)
            return error_msg