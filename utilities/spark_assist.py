import requests
import os
import re


class SparkAssist:
    def __init__(self):
        # Ensure these are set in your environment variables
        self.api_url = os.getenv("SPARK_API_URL", "https://your-spark-instance.ai/v1/chat")
        self.api_key = os.getenv("SPARK_API_KEY", "your_api_key_here")

    def generate_page_object(self, payload):
        scenario_raw = payload.get('scenario', 'GeneratedPage')
        scenario_name = re.sub(r'[^a-zA-Z0-9]', '', scenario_raw.title())
        mappings = payload.get('mappings', [])
        is_append = payload.get('is_append', False)
        ai_prompt = payload.get('prompt', 'No specific instructions provided.')
        base_source = payload.get('base_page_source', '')
        # 🟢 Extract the page name for namespacing
        page_name = payload.get('page_name', 'common')

        # 🏛️ SYSTEM INSTRUCTIONS: Updated to ensure the AI uses the REAL page_name
        system_instruction = (
            "ROLE: Senior Test Automation Architect.\n"
            "CONTEXT: Generating Python Page Object code using an AI-Powered BasePage.\n\n"
            "STRICT ARCHITECTURAL RULES:\n"
            f"1. UNIFIED ACTION: Use 'self.smart_action(intent, value, page_name=\"{page_name}\")' for UI interactions.\n"
            f"2. NAMESPACING: You MUST use the page_name \"{page_name}\" for every smart_action call.\n"
            "3. INTENT-BASED: The first argument of smart_action MUST be the exact 'intent' string from the mappings.\n"
            "4. NO HARDCODED LOCATORS: Do NOT generate XPaths or IDs. The AI resolves these via the intent string.\n"
            "5. METHOD NAMING: Use snake_case. If 'is_parameterized' is True, the method MUST accept a 'value' argument.\n"
            "6. COMPONENT AGNOSTIC: Use self.smart_action for everything.\n"
            f"   - Click: self.smart_action(intent, page_name=\"{page_name}\")\n"
            f"   - Input: self.smart_action(intent, value, page_name=\"{page_name}\")\n"
            "7. BASE_PAGE CONTEXT: Inherit from BasePage. Pass 'ai_engine' to super().__init__.\n"
            "8. OUTPUT: Return ONLY raw Python code. NO markdown, NO explanations."
        )

        user_content = (
            f"--- CONFIGURATION ---\n"
            f"TARGET PAGE NAMESPACE: {page_name}\n"
            f"SCENARIO: {scenario_name}\n"
            f"UI MAPPINGS (INTENTS + META): {mappings}\n"
            f"USER INSTRUCTIONS FROM FEATURE FILE: {ai_prompt}"
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

            # Clean up any accidental markdown the AI might return
            clean_code = re.sub(r'```python|```', '', raw_code).strip()
            return clean_code

        except Exception as e:
            return f"# ❌ Spark Assist Error: {str(e)}"