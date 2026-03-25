import os
import re
import time
import json
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from thefuzz import fuzz


class AIAutomationFramework:
    def __init__(self, driver, timeout=10, memory_file="ai_ui_memory.json"):
        self.driver = driver
        self.timeout = timeout
        self.memory_file = os.path.join(os.getcwd(), memory_file)

        # 🟢 ARCHITECT'S NAMESPACE: Default context
        self.active_page_context = "common"

        # 🚀 ARCHITECT WEIGHTS: Optimized for Modern Web (React/Angular)
        self.THRESHOLD = 38.0
        self.WEIGHTS = {
            'aria-label': 1.0,
            'placeholder': 0.9,
            'label_text': 1.0,
            'name': 0.4,
            'id': 0.05
        }
        self._nlp = None

    def set_context(self, page_name):
        """🚀 THE NAVIGATOR: Sets the folder name in JSON for the current Feature."""
        self.active_page_context = page_name.lower().replace(" ", "_")

    def _get_nlp(self):
        """Lazy-loads SpaCy for Semantic Similarity."""
        if self._nlp is None:
            import spacy
            try:
                self._nlp = spacy.load("en_core_web_md")
            except Exception:
                os.system("python -m spacy download en_core_web_md")
                self._nlp = spacy.load("en_core_web_md")
        return self._nlp

    # --- 🛠️ VISUALS & INTERACTION ---

    def highlight(self, element, color="orange"):
        """🚀 THE X-RAY: Non-destructive highlighting to preserve React styles."""
        try:
            self.driver.execute_script("""
                var el = arguments[0];
                var color = arguments[1];
                var originalBorder = el.style.border;
                el.style.border = '3px solid ' + color;
                el.style.backgroundColor = 'rgba(255, 165, 0, 0.1)';
                setTimeout(function() {
                    el.style.border = originalBorder;
                    el.style.backgroundColor = '';
                }, 1500);
            """, element, color)
        except:
            pass

    # --- 🏗️ STRUCTURED MEMORY (JSON) ---

    def _load_memory(self):
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_memory(self, intent, meta, page_context=None):
        """🚀 NAMESPACED SAVING: Organizes locators by Page Name."""
        memory = self._load_memory()
        ctx = page_context or self.active_page_context

        if ctx not in memory:
            memory[ctx] = {}

        memory[ctx][intent.lower()] = {
            "xpath": meta['xpath'],
            "tag": meta['tag'],
            "component_type": meta.get('component_type', 'BUTTON'),
            "class": meta.get('class', ''),
            "last_verified": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        with open(self.memory_file, 'w') as f:
            json.dump(memory, f, indent=4)

    # --- 🔍 CORE ENGINE: THE SCRAPER ---

    def _get_deep_elements(self):
        """Master Scraper: Extracts metadata from the DOM using JavaScript."""
        return self.driver.execute_script("""
            const found = [];
            const findAllElements = (root) => {
                const query = 'input, button, select, textarea, [role], a, div, span, i, svg';
                let elements = Array.from(root.querySelectorAll(query));
                root.querySelectorAll('*').forEach(el => {
                    if (el.shadowRoot) { elements.push(...findAllElements(el.shadowRoot)); }
                });
                return elements;
            };

            const allElements = findAllElements(document);
            allElements.forEach(el => {
                try {
                    const style = window.getComputedStyle(el);
                    if (el.offsetWidth === 0 || style.visibility === 'hidden' || style.display === 'none') return;

                    const tag = el.tagName.toLowerCase();
                    const cls = el.className.toString().toLowerCase();
                    const role = (el.getAttribute('role') || "").toLowerCase();

                    let cType = "BUTTON";
                    if (tag === 'textarea' || (tag === 'input' && !['checkbox', 'radio'].includes(el.type))) { cType = "TEXTBOX"; }
                    else if (el.type === 'checkbox' || role === 'checkbox') { cType = "CHECKBOX"; }
                    else if (tag === 'select' || el.hasAttribute('aria-haspopup')) { cType = "DROPDOWN"; }

                    let intent = (el.placeholder || el.getAttribute('aria-label') || "").trim();
                    if (intent.length < 2) {
                        let neighbor = el.previousElementSibling || el.parentElement.querySelector('label');
                        if (neighbor && neighbor.innerText.trim().length > 1) { intent = neighbor.innerText; }
                    }
                    if (intent.length < 2) intent = el.innerText || "";
                    intent = intent.split('\\n')[0].trim().replace(/:$/, "");
                    if (intent.length < 2) return;

                    found.push({
                        intent: intent, component_type: cType, 
                        xpath: el.id ? `//*[@id='${el.id}']` : `//*[contains(text(), '${intent}')]`,
                        tag: tag, class: cls, 
                        placeholder: el.placeholder || "", aria: el.getAttribute('aria-label') || ""
                    });
                } catch (e) {}
            });
            return found;
        """)

    # --- 🧠 THE BRAIN: NLP & FUZZY MATCHING ---

    def _find_locator_weighted(self, user_query):
        self._wait_for_app_ready()
        nlp = self._get_nlp()
        elements = self._get_deep_elements()
        if not elements: return None

        query_doc = nlp(user_query.lower())
        matches = []

        for el in elements:
            scores = {
                'aria-label': fuzz.partial_ratio(user_query.lower(), el['aria'].lower()),
                'placeholder': fuzz.partial_ratio(user_query.lower(), el['placeholder'].lower()),
                'label_text': fuzz.token_sort_ratio(user_query.lower(), el['intent'].lower())
            }
            weighted_sum = sum(scores[k] * self.WEIGHTS.get(k, 0) for k in scores)

            el_doc = nlp(el['intent'].lower())
            sim = query_doc.similarity(el_doc) if query_doc.vector_norm > 0 else 0
            total = (weighted_sum / 2) + (sim * 50)
            matches.append({"total": total, "element": el})

        matches.sort(key=lambda x: x['total'], reverse=True)
        if matches and matches[0]['total'] >= self.THRESHOLD:
            return matches[0]['element']
        return None

    # --- 🚀 THE P2 ORCHESTRATOR: RESOLVE & HEAL ---

    def get_step_metadata(self, step_text, page_context=None):
        """🚀 THE RESOLVER: Hierarchy -> Memory[Page] -> Memory[Common] -> Heal."""
        params = re.findall(r"[\"'](.*?)[\"']|<(.*?)>|\{(.*?)\}", step_text)
        intents = [next((i for i in g if i), None) for g in params if any(g)]
        results = []
        memory = self._load_memory()

        ctx = page_context or self.active_page_context

        for intent in intents:
            intent_key = intent.lower()
            meta = None

            # 1. Check Memory (Page Context then Common)
            if ctx in memory and intent_key in memory[ctx]:
                meta = memory[ctx][intent_key]
            elif "common" in memory and intent_key in memory["common"]:
                meta = memory["common"][intent_key]

            # 2. P2 Validation: Is the locator still alive?
            if meta:
                try:
                    el = self.driver.find_element(By.XPATH, meta['xpath'])
                    if not el.is_displayed(): raise Exception("Element Hidden")
                    self.highlight(el, "cyan")  # Success Highlight
                except:
                    print(f"🛠️ UI Changed for '{intent}'. Triggering Healing...")
                    meta = None

                    # 3. P1 Fallback: Discover and Update Memory
            if not meta:
                meta = self._find_locator_weighted(intent)
                if meta:
                    self._save_memory(intent, meta, ctx)
                    el = self.driver.find_element(By.XPATH, meta['xpath'])
                    self.highlight(el, "springgreen")  # New discovery highlight

            if meta:
                results.append(meta)

        return results

    def _wait_for_app_ready(self):
        try:
            WebDriverWait(self.driver, 3).until_not(
                EC.presence_of_element_located((By.XPATH, "//*[contains(@class, 'loader')]")))
        except:
            pass
