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
        """P1 STABLE SCRAPER: Fast, deterministic detection of all 5 HTML types + Textarea."""
        return self.driver.execute_script("""
            const found = [];
            // 🚀 1. TARGETED SELECTOR: Avoids 'all (*)' to prevent hanging/loops
            const selectors = 'input, button, select, textarea, [role="combobox"], [role="checkbox"], [role="radio"], [role="button"], [role="textbox"]';
            const controls = document.querySelectorAll(selectors);

            controls.forEach(el => {
                try {
                    const style = window.getComputedStyle(el);
                    if (el.offsetWidth === 0 || style.visibility === 'hidden') return;

                    const tag = el.tagName.toLowerCase();
                    const type = (el.getAttribute('type') || "").toLowerCase();
                    const role = (el.getAttribute('role') || "").toLowerCase();
                    const id = el.id || "";
                    const name = el.getAttribute('name') || "";
                    const placeholder = el.getAttribute('placeholder') || "";

                    // 🚀 2. INTENT DETECTION (Labeling)
                    let intent = "";
                    const nativeLabel = document.querySelector(`label[for="${id}"]`) || el.closest('label');
                    if (nativeLabel) intent = nativeLabel.innerText;
                    else if (placeholder) intent = placeholder;
                    else if (name) intent = name;
                    else {
                        const prevText = el.previousElementSibling?.innerText || el.parentElement?.innerText;
                        intent = (prevText && prevText.length < 50) ? prevText : (el.innerText || "");
                    }

                    // 🚀 3. CLASSIFICATION (The 5-Element Matrix)
                    let cType = "BUTTON";
                    if (tag === 'select' || role.includes('box')) cType = "DROPDOWN";
                    else if (type === 'checkbox' || role === 'checkbox') cType = "CHECKBOX";
                    else if (type === 'radio' || role === 'radio') cType = "RADIO";
                    else if (tag === 'input' || tag === 'textarea' || role === 'textbox') cType = "TEXTBOX";

                    // 🚀 4. CLEAN LOCATOR GENERATOR (Prioritizes Direct Attributes)
                    let finalXpath = "";
                    if (name) finalXpath = `//${tag}[@name='${name}']`;
                    else if (placeholder) finalXpath = `//${tag}[@placeholder='${placeholder}']`;
                    else if (id && !id.includes(':') && !id.startsWith('mui')) finalXpath = `//${tag}[@id='${id}']`;
                    else {
                        const cleanIntent = intent.trim().split('\\n')[0].replace(/[":]/g, "");
                        finalXpath = `//*[contains(normalize-space(), "${cleanIntent}")]/following::${tag}[1]`;
                    }

                    found.push({
                        intent: intent.trim().split('\\n')[0].replace(/:$/, ""),
                        component_type: cType,
                        xpath: finalXpath,
                        template_xpath: `//*[contains(normalize-space(), "${intent.trim().split('\\n')[0].replace(/[":]/g, "")}")]/following::${tag}[1]`,
                        is_data_input: (cType === "TEXTBOX" || cType === "DROPDOWN"),
                        name: name,
                        placeholder: placeholder,
                        tag: tag,
                        aria: el.getAttribute('aria-label') || "",
                        role: role,
                        id: id
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
                    # Fuzzy match score (0-100)
                    score = fuzz.token_sort_ratio(clean_intent, self.clean_for_fuzzy(str(val)))
                    # Apply Architect's Weighting (Booster/Penalty)
                    max_score = max(max_score, score * weight)

            # Extra Booster: NLP Similarity
            context_str = f"{el['intent']} {el['name']} {el['placeholder']} {el['role']}"
            context_doc = nlp(self.clean_for_fuzzy(context_str))
            sim = user_doc.similarity(context_doc) if user_doc.vector_norm > 0 else 0

            # Combine Fuzzy and NLP
            total_score = max_score * (sim + 0.1)
            matches.append({"total": total_score, "element": el})

        matches.sort(key=lambda x: x['total'], reverse=True)

        # Threshold for P1 Stability
        if matches and matches[0]['total'] > 12:
            best = matches[0]['element']
            return {
                "intent": intent,
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
                    except: pass
        return results