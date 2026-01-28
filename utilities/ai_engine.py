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
        Universal Discovery Engine:
        1. Identifies if the [ai] trigger is present.
        2. Cleans the text for NLP analysis.
        3. Supports both Parameterized steps and Simple action steps.
        4. Generates a unique Page Object method with proper Selenium actions.
        """
        # 1. Activation Gate
        if "[ai]" not in step_text.lower():
            return None

        # 2. Text Sanitization (Remove [ai] so it doesn't skew NLP similarity)
        clean_text = step_text.replace("[ai]", "").replace("  ", " ").strip()

        # 3. Parameter Extraction (Supports "hardcoded" and <placeholders>)
        params = re.findall(r"['\"](.*?)['\"]|<(.*?)>", clean_text)
        param_names = [p[0] if p[0] else p[1] for p in params]

        mappings = []

        # --- LOGIC BRANCHING ---
        if param_names:
            # BRANCH A: Multiple or Single Parameters (Type Action)
            raw_intents = re.split(r"['\"].*?['\"]|<.*?>", clean_text.lower())
            for i, p_name in enumerate(param_names):
                intent = raw_intents[i].strip()
                # Borrow context if intent is too short (e.g., "and <city>")
                if len(intent) < 3 and i > 0:
                    intent = f"{raw_intents[i - 1]} {intent}"

                # Remove BDD keywords
                clean_intent = re.sub(r'^(given|when|then|and|but)\s+', '', intent)

                loc = self._find_locator_weighted(clean_intent)
                if loc:
                    self.highlight_element(loc)
                    # Use parameter name from BDD as the Python argument name
                    arg_name = p_name.replace("-", "_").replace(" ", "_")
                    mappings.append({
                        "loc": loc,
                        "arg": arg_name,
                        "action": "wait_and_type",
                        "intent": clean_intent
                    })
        else:
            # BRANCH B: No Parameters (Click/Interaction Action)
            clean_intent = re.sub(r'^(given|when|then|and|but)\s+', '', clean_text.lower())
            loc = self._find_locator_weighted(clean_intent)
            if loc:
                self.highlight_element(loc)
                mappings.append({
                    "loc": loc,
                    "arg": None,
                    "action": "wait_and_click",
                    "intent": clean_intent
                })

        # --- 4. Validation & Evidence ---
        if not mappings:
            return f"# AI Error: Could not find UI elements for intent: {clean_text}"

        # Create logs directory and capture visual audit
        if not os.path.exists("logs"): os.makedirs("logs")
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        self.driver.save_screenshot(f"logs/AI_Map_{timestamp}.png")

        # --- 5. Python Code Generation ---
        # Create a PEP8 compliant method name from the first few words of the step
        method_base = "_".join(re.sub(r"['\"].*?['\"]|<.*?>", "", clean_text).lower().split()[:3])

        # Filter out None values for arguments (clicks don't have args)
        args_list = ["self"] + [m['arg'] for m in mappings if m['arg']]
        args_str = ", ".join(args_list)

        code = [f"    def {method_base}({args_str}):"]
        for m in mappings:
            strategy = m['loc']['strategy'].upper()
            val_part = f", {m['arg']}" if m['arg'] else ""
            code.append(f"        # Action for: '{m['intent']}'")
            code.append(f"        self.{m['action']}((By.{strategy}, '{m['loc']['value']}'){val_part})")

        return "\n".join(code)
