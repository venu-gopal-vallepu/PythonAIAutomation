import os
import re
import time
import math
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from thefuzz import fuzz


class AIAutomationFramework:
    def __init__(self, driver, timeout=10):
        self.driver = driver
        self.timeout = timeout
        # Weights for Self-Healing
        self.WEIGHTS = {
            'aria-label': 1.0,
            'placeholder': 0.9,
            'intent': 0.8,
            'name': 0.8,
            'role': 0.7,
            'id': 0.1
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

    def clean_for_fuzzy(self, text):
        if not text: return ""
        text = re.sub(r'(?<!^)(?=[A-Z])', ' ', str(text))
        return re.sub(r'[^a-zA-Z\s]', '', text).lower().replace('_', ' ').strip()

    def visual_debug(self, xpath, intent):
        """Highlights the matched element in the browser for manual verification."""
        script = """
            const el = document.evaluate(arguments[0], document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
            if (el) {
                const original = el.style.outline;
                el.style.outline = '3px solid #00ff00';
                const label = document.createElement('div');
                label.innerText = 'AI MATCH: ' + arguments[1];
                label.style = 'position:absolute; background:#00ff00; color:black; padding:2px; z-index:10000; top:-20px; font-size:10px; font-weight:bold;';
                el.appendChild(label);
                setTimeout(() => { label.remove(); el.style.outline = original; }, 2000);
            }
        """
        try:
            self.driver.execute_script(script, xpath, intent)
        except:
            pass

    def safe_interact(self, xpath, action="click"):
        try:
            el = WebDriverWait(self.driver, self.timeout).until(EC.element_to_be_clickable((By.XPATH, xpath)))
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
            time.sleep(0.2)
            if action == "click": el.click()
            return True
        except:
            return False

    def _get_deep_elements(self):
        """ARCHITECT SCRAPER: Captures Name, Placeholder, and Visual Proximity."""
        return self.driver.execute_script("""
            const getControlInfo = (el) => {
                const style = window.getComputedStyle(el);
                const role = el.getAttribute('role') || el.type || "";
                const tag = el.tagName.toLowerCase();

                // Ensure the element is actually interactable by a human
                const isVisible = el.offsetWidth > 0 && el.offsetHeight > 0 && style.visibility !== 'hidden';

                return {
                    tag: tag,
                    role: role,
                    aria: el.getAttribute('aria-label') || "",
                    placeholder: el.getAttribute('placeholder') || "",
                    name: el.getAttribute('name') || "",
                    id: el.id || "",
                    isDropdown: role.includes('combobox') || role.includes('listbox') || tag === 'select' || (style.cursor === 'pointer' && el.innerText.includes('▼')),
                    isInput: ['INPUT', 'TEXTAREA', 'SELECT'].includes(tag),
                    isVisible: isVisible
                };
            };

            const generateSemanticXPath = (el, intentText) => {
                const clean = intentText.replace(/[":]/g, "").trim();
                return `//*[contains(normalize-space(), "${clean}")]/following::*[(self::input or self::select or @role or @onclick or contains(@style, "cursor: pointer"))][1]`;
            };

            const found = [];
            const all = Array.from(document.querySelectorAll('*'));

            // Only consider controls that are VISIBLE to avoid 'Hidden Input' traps
            const controls = all.filter(el => {
                const info = getControlInfo(el);
                return info.isVisible && (window.getComputedStyle(el).cursor === 'pointer' || el.onclick || info.isInput);
            });

            all.filter(el => el.innerText?.trim().length > 1 && el.innerText.length < 50 && el.children.length === 0).forEach(node => {
                const rT = node.getBoundingClientRect();
                let closest = null; let minDist = 180; // Slightly larger radius for spacious MUI layouts

                controls.forEach(c => {
                    if (c === node) return;
                    const rC = c.getBoundingClientRect();
                    const d = Math.hypot((rT.left+rT.width/2)-(rC.left+rC.width/2), (rT.top+rT.height/2)-(rC.top+rC.height/2));
                    if (d < minDist) { minDist = d; closest = c; }
                });

                if (closest) {
                    const info = getControlInfo(closest);
                    found.push({
                        intent: node.innerText.trim(),
                        ...info,
                        template_xpath: generateSemanticXPath(closest, node.innerText.trim()),
                        xpath: `(${info.tag})[${Array.from(document.querySelectorAll(info.tag)).indexOf(closest) + 1}]`
                    });
                }
            });
            return found;
        """)

    def _find_locator_weighted(self, intent):
        """The Brain: Matches Intent to Scraped Metadata using NLP + Multi-Attr Fuzzy."""
        nlp = self._get_nlp()
        elements = self._get_deep_elements()
        clean_intent = self.clean_for_fuzzy(intent)
        user_doc = nlp(clean_intent)

        matches = []
        for el in elements:
            max_fuzzy = 0
            # Attribute Map for Weighted Scoring
            attr_map = {
                'aria-label': el['aria'],
                'placeholder': el['placeholder'],
                'name': el['name'],
                'intent': el['intent'],
                'role': el['role'],
                'id': el['id']
            }

            for attr, weight in self.WEIGHTS.items():
                val = attr_map.get(attr, "")
                if val:
                    score = fuzz.token_sort_ratio(clean_intent, self.clean_for_fuzzy(str(val)))
                    max_fuzzy = max(max_fuzzy, score * weight)

            # Contextual Similarity (Intent + Name + Placeholder)
            context_str = f"{el['intent']} {el['name']} {el['placeholder']} {el['role']}"
            context_doc = nlp(self.clean_for_fuzzy(context_str))
            sim = user_doc.similarity(context_doc) if user_doc.vector_norm > 0 else 0

            total_score = max_fuzzy * (sim + 0.1)
            matches.append({"total": total_score, "element": el})

        matches.sort(key=lambda x: x['total'], reverse=True)

        if matches and matches[0]['total'] > 12:  # Threshold for confidence
            best = matches[0]['element']
            return {
                "intent": intent,
                "component_type": "DROPDOWN" if best['isDropdown'] else "TEXTBOX" if best['isInput'] else "BUTTON",
                "xpath": best['xpath'],
                "template_xpath": best['template_xpath'],
                "is_data_input": best['isInput'],
                "name": best['name'],
                "placeholder": best['placeholder']
            }
        return None

    def discover_and_map(self, ai_ctx, user_intent=None):
        """Maps page for Spark Assist POM generation."""
        elements = self._get_deep_elements()
        for el in elements:
            intent_key = el['intent'].lower().replace(" ", "_").strip(":")
            if not user_intent or user_intent.lower() in el['intent'].lower():
                ai_ctx["buffer"][intent_key] = {
                    "intent": el['intent'],
                    "component_type": "DROPDOWN" if el['isDropdown'] else "TEXTBOX" if el['isInput'] else "BUTTON",
                    "xpath": el['xpath'],
                    "template_xpath": el['template_xpath'], # <--- ADD THIS LINE
                    "is_data_input": el['isInput'],
                    "name": el['name'] # <--- ALSO GOOD TO ADD
                }
        return ai_ctx["buffer"]

    def get_step_metadata(self, step_text):
        """Entry point for Gherkin Phase-1/Phase-2 execution."""
        results = []
        params = re.findall(r"[\"'](.*?)[\"']|<(.*?)>|\{(.*?)\}", step_text)
        intents = [next((i for i in g if i), None) for g in params if any(g)]

        for i, intent in enumerate(intents):
            meta = self._find_locator_weighted(intent)
            if meta:
                results.append(meta)
                # Auto-click dropdowns to reveal options for subsequent parameters
                if i == 0 and meta['component_type'] == "DROPDOWN":
                    try:
                        el = WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable((By.XPATH, meta['xpath'])))
                        self.driver.execute_script("arguments[0].click();", el)
                        time.sleep(0.8) # Wait for portal/animation
                    except: pass
        return results
