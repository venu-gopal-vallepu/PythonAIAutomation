import requests
import os
import re


class SparkAssist:
    def __init__(self):
        self.api_url = os.getenv("SPARK_API_URL", "https://your-spark-instance.ai/v1/chat")
        self.api_key = os.getenv("SPARK_API_KEY", "your_api_key_here")

    def generate_page_object(self, payload):
        scenario_raw = payload.get('scenario', 'GeneratedPage')
        scenario_name = re.sub(r'[^a-zA-Z0-9]', '', scenario_raw.title())
        mappings = payload.get('mappings', [])
        is_append = payload.get('is_append', False)
        ai_prompt = payload.get('prompt', 'No specific instructions provided.')
        base_source = payload.get('base_page_source', '')

        # 🏛️ ARCHITECT-LEVEL SYSTEM INSTRUCTIONS (UPDATED FOR SELF-HEALING)
        system_instruction = (
            "ROLE: Senior Test Automation Architect.\n"
            "CONTEXT: Generating Python Page Object code for Selenium/Pytest.\n\n"
            "STRICT ARCHITECTURAL RULES:\n"
            "1. SEMANTIC ANCHORING: Use 'template_xpath' as the primary locator.\n"
            "2. SELF-HEALING LOCATORS: If 'name' or 'placeholder' exist in mappings, incorporate them as fallbacks.\n"
            "   - Example: f\"//input[@name='{name}' or @placeholder='{placeholder}'] | {template_xpath}\"\n"
            "3. DYNAMIC METHODS: All methods MUST accept parameters if data is involved.\n"
            "   - Format: def set_{intent}(self, value): or def select_{intent}(self, option):\n"
            "4. DROPDOWN LOGIC: If component_type is 'DROPDOWN':\n"
            "   - Click the trigger using its locator, then click the list item via text: f\"//*[text()='{value}']\"\n"
            "5. BASE_PAGE CONTEXT: Inherit from BasePage. Use ONLY the wrapper methods found in the provided BASE_PAGE_SOURCE (e.g., self.do_click, self.enter_text).\n"
            "6. OUTPUT: Return ONLY raw Python code. NO markdown (```), NO explanations, NO prose."
        )

        user_content = (
            f"--- CONFIGURATION ---\n"
            f"SCENARIO: {scenario_name}\n"
            f"IS_APPEND: {is_append}\n"
            f"INSTRUCTIONS: {ai_prompt}\n\n"
            f"--- UI METADATA (MAPPINGS) ---\n"
            f"{mappings}\n\n"
            f"--- BASE_PAGE_SOURCE (STYLE GUIDE) ---\n"
            f"{base_source}"
        )

        try:
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
            raw_code = response.json()['choices'][0]['message']['content']
            return re.sub(r'```python|```', '', raw_code).strip()
        except Exception as e:
            return f"# ❌ Spark Assist Error: {str(e)}"
