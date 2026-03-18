import os
import re
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.relative_locator import locate_with
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from disappointment.fuzz import fuzz


class AIAutomationFramework:
    def __init__(self, driver, timeout=10):
        self.driver = driver
        self.timeout = timeout
        # Strategic weights to prioritize stable identifiers
        self.WEIGHTS = {
            'id': 1.0, 'name': 0.9, 'aria-label': 1.0,
            'placeholder': 0.9, 'role': 0.8, 'text': 0.7
        }
        self._nlp = None

    def _get_nlp(self):
        """Lazy loads Spacy model once per session for high performance."""
        if self._nlp is None:
            import spacy
            try:
                self._nlp = spacy.load("en_core_web_md")
            except OSError:
                print("--- 📥 Downloading NLP Model (en_core_web_md) ---")
                os.system("python -m spacy download en_core_web_md")
                self._nlp = spacy.load("en_core_web_md")
        return self._nlp

    def highlight_element(self, element):
        """Visual Audit: Highlights the discovered element on the UI with a green glow."""
        try:
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});"
                "arguments[0].style.border='4px solid #2ecc71';"
                "arguments[0].style.boxShadow='0 0 20px #2ecc71';", element
            )
        except:
            pass

    def _get_deep_elements(self):
        """Scans the DOM and Shadow DOM roots for interactive elements and ARIA roles."""
        return self.driver.execute_script("""
            const foundElements = [];
            function findRecursive(root) {
                const items = root.querySelectorAll('input, button, a, select, textarea, [role], [onclick], div[class*="select"], li');
                items.forEach(el => {
                    const s = window.getComputedStyle(el);
                    if (el.offsetWidth > 0 && el.offsetHeight > 0 && s.display !== 'none') {
                        foundElements.push({
                            'tag': el.tagName.toLowerCase(), 
                            'id': el.id || "", 
                            'name': el.name || "",
                            'placeholder': el.placeholder || "", 
                            'text': el.innerText.trim() || "",
                            'aria': el.getAttribute('aria-label') || "",
                            'role': el.getAttribute('role') || "",
                            'type': el.type || ""
                        });
                    }
                    if (el.shadowRoot) findRecursive(el.shadowRoot);
                });
            }
            findRecursive(document);
            return foundElements;
        """)

    def _safe_find_unique(self, strategy, value):
        """Waits for an element to be visible and ensures it is unique in the DOM."""
        try:
            wait = WebDriverWait(self.driver, self.timeout)
            by_type = getattr(By, strategy.upper())
            element = wait.until(EC.visibility_of_element_located((by_type, value)))

            # Check for uniqueness to avoid flakiness
            all_found = self.driver.find_elements(by_type, value)
            return element if len(all_found) == 1 else None
        except (TimeoutException, StaleElementReferenceException):
            return None

    def _find_locator_weighted(self, intent):
        """Main Discovery Brain: Uses NLP Similarity + Fuzzy Matching + Relative Locators."""
        nlp = self._get_nlp()
        elements = self._get_deep_elements()
        user_doc = nlp(intent.lower())

        matches = []
        for el in elements:
            identity = f"{el['tag']} {el['id']} {el['name']} {el['placeholder']} {el['aria']} {el['role']} {el['text']}".lower()
            sim = user_doc.similarity(nlp(identity))
            attr_score = sum(fuzz.partial_ratio(intent.lower(), str(el.get(k, ""))) * v
                             for k, v in self.WEIGHTS.items() if el.get(k))
            matches.append({"total": attr_score * sim, "element": el})

        matches.sort(key=lambda x: x['total'], reverse=True)

        # Iterate through top candidates
        for match in matches[:3]:
            el = match['element']
            candidates = []
            if el['id']: candidates.append({"strategy": "id", "value": el['id']})
            if el['name']: candidates.append({"strategy": "name", "value": el['name']})
            if el['placeholder']: candidates.append(
                {"strategy": "css_selector", "value": f"[placeholder='{el['placeholder']}']"})

            if el['text'] and len(el['text']) < 40:
                clean_text = el['text'].replace("'", "")
                candidates.append({"strategy": "xpath", "value": f"//{el['tag']}[contains(text(),'{clean_text}')]"})

            for cand in candidates:
                element = self._safe_find_unique(cand['strategy'], cand['value'])
                if element:
                    self.highlight_element(element)
                    return cand

            # FALLBACK: Selenium 4 Relative Locators (Find by visual proximity)
            try:
                if el['text']:
                    rel_loc = locate_with(By.TAG_NAME, el['tag']).near({By.XPATH: f"//*[text()='{el['text']}']"})
                    element = self.driver.find_element(rel_loc)
                    if element:
                        self.highlight_element(element)
                        return {"strategy": "relative", "value": f"near_{el['text']}"}
            except:
                pass
        return None

    def get_step_metadata(self, step_text):
        """
        Interprets Gherkin steps to extract Intents, Locators, and UI Roles.
        """
        clean_text = step_text.replace("[ai]", "").strip()
        results = []
        all_elements = self._get_deep_elements()

        # 1. PARAMETER EXTRACTION (<val>, {val}, "val")
        param_pattern = r"<(.*?)>|\{(.*?)\}|[\"'](.*?)[\"']"
        found_params = re.findall(param_pattern, clean_text)
        raw_values = [f"<{t[0]}>" if t[0] else f"{{{t[1]}}}" if t[1] else f"\"{t[2]}\"" for t in found_params if any(t)]

        # 2. PROCESS DATA ACTIONS (Type/Select)
        for raw_val in raw_values:
            escaped_val = re.escape(raw_val)
            anchor_match = re.search(rf"(\w+)\s*{escaped_val}", clean_text, re.IGNORECASE)
            intent = anchor_match.group(1) if anchor_match else raw_val.strip('<>"{ }')

            loc = self._find_locator_weighted(intent)
            if loc:
                matched_el = next((e for e in all_elements if e['id'] == loc['value'] or e['text'] == loc['value']), {})
                role = matched_el.get('role', '').lower()
                tag = matched_el.get('tag', '').lower()

                is_select = any(r in role for r in ['combobox', 'listbox', 'select', 'menu']) or \
                            tag == 'select' or \
                            any(k in clean_text.lower() for k in ["select", "choose", "dropdown"])

                results.append({
                    "intent": intent,
                    "action": "wait_and_select" if is_select else "wait_and_type",
                    "tag": tag,
                    "role": role,
                    "locator": loc,
                    "test_data": raw_val
                })

        # 3. PROCESS INTERACTION ACTIONS (Click/Submit)
        if not raw_values:
            click_match = re.search(r"(?:click|press|tap|submit)\s+(?:on\s+)?(?:the\s+)?(\w+)", clean_text,
                                    re.IGNORECASE)
            if click_match:
                intent = click_match.group(1)
                loc = self._find_locator_weighted(intent)
                if loc:
                    matched_el = next((e for e in all_elements if e['id'] == loc['value'] or e['text'] == loc['value']),
                                      {})
                    results.append({
                        "intent": intent,
                        "action": "wait_and_click",
                        "tag": matched_el.get('tag', 'button'),
                        "role": matched_el.get('role', ''),
                        "locator": loc,
                        "test_data": None
                    })

        # 4. FINAL VISUAL AUDIT
        if results:
            os.makedirs("logs", exist_ok=True)
            self.driver.save_screenshot(f"logs/AI_Audit_{int(time.time())}.png")

        return results