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

        # 2. UPDATED System Instruction for Dynamic Parameterization
        system_instruction = (
            "ROLE: Senior Automation Architect.\n"
            "STRICT RULES FOR DYNAMIC DATA (EXAMPLES TABLE):\n"
            "1. NO HARDCODED VALUES: If an element has 'template_xpath', use it with .format(value=param).\n"
            "2. METHOD SIGNATURES:\n"
            "   - If 'is_data_input' is True OR 'template_xpath' exists, the method MUST accept a parameter (e.g., 'text' or 'value').\n"
            "   - Example: def select_role(self, role_name): self.click(self.role_template.format(value=role_name))\n"
            "3. COMPONENT LOGIC:\n"
            "   - DROPDOWN: Use 'template_xpath' to click the specific item revealed by the trigger.\n"
            "   - TEXTBOX: Use the static 'xpath' but accept 'text' as a method parameter.\n"
            "   - TOGGLE: Generate code to check .is_selected() before clicking to ensure it matches desired state.\n"
            "4. CLASS STRUCTURE: Inherit from BasePage. If is_append is True, only return new methods.\n"
            "5. BASE_PAGE CONTEXT: Use methods found in the provided BASE_PAGE_METHODS (e.g., self.click_element, self.type_text).\n"
            "OUTPUT: ONLY raw Python code. No markdown, no explanations."
        )

        # 3. Comprehensive User Content (Sending full base source for context)
        user_content = (
            f"SCENARIO_NAME: {scenario_name}\n"
            f"USER_PROMPT: {ai_prompt}\n"
            f"METADATA_FROM_AI_ENGINE: {mappings}\n"
            f"IS_APPEND: {is_append}\n"
            f"BASE_PAGE_FULL_CONTEXT:\n{base_source}" # Sending full source so Spark sees all method names
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
                    "temperature": 0.1 # Keep it deterministic
                },
                timeout=60
            )
            response.raise_for_status()
            raw_code = response.json()['choices'][0]['message']['content']
            return re.sub(r'```python|```', '', raw_code).strip()
        except Exception as e:
            return f"# ❌ Spark Error: {str(e)}"