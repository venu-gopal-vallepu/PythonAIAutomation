import requests
import os
import re


class SparkAssist:
    def __init__(self):
        # Configuration - Use environment variables for security
        self.api_url = os.getenv("SPARK_API_URL", "https://your-spark-instance.ai/v1/chat")
        self.api_key = os.getenv("SPARK_API_KEY", "your_api_key_here")

    def _extract_interface_summary(self, source_code):
        """
        Extracts method names and parameters from BasePage to guide Spark.
        """
        if not source_code:
            return "Available: click_element(loc), enter_text(loc, text), select_list_value_from_dropdown(loc, text)"

        pattern = r'def\s+([a-zA-Z_]\w*\(.*?\)):(?:\s+"""(.*?)""")?'
        matches = re.findall(pattern, source_code, re.DOTALL)

        summary = "AVAILABLE BASEPAGE METHODS (Use these signatures):\n"
        for sig, doc in matches:
            if not sig.startswith("__"):
                summary += f"• {sig}\n"
        return summary

    def generate_page_object(self, payload):
        base_source = payload.get('base_page_source', '')
        mappings = payload.get('mappings', [])
        scenario = payload.get('scenario', 'GeneratedPage').replace(" ", "")
        is_append = payload.get('is_append', False)

        interface_map = self._extract_interface_summary(base_source)

        # --- REFINED INSTRUCTIONS FOR LOCATORS & SIGNATURES ---
        system_instruction = (
            "You are a Senior Automation Architect. Generate clean, PEP8 compliant Python code.\n\n"
            f"{interface_map}\n"
            "STRICT CODE STRUCTURE RULES:\n"
            "1. INHERITANCE: Class must inherit from 'BasePage'.\n"
            "2. IMPORTS: Use 'from feature.page.base_page import BasePage' and 'from selenium.webdriver.common.by import By'.\n"
            "3. LOCATOR FORMAT: All locators MUST be private class-level tuples at the top of the class.\n"
            "   Example: _username_txt = (By.ID, 'user-id')\n"
            "4. METHOD NAMING: Use descriptive snake_case names based on the 'intent' field.\n"
            "5. SIGNATURE MATCHING:\n"
            "   - For 'wait_and_type' actions, use your BasePage method that accepts (locator, text).\n"
            "   - For 'wait_and_select' on React/Div elements, use your custom dropdown method: select_list_value_from_dropdown(loc, text).\n"
            "6. CLEANLINESS: Return ONLY the raw Python code. No conversation, no markdown, no backticks, no text explanations."
        )

        user_content = f"""
        TASK: Generate Page Object for '{scenario}'
        IS_APPEND: {is_append} (If True, omit class definition and imports)

        UI METADATA (Discovery Engine Results):
        {mappings}

        DATA HANDLING:
        - If test_data is <parameter>, treat as a method argument.
        - If test_data is "hardcoded", use the string directly in the method call.
        """

        try:
            print(f"--- 📡 Generating Page Object for: {scenario} ---")

            response = requests.post(
                self.api_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": "spark-pro-v2",
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": user_content}
                    ],
                    "temperature": 0.1
                },
                timeout=60
            )

            response.raise_for_status()
            result_code = response.json()['choices'][0]['message']['content']

            # Ensure any accidental AI-generated markdown is removed
            return re.sub(r'```python|```', '', result_code).strip()

        except Exception as e:
            return f"# ❌ Error in Spark Generation: {str(e)}"