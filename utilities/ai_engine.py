import os
import re
import time
from selenium.webdriver.common.by import By
from thefuzz import fuzz


class AIAutomationFramework:
    def __init__(self, driver, timeout=10):
        self.driver = driver
        self.timeout = timeout
        # User-Centric weights optimized for React/MUI (No stable IDs)
        self.WEIGHTS = {
            'aria-label': 1.0,
            'placeholder': 0.9,
            'text_intent': 0.8,  # Nearby label text found by JS
            'role': 0.7,
            'name': 0.4,
            'id': 0.1  # Lowest priority for dynamic React IDs
        }
        self._nlp = None

    def _get_nlp(self):
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
        """Cleans strings for better matching (CamelCase, snake_case, etc)."""
        if not text: return ""
        text = re.sub(r'(?<!^)(?=[A-Z])', ' ', str(text))
        text = text.replace('_', ' ').replace('-', ' ')
        return re.sub(r'[^a-zA-Z\s]', '', text).lower().strip()

    def _get_deep_elements(self):
        return self.driver.execute_script("""
            const getSmartXPath = (el) => {
                const tag = el.tagName.toLowerCase();
                const role = el.getAttribute('role') || "";

                // PHASE 2: For Dropdown Items (li/options), use Global Text Anchor
                if (tag === 'li' || role === 'option' || el.className.includes('option')) {
                    const txt = el.innerText.trim();
                    return `//li[contains(normalize-space(), "${txt}")] | //*[contains(@role, "option")][contains(normalize-space(), "${txt}")]`;
                }

                // PHASE 1: For Triggers, use ARIA or Proximity Label
                if (el.getAttribute('aria-label')) return `//*[@aria-label="${el.getAttribute('aria-label')}"]`;

                const allText = document.querySelectorAll('label, span, p, b');
                let closestText = "";
                let minDistance = 150; 
                const elRect = el.getBoundingClientRect();

                allText.forEach(t => {
                    const txt = t.innerText.trim();
                    if (txt.length > 1 && txt.length < 50 && t.children.length === 0) {
                        const tRect = t.getBoundingClientRect();
                        const dist = Math.sqrt(Math.pow(elRect.left - tRect.left, 2) + Math.pow(elRect.top - tRect.top, 2));
                        if (dist < minDistance) {
                            minDistance = dist;
                            closestText = txt.split('\\n')[0].replace(/[":*]/g, '').trim();
                        }
                    }
                });

                return closestText ? `//*[contains(text(), "${closestText}")]/following::${tag}[1]` : `(${tag})[1]`;
            };

            const found = [];
            // Expanded query to catch React Portals and custom selects
            const query = 'input, button, select, textarea, li, [role="option"], [role="combobox"], .MuiSelect-select, a';

            document.querySelectorAll(query).forEach(el => {
                const rect = el.getBoundingClientRect();
                if (rect.width > 0 || rect.height > 0 || el.tagName.toLowerCase() === 'li') {

                    let labelText = "";
                    const labels = document.querySelectorAll('label, span, p');
                    const r = el.getBoundingClientRect();
                    let minDist = 100;

                    labels.forEach(l => {
                        if(l.innerText.trim().length > 1) {
                            const lr = l.getBoundingClientRect();
                            const d = Math.sqrt(Math.pow(r.left-lr.left,2)+Math.pow(r.top-lr.top,2));
                            if(d < minDist) { minDist = d; labelText = l.innerText.trim(); }
                        }
                    });

                    found.append({
                        'tag': el.tagName.toLowerCase(),
                        'id': el.id || "",
                        'text_intent': labelText || el.innerText.trim(),
                        'role': el.getAttribute('role') || el.type || "",
                        'xpath': getSmartXPath(el)
                    });
                }
            });
            return found;
        """)

    def _find_locator_weighted(self, intent):
        nlp = self._get_nlp()
        elements = self._get_deep_elements()
        clean_intent = self.clean_for_fuzzy(intent)
        user_doc = nlp(clean_intent)

        matches = []
        for el in elements:
            # 1. Fuzzy Matching
            max_fuzzy = 0
            attr_map = {
                'aria-label': el.get('aria', ""),
                'placeholder': el.get('placeholder', ""),
                'text_intent': el.get('text_intent', ""),
                'role': el.get('role', ""),
                'name': el.get('name', ""),
                'id': el.get('id', "")
            }

            for attr, weight in self.WEIGHTS.items():
                val = attr_map.get(attr, "")
                if val:
                    score = fuzz.token_sort_ratio(clean_intent, self.clean_for_fuzzy(str(val)))
                    max_fuzzy = max(max_fuzzy, score * weight)

            # 2. Boost/Penalize (React-Aware)
            tag = el['tag'].lower()
            role = (el.get('role') or "").lower()  # Handle None types safely

            # Boost form elements + list items, penalize generic links
            adjustment = 0.3 if (tag == 'a' and 'button' not in role) else 1.2 if (
                    tag in ['input', 'button', 'select', 'textarea', 'li'] or
                    any(r in role for r in ['button', 'combobox', 'listbox', 'switch', 'option'])
            ) else 1.0

            # 3. Location Penalty
            penalty = 0.4 if any(
                nav in el['xpath'].lower() for nav in ['header', 'footer', 'nav-menu', 'sidebar']) else 1.0
            penalty = max(penalty, 0.1)

            # 4. NLP Similarity (The Self-Healing Sauce)
            context_text = self.clean_for_fuzzy(
                f"{el.get('text_intent', '')} {el.get('aria', '')} {el.get('placeholder', '')} {role} {el.get('name', '')}")
            sim = user_doc.similarity(nlp(context_text)) if user_doc.vector_norm > 0 else 0.0

            total_score = max_fuzzy * (sim + 0.1) * adjustment * penalty
            matches.append({"total": total_score, "element": el})

        matches.sort(key=lambda x: x['total'], reverse=True)

        if matches and matches[0]['total'] > 10:
            best = matches[0]['element']
            best_tag = best['tag'].lower()
            best_role = (best.get('role') or "").lower()

            # --- SPARK FINALIZATION MAPPING (The Handshake) ---
            # Explicitly include 'li' and 'option' roles so Spark knows it's a DROPDOWN selection
            if any(r in best_role for r in ['combobox', 'listbox', 'option']) or best_tag in ['select', 'li']:
                c_type = "DROPDOWN"
            elif any(r in best_role for r in ['radio', 'checkbox', 'switch']):
                c_type = "TOGGLE"
            elif best_tag in ['button', 'a'] or 'button' in best_role:
                c_type = "BUTTON"
            else:
                c_type = "TEXTBOX"

            return {
                "intent": intent,
                "component_type": c_type,
                "xpath": best['xpath'],
                "aria": best.get('aria', "")
            }
        return None

    def get_step_metadata(self, step_text):

        results = []

        # 1. Extract all parameters: "Admin", "permission_group", etc.
        # This regex catches text in quotes "", angle brackets <>, or curly braces {}
        params = re.findall(r"[\"'](.*?)[\"']|<(.*?)>|\{(.*?)\}", step_text)

        for group in params:
            # Get the non-empty match from the regex group
            intent = next((item for item in group if item), None)
            if intent:
                # Call the Brain to find the element and identify if it's a DROPDOWN, BUTTON, etc.
                meta = self._find_locator_weighted(intent)
                if meta:
                    results.append(meta)

        if not results:
            match = re.search(r"(?:click|on|select|type|into)\s+(?:the\s+)?(\w+)", step_text, re.I)
            if match:
                meta = self._find_locator_weighted(match.group(1))
                if meta:
                    results.append(meta)

        # P1 Success: Returns a list of locators for Spark to process in sequence
        return results
