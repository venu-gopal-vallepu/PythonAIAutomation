import requests
import os
import re

class SparkAssist:
    def __init__(self):
        # Ensure these environment variables are set or replaced with your actual endpoint
        self.api_url = os.getenv("SPARK_API_URL", "https://your-spark-instance.ai/v1/chat")
        self.api_key = os.getenv("SPARK_API_KEY", "your_api_key_here")

    def generate_page_object(self, payload):
        # 1. Extract data from payload (mapped to conftest keys)
        scenario_raw = payload.get('scenario', 'GeneratedPage')
        scenario_name = re.sub(r'[^a-zA-Z0-9]', '', scenario_raw.title())
        mappings = payload.get('mappings', [])
        is_append = payload.get('is_append', False)
        ai_prompt = payload.get('prompt', 'No specific instructions provided.')
        base_source = payload.get('base_page_source', '')

        # 2. Refined System Instruction
        system_instruction = (
            "ROLE: Senior Automation Architect.\n"
            "CONTEXT: React application (No data-testids). Generating Page Object methods.\n"
            "STRICT RULES:\n"
            "1. LOCATORS: Use the provided 'xpath' (Relative/Semantic) or 'aria'.\n"
            "2. CLASS STRUCTURE: If is_append is False, create a class matching the SCENARIO name inheriting from BasePage.\n"
            "3. METHOD MAPPING:\n"
            "   - DROPDOWN -> self.select_list_value_from_dropdown(LOCATOR, text)\n"
            "   - TEXTBOX -> self.type_text(LOCATOR, text)\n"
            "   - BUTTON/TOGGLE -> self.click_element(LOCATOR)\n"
            "4. REASONING: Follow the USER PROMPT for specific interaction logic.\n"
            "5. OUTPUT: Return ONLY raw Python code. No markdown, no explanations."
        )

        # 3. Comprehensive User Content
        user_content = (
            f"SCENARIO_NAME: {scenario_name}\n"
            f"USER_PROMPT: {ai_prompt}\n"
            f"METADATA: {mappings}\n"
            f"IS_APPEND: {is_append}\n"
            f"BASE_PAGE_METHODS: {base_source[:500]}..." # Give Spark a hint of method names
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
            # Clean up potential markdown wrappers
            raw_code = response.json()['choices'][0]['message']['content']
            return re.sub(r'```python|```', '', raw_code).strip()
        except Exception as e:
            return f"# ❌ Spark Error: {str(e)}"