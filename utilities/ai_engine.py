import os
import re
import time
import math
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from thefuzz import fuzz, process


class AIAutomationFramework:
    def __init__(self, driver, timeout=10):
        self.driver = driver
        self.timeout = timeout
        # 🚀 ARCHITECT WEIGHTS: Boosters for stable attributes, Penalties for brittle ones
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
        text = re.sub(r'(?<!^)(?=[A-Z])', ' ', str(text))  # Handle PascalCase
        return re.sub(r'[^a-zA-Z\s]', '', text).lower().replace('_', ' ').strip()

    def _get_deep_elements(self):
        """🚀 P1 FULL-SPECTRUM SCRAPER: Synchronized for Python Scoring."""
        return self.driver.execute_script("""
            const found = [];
            const allElements = document.querySelectorAll('input, button, select, textarea, [role], [aria-haspopup], div, span, a');

            allElements.forEach(el => {
                try {
                    const style = window.getComputedStyle(el);
                    if (el.offsetWidth === 0 || style.visibility === 'hidden' || style.display === 'none') return;

                    const tag = el.tagName.toLowerCase();
                    const isStandard = ['input', 'button', 'select', 'textarea', 'a'].includes(tag);
                    const role = (el.getAttribute('role') || "").toLowerCase();
                    const isPointer = style.cursor === 'pointer';

                    if (!isStandard && role === "" && !isPointer) return;

                    const type = (el.getAttribute('type') || "").toLowerCase();
                    const aria = el.getAttribute('aria-haspopup') || "";
                    const cls = el.className.toString().toLowerCase();

                    let cType = "BUTTON"; 
                    if (tag === 'select' || role.includes('box') || aria !== "" || cls.includes('select')) {
                        cType = "DROPDOWN";
                    } else if (tag === 'textarea' || (tag === 'input' && !['checkbox', 'radio'].includes(type))) {
                        cType = "TEXTBOX";
                    } else if (type === 'checkbox' || role === 'checkbox') {
                        cType = "CHECKBOX";
                    } else if (type === 'radio' || role === 'radio') {
                        cType = "RADIO";
                    }

                    let intent = (el.placeholder || el.name || el.getAttribute('aria-label') || el.innerText || "").split('\\n')[0].trim();
                    if (!intent || intent.length < 2) {
                        const label = document.querySelector(`label[for="${el.id}"]`) || el.closest('label');
                        intent = label ? label.innerText : "";
                    }
                    if (!intent) intent = el.parentElement?.innerText?.split('\\n')[0] || "Unknown";

                    let xpath = el.name ? `//${tag}[@name='${el.name}']` : `//*[contains(normalize-space(), "${intent.replace(/[":]/g, "").trim()}")]`;

                    found.push({
                        intent: intent.replace(/:$/, "").trim(),
                        component_type: cType,
                        xpath: xpath,
                        template_xpath: `//*[contains(normalize-space(), "${intent.replace(/[":]/g, "").trim()}")]/following::${tag}[1]`,
                        is_data_input: (cType === "TEXTBOX" || cType === "DROPDOWN"),
                        tag: tag,
                        role: role,
                        id: el.id || "",
                        aria: el.getAttribute('aria-label') || "",
                        placeholder: el.placeholder || "",
                        name: el.name || ""
                    });
                } catch (e) {}
            });
            return found;
        """)

    def _find_locator_weighted(self, intent):
        """The Brain: Matches Intent to Metadata using NLP + Multi-Attr Fuzzy Scoring."""
        nlp = self._get_nlp()
        elements = self._get_deep_elements()

        if not elements:
            print("⚠️ [AI ERROR]: Scraper found 0 elements. Check page load.")
            return None

        clean_intent = self.clean_for_fuzzy(intent)
        user_doc = nlp(clean_intent)
        matches = []

        for el in elements:
            max_score = 0
            # ✅ FIXED: Now matches the keys returned by JavaScript
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
                    max_score = max(max_score, score * weight)

            context_str = f"{el['intent']} {el['name']} {el['placeholder']} {el['role']}"
            context_doc = nlp(self.clean_for_fuzzy(context_str))
            sim = user_doc.similarity(context_doc) if (user_doc.vector_norm > 0 and context_doc.vector_norm > 0) else 0

            total_score = max_score * (sim + 0.1)
            matches.append({"total": total_score, "element": el})

        matches.sort(key=lambda x: x['total'], reverse=True)

        if matches and matches[0]['total'] > 12:
            best = matches[0]['element']
            # ✅ FIXED: Return all keys required by discover_and_map and Spark
            return {
                "intent": best['intent'],
                "component_type": best['component_type'],
                "xpath": best['xpath'],
                "template_xpath": best['template_xpath'],
                "is_data_input": best['is_data_input'],
                "name": best['name'],
                "placeholder": best['placeholder']
            }
        return None

    def discover_and_map(self, ai_ctx, user_intent=None):
        """Maps page for Spark Assist POM generation handling all 5 types."""
        elements = self._get_deep_elements()
        for el in elements:
            intent_key = el['intent'].lower().replace(" ", "_").strip(":")
            if not user_intent or user_intent.lower() in el['intent'].lower():
                ai_ctx["buffer"][intent_key] = {
                    "intent": el['intent'],
                    "component_type": el['component_type'],
                    "xpath": el['xpath'],
                    "template_xpath": el['template_xpath'],
                    "is_data_input": el['is_data_input'],
                    "name": el['name'],
                    "placeholder": el['placeholder']
                }
        return ai_ctx["buffer"]

    def get_step_metadata(self, step_text):
        """Orchestrates metadata discovery and auto-handles Dropdowns."""
        results = []
        params = re.findall(r"[\"'](.*?)[\"']|<(.*?)>|\{(.*?)\}", step_text)
        intents = [next((i for i in g if i), None) for g in params if any(g)]

        for i, intent in enumerate(intents):
            meta = self._find_locator_weighted(intent)
            if meta:
                results.append(meta)
                # Auto-open dropdowns for multi-parameter steps
                if meta['component_type'] == "DROPDOWN":
                    try:
                        el = WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable((By.XPATH, meta['xpath'])))
                        self.driver.execute_script("arguments[0].click();", el)
                        time.sleep(0.5)
                    except:
                        pass
        return results
