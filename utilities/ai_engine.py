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

        # 🚀 ARCHITECT WEIGHTS: Optimized for Modern React/Angular (No-TestID mode)
        self.THRESHOLD = 38.0
        self.WEIGHTS = {
            'aria-label': 1.0,
            'placeholder': 0.9,
            'label_text': 1.0,  # 🎯 Primary Signal: Neighbor or Self-Text
            'name': 0.4,
            'id': 0.05  # 📉 Low trust for dynamic React IDs
        }
        self._nlp = None

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

    # --- 🛠️ INTERACTION, VISUALS & MEMORY ---

    def highlight(self, element, color="orange"):
        """Visual feedback to see what the AI 'Eyes' are targeting."""
        try:
            self.driver.execute_script(
                f"arguments[0].setAttribute('style', 'border: 3px solid {color}; background: rgba(255,165,0,0.1);');",
                element
            )
        except:
            pass

    def safe_click(self, element):
        """🚀 THE ARCHITECT'S CLICK: Uses JS as a fallback for React overlays."""
        try:
            self.highlight(element, color="springgreen")
            element.click()
        except Exception:
            self.driver.execute_script("arguments[0].click();", element)

    def _load_memory(self):
        if os.path.exists(self.memory_file):
            with open(self.memory_file, 'r') as f:
                return json.load(f)
        return {}

    def _save_memory(self, intent, meta):
        memory = self._load_memory()
        memory[intent.lower()] = {
            "xpath": meta['xpath'],
            "tag": meta['tag'],
            "class": meta.get('class', ''),
            "last_verified": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        with open(self.memory_file, 'w') as f:
            json.dump(memory, f, indent=4)

    def _wait_for_app_ready(self):
        """🚀 THE PULSE CHECK: Waits for React/Angular loaders to vanish."""
        try:
            loader_query = "//*[contains(@class, 'spinner') or contains(@class, 'loader') or contains(@id, 'loading')]"
            WebDriverWait(self.driver, 4).until_not(EC.presence_of_element_located((By.XPATH, loader_query)))
        except:
            pass

            # --- 🔍 CORE ENGINE: THE SCRAPER ---

    def _get_deep_elements(self):
        """🚀 THE MASTER SCRAPER: Pierces Shadow DOM & Handles Caret-Parent Bubbling."""
        return self.driver.execute_script("""
            const found = [];
            const findAllElements = (root) => {
                const query = 'input, button, select, textarea, [role], [aria-haspopup], [aria-expanded], a, div, span, i, svg';
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
                    const isPointer = style.cursor === 'pointer';

                    // --- 1. CARET & PARENT BUBBLE-UP ---
                    const isCaret = (tag === 'i' || tag === 'svg' || tag === 'span') && 
                                   (cls.includes('caret') || cls.includes('chevron') || cls.includes('arrow') || cls.includes('icon-down'));

                    let targetEl = isCaret ? (el.parentElement || el) : el;
                    let targetTag = targetEl.tagName.toLowerCase();
                    let targetCls = targetEl.className.toString().toLowerCase();

                    // --- 2. CLASSIFICATION ---
                    let cType = "BUTTON";
                    const hasCaretChild = targetEl.querySelector('i[class*="caret"], .chevron, .icon-down, svg[class*="arrow"]') !== null;
                    const isDropdown = targetTag === 'select' || role.includes('box') || role.includes('menu') || 
                                     targetEl.hasAttribute('aria-haspopup') || targetEl.hasAttribute('aria-expanded') || 
                                     targetCls.includes('select') || targetCls.includes('dropdown') || isCaret || hasCaretChild;

                    if (isDropdown) { cType = "DROPDOWN"; } 
                    else if (targetTag === 'textarea' || (targetTag === 'input' && !['checkbox', 'radio'].includes(targetEl.type))) { cType = "TEXTBOX"; }
                    else if (targetEl.type === 'checkbox' || role === 'checkbox' || targetCls.includes('switch')) { cType = "CHECKBOX"; }

                    if ((targetTag === 'div' || targetTag === 'span') && !isPointer && cType !== "DROPDOWN" && role === "") return;

                    // --- 3. INTENT DISCOVERY (Table Neighbor Fix) ---
                    let intent = (targetEl.placeholder || targetEl.getAttribute('aria-label') || "").trim();
                    let discoveryMethod = "self";

                    if (intent.length < 2) {
                        let neighbor = targetEl.previousElementSibling;
                        if (!neighbor && targetEl.closest('td')) { neighbor = targetEl.closest('td').previousElementSibling; }
                        if (!neighbor) { neighbor = targetEl.parentElement.querySelector('label, .label, span[class*="label"]'); }

                        if (neighbor && neighbor.innerText.trim().length > 1) {
                            intent = neighbor.innerText;
                            discoveryMethod = "proximity";
                        }
                    }

                    if (intent.length < 2) intent = targetEl.innerText || "";
                    intent = intent.split('\\n')[0].trim().replace(/:$/, "");
                    if (intent.length < 2 || intent.toLowerCase() === 'unknown') return;

                    // --- 4. XPATH GENERATION ---
                    let xpath = `//*[contains(text(), "${intent}")]/following::${targetTag}[1]`;
                    if (discoveryMethod === "proximity" && targetEl.closest('tr')) {
                        xpath = `//tr[contains(., "${intent}")]//*[contains(@class, "${targetCls.split(' ')[0]}") or self::input or @role="button"]`;
                    } else if (targetEl.id && isNaN(targetEl.id.slice(-1)) == false) {
                        xpath = `//*[@id="${targetEl.id}"]`;
                    }

                    found.push({
                        intent: intent, component_type: cType, xpath: xpath,
                        discovery_method: discoveryMethod, tag: targetTag,
                        id: targetEl.id || "", placeholder: targetEl.placeholder || "",
                        is_expanded: targetEl.getAttribute('aria-expanded') === 'true',
                        class: targetCls, aria: targetEl.getAttribute('aria-label') || ""
                    });
                } catch (e) {}
            });
            return found;
        """)

    # --- 🧠 CORE ENGINE: THE BRAIN ---

    def _find_locator_weighted(self, user_query):
        """The Brain: NLP Semantic match + Weighted Fuzzy logic."""
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
                'label_text': fuzz.token_sort_ratio(user_query.lower(), el['intent'].lower()),
                'id': fuzz.ratio(user_query.lower(), el['id'].lower())
            }
            weighted_sum = sum(scores[k] * self.WEIGHTS.get(k, 0) for k in scores)

            el_doc = nlp(el['intent'].lower())
            sim = query_doc.similarity(el_doc) if query_doc.vector_norm > 0 else 0
            total = (weighted_sum / 2) + (sim * 50)
            matches.append({"total": total, "element": el})

        matches.sort(key=lambda x: x['total'], reverse=True)
        if matches and matches[0]['total'] >= self.THRESHOLD:
            best = matches[0]['element']

            # 🕵️‍♂️ Trigger the Visual Debugger
            target_el = self.driver.find_element(By.XPATH, best['xpath'])
            self.draw_ai_connection(best['intent'], target_el)
            return best
        return None

    # --- 🏗️ ORCHESTRATION & P2 SELF-HEALING ---

    def draw_ai_connection(self, label_text, target_element):
        """🚀 THE X-RAY: Draws a line from the Label to the identified Element."""
        try:
            self.driver.execute_script("""
                const drawLine = (text, el) => {
                    const label = Array.from(document.querySelectorAll('label, span, td, div'))
                                       .find(e => e.innerText.trim().includes(text));
                    if (!label || !el) return;

                    const rect1 = label.getBoundingClientRect();
                    const rect2 = el.getBoundingClientRect();

                    const canvas = document.createElement('canvas');
                    canvas.id = 'ai_debug_canvas';
                    canvas.style.position = 'fixed';
                    canvas.style.top = '0';
                    canvas.style.left = '0';
                    canvas.style.width = '100%';
                    canvas.style.height = '100%';
                    canvas.style.zIndex = '10000';
                    canvas.style.pointerEvents = 'none';
                    document.body.appendChild(canvas);

                    const ctx = canvas.getContext('2d');
                    canvas.width = window.innerWidth;
                    canvas.height = window.innerHeight;

                    // Draw Circle on Label
                    ctx.beginPath();
                    ctx.arc(rect1.left + rect1.width/2, rect1.top + rect1.height/2, 10, 0, 2 * Math.PI);
                    ctx.strokeStyle = '#ff6b6b';
                    ctx.lineWidth = 3;
                    ctx.stroke();

                    // Draw Line to Element
                    ctx.beginPath();
                    ctx.moveTo(rect1.left + rect1.width/2, rect1.top + rect1.height/2);
                    ctx.lineTo(rect2.left + rect2.width/2, rect2.top + rect2.height/2);
                    ctx.setLineDash([5, 5]);
                    ctx.strokeStyle = '#4ecdc4';
                    ctx.stroke();

                    // Remove after 2 seconds
                    setTimeout(() => canvas.remove(), 2000);
                };
                drawLine(arguments[0], arguments[1]);
            """, label_text, target_element)
        except:
            pass

    def get_step_metadata(self, step_text):
        """🚀 THE P2 ORCHESTRATOR: Uses Memory first, then Heals."""
        params = re.findall(r"[\"'](.*?)[\"']|<(.*?)>|\{(.*?)\}", step_text)
        intents = [next((i for i in g if i), None) for g in params if any(g)]
        results = []
        memory = self._load_memory()

        for intent in intents:
            intent_key = intent.lower()
            meta = None

            # 1. P2 Check: Try Memory (Self-Healing)
            if intent_key in memory:
                try:
                    xpath = memory[intent_key]['xpath']
                    el = self.driver.find_element(By.XPATH, xpath)
                    if el.is_displayed():
                        # ✅ Use the stored component type or infer it from the tag
                        meta = {
                            "xpath": xpath,
                            "intent": intent,
                            "component_type": memory[intent_key].get('component_type', 'BUTTON'),
                            "tag": memory[intent_key].get('tag', 'div')
                        }
                except:
                    print(f"🛠️ UI Changed for '{intent}'. Triggering Healing...")

            # 2. P1 Fallback: Re-Discover and Update Memory
            if not meta:
                meta = self._find_locator_weighted(intent)
                if meta:
                    self._save_memory(intent, meta)

            if meta:
                results.append(meta)
        return results

    def discover_and_map(self):
        """Visualizes the UI Map for Spark POM generation."""
        return self._get_deep_elements()
