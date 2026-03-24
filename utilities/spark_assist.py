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

        # 🏛️ NEW ARCHITECT-LEVEL SYSTEM INSTRUCTIONS (P2 SELF-HEALING)
        system_instruction = (
            "ROLE: Senior Test Automation Architect.\n"
            "CONTEXT: Generating Python Page Object code using an AI-Powered BasePage.\n\n"
            "STRICT ARCHITECTURAL RULES:\n"
            "1. UNIFIED ACTION: Use ONLY 'self.smart_action(intent, value)' for ALL UI interactions.\n"
            "2. INTENT-BASED: The first argument of smart_action MUST be the exact 'intent' string from the mappings.\n"
            "3. NO HARDCODED LOCATORS: Do NOT generate XPaths, IDs, or CSS selectors in the methods. The AI Engine resolves these via the intent string.\n"
            "4. METHOD NAMING: Use snake_case based on the intent. (e.g., intent 'Permission Group' becomes def set_permission_group(self, value)).\n"
            "5. COMPONENT AGNOSTIC: Whether it is a DROPDOWN, TEXTBOX, or BUTTON, always use self.smart_action.\n"
            "   - If it's a click-only item (Button/Link), call self.smart_action(intent).\n"
            "   - If it involves data (Textbox/Dropdown), call self.smart_action(intent, value).\n"
            "6. BASE_PAGE CONTEXT: Inherit from BasePage. Ensure the constructor passes 'ai_engine' to super().__init__.\n"
            "7. OUTPUT: Return ONLY raw Python code. NO markdown (```), NO explanations, NO prose."
        )

        user_content = (
            f"--- CONFIGURATION ---\n"
            f"SCENARIO: {scenario_name}\n"
            f"UI MAPPINGS (INTENTS): {mappings}\n"
            f"STYLE GUIDE (BASE_PAGE): {base_source}\n"
            f"USER INSTRUCTIONS: {ai_prompt}"
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