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
            'text': 0.7
        }
        self._nlp = None

    def _get_nlp(self):
        """Lazy loads Spacy model for performance."""
        if self._nlp is None:
            import spacy
            try:
                self._nlp = spacy.load("en_core_web_md")
            except OSError:
                print("--- 📥 Downloading NLP Model ---")
                os.system("python -m spacy download en_core_web_md")
                self._nlp = spacy.load("en_core_web_md")
        return self._nlp

    def highlight_element(self, loc):
        """Visual Audit: Highlights the discovered element."""
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
        """Scans the DOM including Shadow DOM roots for interactive elements."""
        return self.driver.execute_script("""
            const foundElements = [];
            function findRecursive(root) {
                // Added [role] and [onclick] to the selector for better coverage
                const items = root.querySelectorAll('input, button, a, select, textarea, [role], [onclick]');
                items.forEach(el => {
                    const s = window.getComputedStyle(el);
                    if (el.offsetWidth > 0 && el.offsetHeight > 0 && s.display !== 'none') {
                        foundElements.push({
                            'tag': el.tagName.toLowerCase(), 
                            'id': el.id, 
                            'name': el.name,
                            'placeholder': el.placeholder || "", 
                            'text': el.innerText.trim() || "",
                            'aria': el.getAttribute('aria-label') || "",
                            'role': el.getAttribute('role') || "", // Added Role
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
        """Ensures the locator points to exactly one element."""
        try:
            by_type = getattr(By, locator['strategy'].upper())
            return len(self.driver.find_elements(by_type, locator['value'])) == 1
        except:
            return False

    def _find_locator_weighted(self, context_text):
        """Core algorithm: NLP + Fuzzy matching to find the best unique locator."""
        nlp = self._get_nlp()
        elements = self._get_deep_elements()
        user_doc = nlp(context_text.lower())

        matches = []
        for el in elements:
            # Create a string representation of the element for NLP comparison
            identity = f"{el['tag']} {el['id']} {el['name']} {el['placeholder']} {el['aria']} {el['text']}".lower()
            sim = user_doc.similarity(nlp(identity))

            # Fuzzy match specific attributes
            attr_score = sum(fuzz.partial_ratio(context_text.lower(), str(el.get(k, ""))) * v
                             for k, v in self.WEIGHTS.items() if el.get(k))

            matches.append({"total": attr_score * sim, "element": el})

        matches.sort(key=lambda x: x['total'], reverse=True)

        # Validation: Return the first unique candidate
        for match in matches[:5]:
            el = match['element']
            candidates = []
            if el['id']: candidates.append({"strategy": "id", "value": el['id']})
            if el['name']: candidates.append({"strategy": "name", "value": el['name']})
            if el['placeholder']: candidates.append(
                {"strategy": "css_selector", "value": f"[placeholder='{el['placeholder']}']"})

            # Fallback to smart XPath
            if el['text']:
                clean_text = el['text'][:20].replace("'", "")
                candidates.append({"strategy": "xpath", "value": f"//{el['tag']}[contains(text(),'{clean_text}')]"})

            for cand in candidates:
                if self._is_unique(cand):
                    return cand
        return None

    def get_step_metadata(self, step_text):
        """
        Interprets the Gherkin step and returns structured data for Spark Assist.
        """
        if "[ai]" not in step_text.lower():
            return []

        clean_text = step_text.replace("[ai]", "").strip()

        # Extract params: "venu@gmail.com" or <username>
        params = re.findall(r"['\"](.*?)['\"]|<(.*?)>", clean_text)
        param_values = [p[0] if p[0] else p[1] for p in params]

        results = []

        if param_values:
            # Case: Step with parameters (likely a 'Type' action)
            intents = re.split(r"['\"].*?['\"]|<.*?>", clean_text.lower())
            for i, val in enumerate(param_values):
                intent = re.sub(r'^(given|when|then|and|but)\s+', '', intents[i].strip())
                loc = self._find_locator_weighted(intent)
                if loc:
                    self.highlight_element(loc)
                    results.append({
                        "intent": intent,
                        "action": "wait_and_type",
                        "locator": loc,
                        "test_data": val
                    })
        else:
            # Case: Step without parameters (likely a 'Click' action)
            intent = re.sub(r'^(given|when|then|and|but)\s+', '', clean_text.lower())
            loc = self._find_locator_weighted(intent)
            if loc:
                self.highlight_element(loc)
                results.append({
                    "intent": intent,
                    "action": "wait_and_click",
                    "locator": loc,
                    "test_data": None
                })

        # Visual Audit
        if results:
            os.makedirs("logs", exist_ok=True)
            self.driver.save_screenshot(f"logs/AI_Audit_{int(time.time())}.png")

        return results