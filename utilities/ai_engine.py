import os
import re
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from thefuzz import fuzz


class AIAutomationFramework:
    def __init__(self, driver, timeout=10):
        self.driver = driver
        self.timeout = timeout
        # P3: Self-Healing Weights - Identity mapping for the fuzzy engine
        # Prioritizes user-visible labels over volatile React/MUI IDs
        self.WEIGHTS = {
            'aria-label': 1.0,
            'placeholder': 0.9,
            'text_intent': 0.8,  # Proximity label found by JS
            'role': 0.7,
            'name': 0.4,
            'id': 0.1
        }
        self._nlp = None

    def _get_nlp(self):
        """Lazy loads the NLP model for semantic similarity."""
        if self._nlp is None:
            import spacy
            try:
                self._nlp = spacy.load("en_core_web_md")
            except OSError:
                print("Downloading NLP Model for Semantic Analysis...")
                os.system("python -m spacy download en_core_web_md")
                self._nlp = spacy.load("en_core_web_md")
        return self._nlp

    def clean_for_fuzzy(self, text):
        """Cleans strings for matching (handles CamelCase, snake_case, etc)."""
        if not text: return ""
        text = re.sub(r'(?<!^)(?=[A-Z])', ' ', str(text))
        text = text.replace('_', ' ').replace('-', ' ')
        return re.sub(r'[^a-zA-Z\s]', '', text).lower().strip()

    def visual_debug(self, xpath, intent):
        """Paints a red border and a floating 'AI MATCH' label on the UI for authoring."""
        script = """
            const el = document.evaluate(arguments[0], document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
            if (el) {
                el.style.outline = '3px solid #ff4444';
                el.style.outlineOffset = '2px';
                const label = document.createElement('div');
                label.innerText = 'AI MATCH: ' + arguments[1];
                label.style = 'position:absolute; background:#ff4444; color:white; padding:2px 6px; font-size:11px; z-index:10000; top:-22px; left:0; border-radius:3px; font-family:sans-serif; font-weight:bold; white-space:nowrap;';
                el.style.position = 'relative';
                el.appendChild(label);
                setTimeout(() => { label.remove(); el.style.outline = 'none'; }, 2500);
            }
        """
        try:
            self.driver.execute_script(script, xpath, intent)
        except:
            pass

    def safe_interact(self, xpath, action="click"):
        """Scrolls element to center and performs action to avoid React overlay issues."""
        try:
            el = WebDriverWait(self.driver, self.timeout).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
            time.sleep(0.3)
            if action == "click":
                self.driver.find_element(By.XPATH, xpath).click()
            return True
        except:
            return False

    def _get_deep_elements(self):
        """JS Scraper: Relates labels to inputs via proximity and generates template-ready XPaths."""
        return self.driver.execute_script("""
            const getSmartXPath = (el) => {
                const tag = el.tagName.toLowerCase();
                const role = el.getAttribute('role') || "";
                const type = el.type || "";
                const text = el.innerText.trim();

                // DYNAMIC TEMPLATE: For Dropdown Items (li) or Options
                if (tag === 'li' || role === 'option') {
                    return `//li[contains(normalize-space(), "${text}")] | //*[@role="option"][contains(., "${text}")]`;
                }

                // DYNAMIC TEMPLATE: For Checkboxes/Radios via nearby text
                if (type === 'checkbox' || type === 'radio' || role === 'checkbox' || role === 'radio') {
                    return `//label[contains(., "${text}")] | //*[contains(text(), "${text}")]/preceding-sibling::input[1]`;
                }

                if (el.getAttribute('aria-label')) return `//*[@aria-label="${el.getAttribute('aria-label')}"]`;
                if (el.placeholder) return `//${tag}[@placeholder="${el.placeholder}"]`;

                return `(${tag})[${Array.from(document.querySelectorAll(tag)).indexOf(el) + 1}]`;
            };

            const found = [];
            const query = 'input, button, select, textarea, li, [role="option"], [role="combobox"], a, [role="button"], [role="checkbox"], [role="radio"]';

            document.querySelectorAll(query).forEach(el => {
                const r = el.getBoundingClientRect();
                // Check visibility or if it's a list item (portals)
                if (r.width > 0 || r.height > 0 || el.tagName.toLowerCase() === 'li') {

                    let labelText = "";
                    let minDist = 100;
                    document.querySelectorAll('label, span, b, p, strong').forEach(l => {
                        const lr = l.getBoundingClientRect();
                        const d = Math.sqrt(Math.pow(r.left-lr.left,2) + Math.pow(r.top-lr.top,2));
                        if (d < minDist && l.innerText.trim().length > 1) {
                            minDist = d; labelText = l.innerText.trim();
                        }
                    });

                    found.push({
                        tag: el.tagName.toLowerCase(),
                        id: el.id || "",
                        name: el.name || el.getAttribute('name') || "",
                        aria: el.getAttribute('aria-label') || "",
                        placeholder: el.placeholder || el.getAttribute('placeholder') || "",
                        text_intent: labelText || el.innerText.trim(),
                        role: el.getAttribute('role') || el.type || "",
                        xpath: getSmartXPath(el)
                    });
                }
            });
            return found;
        """)

    def _find_locator_weighted(self, intent):
        """The Brain: Calculates best element match using Fuzzy + NLP + Penalties."""
        nlp = self._get_nlp()
        elements = self._get_deep_elements()
        clean_intent = self.clean_for_fuzzy(intent)
        user_doc = nlp(clean_intent)

        matches = []
        for el in elements:
            max_fuzzy = 0
            attr_map = {
                'aria-label': el['aria'],
                'placeholder': el['placeholder'],
                'text_intent': el['text_intent'],
                'role': el['role'],
                'name': el['name'],
                'id': el['id']
            }

            for attr, weight in self.WEIGHTS.items():
                val = attr_map.get(attr, "")
                if val:
                    score = fuzz.token_sort_ratio(clean_intent, self.clean_for_fuzzy(str(val)))
                    max_fuzzy = max(max_fuzzy, score * weight)

            tag = el['tag'].lower()
            role = (el.get('role') or "").lower()

            # Boost/Penalize (Boost form elements, penalize generic nav links)
            adjustment = 0.3 if (tag == 'a' and 'button' not in role) else 1.3 if (
                    tag in ['input', 'button', 'li', 'textarea'] or
                    any(r in role for r in ['button', 'combobox', 'checkbox', 'radio', 'option'])
            ) else 1.0

            # Location Penalty (De-prioritize Header/Footer) with 0.1 safety guard
            penalty = 0.4 if any(nav in el['xpath'].lower() for nav in ['header', 'footer', 'nav', 'sidebar']) else 1.0
            penalty = max(penalty, 0.1)

            # NLP Similarity for Self-Healing
            context = self.clean_for_fuzzy(f"{el['text_intent']} {role} {el['name']}")
            sim = user_doc.similarity(nlp(context)) if user_doc.vector_norm > 0 else 0

            total_score = max_fuzzy * (sim + 0.1) * adjustment * penalty
            matches.append({"total": total_score, "element": el})

        matches.sort(key=lambda x: x['total'], reverse=True)

        if matches and matches[0]['total'] > 10:
            best = matches[0]['element']
            raw_xpath = best['xpath']
            best_role = best['role'].lower()
            best_tag = best['tag'].lower()

            # Map Component Types for Spark Handshake
            if any(r in best_role for r in ['checkbox', 'radio', 'switch']):
                c_type = "TOGGLE"
            elif any(r in best_role for r in ['combobox', 'option', 'listbox']) or best_tag in ['select', 'li']:
                c_type = "DROPDOWN"
            elif best_tag in ['button', 'a'] or 'button' in best_role:
                c_type = "BUTTON"
            else:
                c_type = "TEXTBOX"

            # PARAMETERIZATION LOGIC: replace the literal value with {value} for Spark
            template_xpath = raw_xpath.replace(intent, "{value}") if intent.lower() in raw_xpath.lower() else None

            self.visual_debug(raw_xpath, intent)

            return {
                "intent": intent,
                "component_type": c_type,
                "xpath": raw_xpath,
                "template_xpath": template_xpath,
                "is_parameterized": True if template_xpath else False,
                "is_data_input": True if c_type == "TEXTBOX" else False
            }
        return None

    def get_step_metadata(self, step_text):
        """Entry Point: Executes Phase-1 Dropdown clicks and returns all locators."""
        results = []
        # Support for "Admin", <Admin>, or {Admin}
        params = re.findall(r"[\"'](.*?)[\"']|<(.*?)>|\{(.*?)\}", step_text)
        intents = [next((i for i in g if i), None) for g in params]
        intents = [i for i in intents if i]

        for i, intent in enumerate(intents):
            meta = self._find_locator_weighted(intent)
            if meta:
                results.append(meta)
                # TWO-PHASE DROPDOWN LOGIC:
                # If first intent is a dropdown box, click it to reveal <li> items for Phase 2
                if i == 0 and meta['component_type'] == "DROPDOWN":
                    self.safe_interact(meta['xpath'], action="click")
                    time.sleep(1.0)  # Wait for React animation

        # Fallback for simple single-word commands (e.g., "Click Login")
        if not results:
            match = re.search(r"(?:click|on|select|type|into)\s+(?:the\s+)?(\w+)", step_text, re.I)
            if match:
                meta = self._find_locator_weighted(match.group(1))
                if meta: results.append(meta)

        return results