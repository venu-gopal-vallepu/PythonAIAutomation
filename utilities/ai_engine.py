import os
import re
import time
from selenium.webdriver.common.by import By
from thefuzz import fuzz


class AIAutomationFramework:
    def __init__(self, driver):
        self.driver = driver
        # Increased weights for ARIA and Placeholder for modern web stability
        self.WEIGHTS = {
            'id': 1.0,
            'name': 0.9,
            'aria-label': 1.0,
            'placeholder': 0.9,
            'text': 0.7
        }
        self._nlp = None

    def _get_nlp(self):
        """Lazy loads Spacy only when discovery is triggered to keep test runs fast."""
        if self._nlp is None:
            import spacy
            try:
                self._nlp = spacy.load("en_core_web_md")
            except OSError:
                print("--- 📥 Downloading NLP Model (First time only) ---")
                os.system("python -m spacy download en_core_web_md")
                self._nlp = spacy.load("en_core_web_md")
        return self._nlp

    def highlight_element(self, loc):
        """Visual Audit: Highlights the discovered element in the browser."""
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
        """Scans the DOM including Shadow DOM roots."""
        return self.driver.execute_script("""
            const foundElements = [];
            function findRecursive(root) {
                const items = root.querySelectorAll('input, button, a, select, textarea, [role="button"]');
                items.forEach(el => {
                    const s = window.getComputedStyle(el);
                    if (el.offsetWidth > 0 && el.offsetHeight > 0 && s.display !== 'none') {
                        foundElements.push({
                            'tag': el.tagName.toLowerCase(), 'id': el.id, 'name': el.name,
                            'placeholder': el.placeholder || "", 'text': el.innerText || "",
                            'aria': el.getAttribute('aria-label') || "",
                            'canAcceptInput': ['input', 'textarea'].includes(el.tagName.toLowerCase()),
                            'isClickable': ['button', 'a'].includes(el.tagName.toLowerCase()) || s.cursor === 'pointer'
                        });
                    }
                    if (el.shadowRoot) findRecursive(el.shadowRoot);
                });
            }
            findRecursive(document);
            return foundElements;
        """)

    def _is_unique(self, locator):
        """Verifies if a locator returns exactly one element on the live DOM."""
        try:
            by_type = getattr(By, locator['strategy'].upper())
            count = len(self.driver.find_elements(by_type, locator['value']))
            return count == 1
        except:
            return False

    def _find_locator_weighted(self, context_text):
        """Weighted Algorithm with Uniqueness Validation."""
        nlp = self._get_nlp()
        elements = self._get_deep_elements()
        user_doc = nlp(context_text.lower())
        matches = []

        for el in elements:
            identity = f"{el['tag']} {el['id']} {el['name']} {el['placeholder']} {el['aria']} {el['text']}".lower()
            sim = user_doc.similarity(nlp(identity))
            attr_score = sum(fuzz.partial_ratio(context_text.lower(), str(el.get(k, ""))) * v
                             for k, v in self.WEIGHTS.items() if el.get(k))
            matches.append({"total": attr_score * sim, "element": el})

        matches.sort(key=lambda x: x['total'], reverse=True)

        # Validation Loop: Find the best UNIQUE locator
        for match in matches[:5]:
            el = match['element']
            candidates = []
            if el['id']: candidates.append({"strategy": "id", "value": el['id']})
            if el['name']: candidates.append({"strategy": "name", "value": el['name']})
            # Default to specific text-based XPath if ID/Name fail
            candidates.append(
                {"strategy": "xpath", "value": f"//{el['tag']}[contains(normalize-space(.),'{el['text'][:15]}')]"})

            for cand in candidates:
                if self._is_unique(cand):
                    return cand
        return None

    def discover_composite_logic(self, step_text):
        """
        Decomposes BDD steps with multiple parameters.
        Only triggers AI logic if the '[ai]' tag is present in the step text.
        """
        # 1. Check for the AI signal
        is_ai_trigger = "[ai]" in step_text.lower()

        if not is_ai_trigger:
            return "# AI Discovery not triggered for this step (Missing [ai] tag)."

        # 2. Clean the step text for processing (Remove the [ai] tag from the data)
        clean_step_text = step_text.replace("[ai]", "").replace("  ", " ").strip()

        # 3. Identify parameters from the CLEANED text
        params = re.findall(r"['\"](.*?)['\"]|<(.*?)>", clean_step_text)
        param_names = [p[0] if p[0] else p[1] for p in params]

        # 4. Extract context intents (Smart Split)
        raw_intents = re.split(r"['\"].*?['\"]|<.*?>", clean_step_text.lower())

        mappings = []
        for i, p_name in enumerate(param_names):
            intent_context = raw_intents[i].strip()

            # Borrow context if current intent is too vague
            if len(intent_context) < 3 and i > 0:
                intent_context = f"{raw_intents[i - 1]} {intent_context}".strip()

            # Remove BDD keywords (given/when/then) but keep the identity context
            clean_intent = re.sub(r'^(given|when|then|and|but)\s+', '', intent_context)

            loc = self._find_locator_weighted(clean_intent)
            if loc:
                self.highlight_element(loc)
                arg_name = p_name.replace("-", "_").replace(" ", "_")
                mappings.append({"loc": loc, "arg": arg_name, "intent": clean_intent})

        # 5. Evidence & Code Generation
        if not os.path.exists("logs"):
            os.makedirs("logs")

        timestamp = time.strftime("%Y%m%d-%H%M%S")
        self.driver.save_screenshot(f"logs/AI_Map_{timestamp}.png")

        # Generate unique method name from the cleaned text
        method_base = "_".join(re.sub(r"['\"].*?['\"]|<.*?>", "", clean_step_text).lower().split()[:3])
        method_name = f"{method_base}_{'_'.join([m['arg'] for m in mappings])}".strip("_")

        args = ", ".join(["self"] + [m['arg'] for m in mappings])
        code = [f"    def {method_name}({args}):"]
        for m in mappings:
            strategy = m['loc']['strategy'].upper()
            code.append(f"        # Intent: '{m['intent']}'")
            code.append(f"        self.wait_and_type((By.{strategy}, '{m['loc']['value']}'), {m['arg']})")

        return "\n".join(code)
