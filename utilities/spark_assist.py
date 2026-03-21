import requests
import os
import re


class SparkAssist:
    def __init__(self):
        # ORG STANDARD: Use Environment Variables. Never hardcode keys in a product.
        self.api_url = os.getenv("SPARK_API_URL", "https://your-spark-instance.ai/v1/chat")
        self.api_key = os.getenv("SPARK_API_KEY", "your_api_key_here")

    def generate_page_object(self, payload):
        """
        The Architect: Translates AI metadata into clean, PEP8 Page Objects.
        """
        scenario = payload.get('scenario', 'GeneratedPage').replace(" ", "")
        mappings = payload.get('mappings', [])
        is_append = payload.get('is_append', False)

        # TOUGH MENTOR RULE: We tell Spark exactly what to do with the React metadata.
        system_instruction = (
            "ROLE: Senior Automation Architect.\n"
            "TASK: Generate Python Page Object code for a React application.\n"
            "STRICT LOCATOR HIERARCHY:\n"
            "1. Priority 1: [data-testid='value'] (CSS_SELECTOR)\n"
            "2. Priority 2: [aria-label='value'] (CSS_SELECTOR)\n"
            "3. Priority 3: Semantic XPath (e.g., //button[text()='Submit'])\n"
            "4. FORBIDDEN: Never use dynamic IDs (mui-*, :r*, id-*) or absolute XPaths.\n\n"
            "METHOD INTERFACE MAPPING:\n"
            "- If component_type is 'DROPDOWN' -> use self.select_list_value_from_dropdown(locator, text)\n"
            "- If component_type is 'TEXTBOX' -> use self.type_text(locator, text)\n"
            "- If component_type is 'BUTTON' or 'TOGGLE' -> use self.click_element(locator)\n\n"
            "STRUCTURE:\n"
            "- Inherit from 'BasePage'.\n"
            "- Store locators as private class-level tuples (e.g., _login_btn = (By.ID, '...')).\n"
            "- Return ONLY raw Python code. No markdown, no backticks."
        )

        user_content = f"""
        SCENARIO: {scenario}
        UI METADATA: {mappings}
        APPEND_MODE: {is_append} (If True, DO NOT write imports or class definition. Write ONLY methods.)
        """

        try:
            print(f"--- 📡 Spark: Architecting Page Object for {scenario} ---")
            response = requests.post(
                self.api_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": "spark-pro-v2",
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": user_content}
                    ],
                    "temperature": 0.1  # Low temperature = high consistency
                },
                timeout=60
            )
            response.raise_for_status()

            # Clean up any accidental AI formatting
            raw_code = response.json()['choices'][0]['message']['content']
            clean_code = re.sub(r'```python|```', '', raw_code).strip()

            return clean_code

        except Exception as e:
            return f"# ❌ SparkAssist Error: {str(e)}"

    def format_for_append(self, code):
        """
        Ensures the generated methods are correctly indented for an existing class.
        """
        lines = code.splitlines()
        # Indent every line by 4 spaces to fit inside the 'class' block
        return "\n".join([f"    {line}" if line.strip() else line for line in lines])
