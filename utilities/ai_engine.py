import os
import re
import time
import spacy
from selenium.webdriver.common.by import By
from thefuzz import fuzz

# --- NLP INITIALIZATION ---
try:
    nlp = spacy.load("en_core_web_md")
except OSError:
    os.system("python -m spacy download en_core_web_md")
    nlp = spacy.load("en_core_web_md")


class AIAutomationFramework:
    def __init__(self, driver):
        self.driver = driver
        self.WEIGHTS = {'id': 1.0, 'name': 0.9, 'aria-label': 0.9, 'placeholder': 0.8, 'text': 0.7}

    def _extract_all_data(self, user_step):
        return re.findall(r"['\"](.*?)['\"]", user_step)

    def _get_deep_elements(self):
        """Pierces Shadow DOM and maps actionable elements."""
        return self.driver.execute_script("""
            const foundElements = [];
            function findRecursive(root) {
                const items = root.querySelectorAll('input, button, a, select, textarea, [role="button"]');
                items.forEach(el => {
                    const s = window.getComputedStyle(el);
                    if (el.offsetWidth > 0 && el.offsetHeight > 0 && s.display !== 'none') {
                        let r = el.getBoundingClientRect();
                        foundElements.push({
                            'tag': el.tagName.toLowerCase(), 'id': el.id, 'name': el.name,
                            'placeholder': el.placeholder || "", 'text': el.innerText || "",
                            'canAcceptInput': ['input', 'textarea'].includes(el.tagName.toLowerCase()) || el.contentEditable === 'true',
                            'isClickable': ['button', 'a'].includes(el.tagName.toLowerCase()) || el.getAttribute('role') === 'button' || s.cursor === 'pointer'
                        });
                    }
                    if (el.shadowRoot) findRecursive(el.shadowRoot);
                });
            }
            findRecursive(document);
            return foundElements;
        """)

    def _find_locator_weighted(self, user_step):
        user_step_lower = user_step.lower()
        intent = "input" if any(x in user_step_lower for x in ['enter', 'type', 'fill', 'set']) else "action"
        elements = self._get_deep_elements()
        user_doc = nlp(user_step_lower)
        matches = []

        for el in elements:
            if intent == "input" and not el.get('canAcceptInput'): continue
            if intent == "action" and not el.get('isClickable'): continue
            identity = f"{el['tag']} {el['id']} {el['name']} {el['placeholder']} {el['text']}".lower()
            sim = user_doc.similarity(nlp(identity))
            attr = sum(fuzz.partial_ratio(user_step_lower, str(el.get(k, ""))) * v for k, v in self.WEIGHTS.items() if
                       el.get(k))
            matches.append({"total": attr * sim, "element": el})

        matches.sort(key=lambda x: x['total'], reverse=True)
        if matches:
            el = matches[0]['element']
            if el['id']: return {"strategy": "id", "value": el['id']}
            if el['name']: return {"strategy": "name", "value": el['name']}
            return {"strategy": "xpath", "value": f"//{el['tag']}[contains(normalize-space(.),'{el['text'][:15]}')]"}
        return None

    def generate_pom(self, feature_file, page_name, output_dir="features/pages", use_base_page=True):
        """Generates a clean, action-based POM library with inheritance support."""
        # 1. Parse BDD Feature
        with open(feature_file, 'r') as f:
            content = f.read()
        steps = re.findall(r"(?:Given|When|Then|And|But)\s+([^<>\n]+(?:<[^>]+>[^<>\n]*)*)", content)

        unique_methods = {}
        discovered_locators = []

        # 2. Extract Reusable Actions
        for step in steps:
            # Create a clean method name (e.g., enter_username)
            clean_text = re.sub(r"['\"].*?['\"]", "", step).lower()
            clean_text = re.sub(r"<(.*?)>", "", clean_text)
            words = [w for w in clean_text.split() if w not in ['user', 'is', 'on', 'the', 'should', 'be', 'to']]
            method_name = "_".join(words[:2])  # Simplified naming convention

            if method_name and method_name not in unique_methods:
                loc = self._find_locator_weighted(step)
                if loc:
                    is_input = any(x in step.lower() for x in ['enter', 'type', 'fill', 'set', '<', '"'])
                    unique_methods[method_name] = {
                        "loc": loc,
                        "args": "self, value" if is_input else "self",
                        "action": "send_keys(value)" if is_input else "click()"
                    }
                    discovered_locators.append(loc)

        # 3. Write Code with Inheritance
        code = []
        if use_base_page:
            code.append("from features.pages.base_page import BasePage\n")
            code.append(f"class {page_name}(BasePage):")
        else:
            code.append(
                "from selenium.webdriver.common.by import By\nfrom selenium.webdriver.support.ui import WebDriverWait\nfrom selenium.webdriver.support import expected_conditions as EC\n")
            code.append(f"class {page_name}:")
            code.append("    def __init__(self, driver):")
            code.append("        self.driver = driver")
            code.append("        self.wait = WebDriverWait(driver, 10)\n")

        for name, info in unique_methods.items():
            code.append(f"    def {name}({info['args']}):")
            code.append(f"        # Locator mapped via Weighted AI: {info['loc']['value']}")
            target = f"(By.{info['loc']['strategy'].upper()}, '{info['loc']['value']}')"
            code.append(f"        self.wait.until(EC.element_to_be_clickable({target})).{info['action']}\n")

        # --- FINAL BATCH HIGHLIGHT & SCREENSHOT ---
        for loc in discovered_locators:
            try:
                by_type = getattr(By, loc['strategy'].upper())
                el = self.driver.find_element(by_type, loc['value'])
                self.driver.execute_script(
                    "arguments[0].style.border='3px solid #2ecc71'; arguments[0].style.boxShadow='0 0 15px #2ecc71';",
                    el)
            except:
                continue

        timestamp = time.strftime("%Y%m%d-%H%M%S")
        os.makedirs(output_dir, exist_ok=True)
        self.driver.save_screenshot(os.path.join(output_dir, f"{page_name}_map_{timestamp}.png"))

        with open(f"{output_dir}/{page_name.lower()}.py", "w") as f:
            f.write("\n".join(code))
