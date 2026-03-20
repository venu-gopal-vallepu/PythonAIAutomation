import os
import re
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.relative_locator import locate_with
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from thefuzz import fuzz


class AIAutomationFramework:
    def __init__(self, driver, timeout=10):
        self.driver = driver
        self.timeout = timeout
        # STRATEGIC WEIGHTS: Prioritizes technical IDs over generic text
        self.WEIGHTS = {
            'id': 1.0, 'name': 0.9, 'aria-label': 1.0,
            'placeholder': 0.9, 'role': 0.8, 'text': 0.7
        }
        self._nlp = None

    def _get_nlp(self):
        if self._nlp is None:
            import spacy
            try:
                self._nlp = spacy.load("en_core_web_md")
            except OSError:
                os.system("python -m spacy download en_core_web_md")
                self._nlp = spacy.load("en_core_web_md")
        return self._nlp

    def clean_for_nlp(self, text):
        """Processes 'txtUserName' into 'txt user name' for AI understanding."""
        if not text: return ""
        text = re.sub(r'(?<!^)(?=[A-Z])', ' ', str(text))  # CamelCase split
        text = text.replace('_', ' ').replace('-', ' ')  # Symbol split
        return re.sub(r'[^a-zA-Z\s]', '', text).lower().strip()

    def _get_deep_elements(self):
        """Scans DOM and Shadow DOM for all interactive candidates."""
        return self.driver.execute_script("""
            const foundElements = [];
            function findRecursive(root) {
                const items = root.querySelectorAll('input, button, a, select, textarea, [role], [onclick], .btn, .link');
                items.forEach(el => {
                    const s = window.getComputedStyle(el);
                    if (el.offsetWidth > 0 && el.offsetHeight > 0 && s.display !== 'none' && s.visibility !== 'hidden') {
                        foundElements.push({
                            'tag': el.tagName.toLowerCase(), 
                            'id': el.id || "", 
                            'name': el.name || "",
                            'placeholder': el.placeholder || "", 
                            'text': el.innerText.trim() || "",
                            'aria': el.getAttribute('aria-label') || el.getAttribute('title') || "",
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
        """Finds, scrolls to, and returns a unique visible element."""
        try:
            wait = WebDriverWait(self.driver, self.timeout)
            by_type = getattr(By, strategy.upper())
            element = wait.until(EC.element_to_be_clickable((by_type, value)))
            # Ensure it's in view
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            return element if len(self.driver.find_elements(by_type, value)) == 1 else None
        except:
            return None

    def _find_locator_weighted(self, intent):
        """Hybrid Scoring: (Weighted Fuzzy) * (NLP Similarity + 0.1)"""
        nlp = self._get_nlp()
        elements = self._get_deep_elements()
        clean_intent = self.clean_for_nlp(intent)
        user_doc = nlp(clean_intent)

        matches = []
        for el in elements:
            max_fuzzy_weighted = 0
            for attr, weight in self.WEIGHTS.items():
                lookup_key = 'aria' if attr == 'aria-label' else attr
                val = el.get(lookup_key, "")
                if val:
                    score = fuzz.partial_ratio(clean_intent, self.clean_for_nlp(str(val)))
                    weighted_score = score * weight
                    if weighted_score > max_fuzzy_weighted: max_fuzzy_weighted = weighted_score

            full_context = self.clean_for_nlp(f"{el['id']} {el['name']} {el['text']}")
            target_doc = nlp(full_context)
            sim = max(0.0, user_doc.similarity(
                target_doc)) if user_doc.vector_norm > 0 and target_doc.vector_norm > 0 else 0.0

            total_score = max_fuzzy_weighted * (sim + 0.1)
            matches.append({"total": total_score, "element": el})

        matches.sort(key=lambda x: x['total'], reverse=True)

        for match in matches[:3]:
            el = match['element']
            candidates = [{"strategy": "id", "value": el['id']}, {"strategy": "name", "value": el['name']}]
            if el['placeholder']: candidates.append(
                {"strategy": "css_selector", "value": f"[placeholder='{el['placeholder']}']"})

            for cand in candidates:
                if not cand['value']: continue
                element = self._safe_find_unique(cand['strategy'], cand['value'])
                if element: return element, cand

        return None, None

    def perform_actions(self, step_metadata):
        """
        THE EXECUTIONER: Automatically performs the discovered actions.
        This closes the loop between 'finding' and 'doing'.
        """
        for meta in step_metadata:
            element, locator = self._find_locator_weighted(meta['intent'])
            if not element:
                raise Exception(f"❌ AI could not find element for: {meta['intent']}")

            action = meta['action']
            data = meta.get('test_data')

            if action == "wait_and_type":
                element.clear()
                element.send_keys(data)
                print(f"✅ Typed '{data}' into {meta['intent']}")

            elif action == "wait_and_click":
                element.click()
                print(f"✅ Clicked {meta['intent']}")

            elif action == "wait_and_select":
                select = Select(element)
                select.select_by_visible_text(data)
                print(f"✅ Selected '{data}' from {meta['intent']}")

    def get_step_metadata(self, step_text):
        """Processes Gherkin text to find params and intent."""
        clean_text = step_text.replace("[ai]", "").strip()
        results, visual_audit_list = [], []

        param_pattern = r"<(.*?)>|\{(.*?)\}|[\"'](.*?)[\"']"
        found_matches = re.findall(param_pattern, clean_text)

        for m in found_matches:
            intent = next((item for item in m if item), None)
            if not intent: continue
            raw_marker = f"<{m[0]}>" if m[0] else f"{{{m[1]}}}" if m[1] else f"\"{m[2]}\""

            element_obj, locator_data = self._find_locator_weighted(intent)
            if locator_data:
                if element_obj: visual_audit_list.append({'element': element_obj, 'label': intent})
                results.append({
                    "intent": intent, "action": "wait_and_type",
                    "locator": locator_data, "test_data": raw_marker
                })

        if not results:  # Fallback for clicks
            click_match = re.search(r"(?:click|press|tap)\s+(?:on\s+)?(?:the\s+)?(\w+)", clean_text, re.IGNORECASE)
            if click_match:
                intent = click_match.group(1)
                element_obj, locator_data = self._find_locator_weighted(intent)
                if locator_data:
                    if element_obj: visual_audit_list.append({'element': element_obj, 'label': intent})
                    results.append(
                        {"intent": intent, "action": "wait_and_click", "locator": locator_data, "test_data": None})

        return results