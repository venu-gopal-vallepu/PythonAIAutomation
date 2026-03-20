import os
import re
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.relative_locator import locate_with
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from thefuzz import fuzz


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

    def highlight_with_labels(self, discovery_data, color="#2ecc71"):
        """Visual Audit: Draws glowing borders and floating labels simultaneously."""
        if not discovery_data: return
        try:
            self.driver.execute_script("""
                const data = arguments[0];
                const color = arguments[1];
                document.querySelectorAll('.ai-discovery-label').forEach(l => l.remove());

                data.forEach(item => {
                    const el = item.element;
                    const labelText = item.label;
                    el.style.border = '4px solid ' + color;
                    el.style.boxShadow = '0 0 20px ' + color;
                    el.style.transition = 'all 0.3s ease-in-out';

                    const label = document.createElement('div');
                    label.className = 'ai-discovery-label';
                    label.innerText = 'AI: ' + labelText;
                    Object.assign(label.style, {
                        position: 'absolute', backgroundColor: color, color: 'white',
                        padding: '2px 8px', fontSize: '12px', fontFamily: 'sans-serif',
                        fontWeight: 'bold', borderRadius: '4px', zIndex: '10000',
                        pointerEvents: 'none', boxShadow: '2px 2px 5px rgba(0,0,0,0.2)'
                    });
                    const rect = el.getBoundingClientRect();
                    label.style.top = (window.scrollY + rect.top - 25) + 'px';
                    label.style.left = (window.scrollX + rect.left) + 'px';
                    document.body.appendChild(label);
                });
                if(data.length > 0) data[0].element.scrollIntoView({block: 'center', inline: 'nearest'});
            """, discovery_data, color)
        except Exception as e:
            print(f"⚠️ Visual Labeling failed: {e}")

    def _get_deep_elements(self):
        """Scans DOM and Shadow DOM for all interactive candidates."""
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
        """Ensures the element is unique and visible."""
        try:
            wait = WebDriverWait(self.driver, self.timeout)
            by_type = getattr(By, strategy.upper())
            element = wait.until(EC.visibility_of_element_located((by_type, value)))
            return element if len(self.driver.find_elements(by_type, value)) == 1 else None
        except (TimeoutException, StaleElementReferenceException):
            return None

    def _find_locator_weighted(self, intent):
        """
        HYBRID ENGINE: Optimized for Scenario Outlines and technical IDs.
        Uses NLP for meaning + Fuzzy for spelling + Vector Norm safety.
        """
        nlp = self._get_nlp()
        elements = self._get_deep_elements()

        # 1. Prepare User Intent
        clean_intent = intent.lower().strip()
        user_doc = nlp(clean_intent)

        matches = []
        for el in elements:
            # 2. Extract Element Identity for Hybrid Scoring
            # We bundle all attributes to give NLP/Fuzzy the best chance
            identity_parts = [
                str(el.get('id', '')),
                str(el.get('name', '')),
                str(el.get('placeholder', '')),
                str(el.get('aria', '')),
                str(el.get('text', ''))
            ]
            full_identity = " ".join(identity_parts).lower().strip()
            target_doc = nlp(full_identity)

            # 3. NLP SIMILARITY (The 'Brain')
            # Check vector_norm to prevent 0.0 scores for words like 'longname'
            sim = 0.0
            if user_doc.vector_norm > 0 and target_doc.vector_norm > 0:
                sim = user_doc.similarity(target_doc)

            # 4. FUZZY MATCHING (The 'Eyes')
            # partial_ratio is aggressive at finding 'longname' inside 'txt_longname_field'
            fuzzy_score = fuzz.partial_ratio(clean_intent, full_identity)

            # 5. FINAL CALCULATION
            # sim + 0.1 ensures that even if similarity is 0, fuzzy score carries the element
            total_score = fuzzy_score * (sim + 0.1)
            matches.append({"total": total_score, "element": el})

        # Sort by highest score
        matches.sort(key=lambda x: x['total'], reverse=True)

        # 6. TRY TOP 3 STRATEGIES
        for match in matches[:3]:
            el = match['element']
            candidates = []
            if el['id']: candidates.append({"strategy": "id", "value": el['id']})
            if el['name']: candidates.append({"strategy": "name", "value": el['name']})
            if el['placeholder']: candidates.append(
                {"strategy": "css_selector", "value": f"[placeholder='{el['placeholder']}']"})

            if el['text'] and len(el['text']) < 40:
                clean_xpath_text = el['text'].replace("'", "")
                candidates.append(
                    {"strategy": "xpath", "value": f"//{el['tag']}[contains(text(),'{clean_xpath_text}')]"})

            for cand in candidates:
                element = self._safe_find_unique(cand['strategy'], cand['value'])
                if element:
                    return element, cand

        # 7. FAILSAFE: Selenium 4 Relative Locators
        for match in matches[:2]:
            el = match['element']
            try:
                if el['text']:
                    rel_loc = locate_with(By.TAG_NAME, el['tag']).near({By.XPATH: f"//*[text()='{el['text']}']"})
                    element = self.driver.find_element(rel_loc)
                    if element:
                        return element, {"strategy": "relative", "value": f"near_{el['text']}"}
            except:
                pass

        return (None, None)

    def get_step_metadata(self, step_text):
        """DYNAMISM: Processes any number of parameters and identifies UI intents."""
        clean_text = step_text.replace("[ai]", "").strip()
        results = []
        visual_audit_list = []
        all_elements = self._get_deep_elements()

        # 1. UNIVERSAL PARAMETER EXTRACTION
        param_pattern = r"<(.*?)>|\{(.*?)\}|[\"'](.*?)[\"']"
        found_matches = re.findall(param_pattern, clean_text)

        # 2. DYNAMIC LOOPING
        for m in found_matches:
            intent = next((item for item in m if item), None)
            if not intent: continue

            raw_marker = f"<{m[0]}>" if m[0] else f"{{{m[1]}}}" if m[1] else f"\"{m[2]}\""
            print(f"🔍 AI Discovery Cycle for: '{intent}'")

            element_obj, locator_data = self._find_locator_weighted(intent)

            if locator_data:
                if element_obj:
                    visual_audit_list.append({'element': element_obj, 'label': intent})

                # Determine if element is a dropdown/select
                matched_el = next(
                    (e for e in all_elements if e['id'] == locator_data['value'] or e['text'] in locator_data['value']),
                    {})
                is_select = (matched_el.get('tag') == 'select' or
                             any(k in clean_text.lower() for k in ["select", "choose", "dropdown"]))

                results.append({
                    "intent": intent,
                    "action": "wait_and_select" if is_select else "wait_and_type",
                    "tag": matched_el.get('tag', 'input'),
                    "locator": locator_data,
                    "test_data": raw_marker
                })

        # 3. INTERACTION FALLBACK (Clicks)
        if not results:
            click_match = re.search(r"(?:click|press|tap|submit)\s+(?:on\s+)?(?:the\s+)?(\w+)", clean_text,
                                    re.IGNORECASE)
            if click_match:
                intent = click_match.group(1)
                element_obj, locator_data = self._find_locator_weighted(intent)
                if locator_data:
                    if element_obj:
                        visual_audit_list.append({'element': element_obj, 'label': intent})
                    results.append({
                        "intent": intent, "action": "wait_and_click",
                        "tag": "button", "locator": locator_data, "test_data": None
                    })

        # 4. FINAL VISUAL AUDIT
        if visual_audit_list:
            self.highlight_with_labels(visual_audit_list)
            os.makedirs("logs", exist_ok=True)
            self.driver.save_screenshot(f"logs/AI_Audit_{int(time.time())}.png")
            time.sleep(1.5)

        return results
