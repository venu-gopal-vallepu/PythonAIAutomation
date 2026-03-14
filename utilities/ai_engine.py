import os
import re
import time
from selenium.webdriver.common.by import By
from thefuzz import fuzz


class AIAutomationFramework:
    def __init__(self, driver):
        self.driver = driver
        # Refined weights for modern web apps
        self.WEIGHTS = {
            'id': 1.0,
            'name': 0.9,
            'aria-label': 1.0,
            'placeholder': 0.9,
            'role': 0.8,
            'text': 0.7
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

    def highlight_element(self, loc):
        """Visual Audit: Highlights the discovered element on the UI."""
        try:
            by_type = getattr(By, loc['strategy'].upper())
            element = self.driver.find_element(by_type, loc['value'])
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});"
                "arguments[0].style.border='4px solid #2ecc71';"
                "arguments[0].style.boxShadow='0 0 20px #2ecc71';", element
            )
        except:
            pass

    def _get_deep_elements(self):
        """Scans the DOM and Shadow DOM roots for interactive elements."""
        return self.driver.execute_script("""
            const foundElements = [];
            function findRecursive(root) {
                // Selector includes roles and onclick for modern JS framework coverage
                const items = root.querySelectorAll('input, button, a, select, textarea, [role], [onclick], div[class*="select"]');
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

    def _is_unique(self, locator):
        """Validates that a locator points to exactly one element to prevent flakiness."""
        try:
            by_type = getattr(By, locator['strategy'].upper())
            return len(self.driver.find_elements(by_type, locator['value'])) == 1
        except:
            return False

    def _find_locator_weighted(self, context_text):
        """Main Discovery Brain: Uses NLP Similarity + Fuzzy Matching."""
        nlp = self._get_nlp()
        elements = self._get_deep_elements()
        user_doc = nlp(context_text.lower())

        matches = []
        for el in elements:
            # Identity string for NLP semantic comparison
            identity = f"{el['tag']} {el['id']} {el['name']} {el['placeholder']} {el['aria']} {el['role']} {el['text']}".lower()
            sim = user_doc.similarity(nlp(identity))

            # Fuzzy scoring for specific attributes
            attr_score = sum(fuzz.partial_ratio(context_text.lower(), str(el.get(k, ""))) * v
                             for k, v in self.WEIGHTS.items() if el.get(k))

            matches.append({"total": attr_score * sim, "element": el})

        # Sort by highest confidence score
        matches.sort(key=lambda x: x['total'], reverse=True)

        # Iterate through top candidates to find a stable, unique locator
        for match in matches[:5]:
            el = match['element']
            candidates = []
            if el['id']: candidates.append({"strategy": "id", "value": el['id']})
            if el['name']: candidates.append({"strategy": "name", "value": el['name']})
            if el['placeholder']: candidates.append(
                {"strategy": "css_selector", "value": f"[placeholder='{el['placeholder']}']"})

            # Smart XPath for text-heavy elements
            if el['text'] and len(el['text']) < 50:
                clean_text = el['text'].replace("'", "")
                candidates.append({"strategy": "xpath", "value": f"//{el['tag']}[contains(text(),'{clean_text}')]"})

            for cand in candidates:
                if self._is_unique(cand):
                    return cand
        return None

    def get_step_metadata(self, step_text):
        """
        Interprets Gherkin steps to extract Intents, Locators, and BasePage Signatures.
        """
        if "[ai]" not in step_text.lower():
            return []

        clean_text = step_text.replace("[ai]", "").strip()
        results = []

        # 1. PARAMETER EXTRACTION (Handles <>, {}, and "")
        param_pattern = r"<(.*?)>|\{(.*?)\}|[\"'](.*?)[\"']"
        found_params = re.findall(param_pattern, clean_text)
        params = [p for tup in found_params for p in tup if p]

        # 2. PROCESS INPUT/TYPE ACTIONS
        for p in params:
            # Find the anchor word before the parameter for NLP intent
            anchor_pattern = rf"(\w+)\s*(?:<|>|{{|}}|\"|'){re.escape(p)}"
            match = re.search(anchor_pattern, clean_text, re.IGNORECASE)
            intent = match.group(1) if match else p

            loc = self._find_locator_weighted(intent)
            if loc:
                matched_el = next((e for e in self._get_deep_elements()
                                   if e['id'] == loc['value'] or e['name'] == loc['value']), {})

                results.append({
                    "intent": intent,
                    "action": "wait_and_type",
                    "tag": matched_el.get('tag', 'input'),
                    "locator": loc,
                    "test_data": p
                })

        # 3. PROCESS INTERACTION ACTIONS (Click/Select/Choose)
        interaction_keywords = r"\b(click|press|tap|submit|select|choose)\b"
        interaction_match = re.search(f"{interaction_keywords}\s+(?:on\s+)?(?:the\s+)?(\w+)", clean_text, re.IGNORECASE)

        if interaction_match:
            keyword = interaction_match.group(1).lower()
            intent = interaction_match.group(2)

            # Map keyword to your specific BasePage signatures
            action_type = "wait_and_select" if keyword in ["select", "choose"] else "wait_and_click"

            # Avoid duplicating an intent already handled in the 'type' loop
            if not any(res['intent'] == intent for res in results):
                loc = self._find_locator_weighted(intent)
                if loc:
                    matched_el = next((e for e in self._get_deep_elements()
                                       if e['id'] == loc['value'] or e['text'] == loc['value']), {})

                    self.highlight_element(loc)
                    results.append({
                        "intent": intent,
                        "action": action_type,
                        "tag": matched_el.get('tag', 'div'),
                        "role": matched_el.get('role', ''),
                        "locator": loc,
                        # For dropdowns, we pass the parameter found in the sentence as the selection value
                        "test_data": params[0] if action_type == "wait_and_select" and params else None
                    })

        # 4. FINAL VISUAL AUDIT
        if results:
            os.makedirs("logs", exist_ok=True)
            self.driver.save_screenshot(f"logs/AI_Discovery_Audit_{int(time.time())}.png")

        return results