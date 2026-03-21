import os
import re
import time
from selenium.webdriver.common.by import By
from thefuzz import fuzz


class AIAutomationFramework:
    def __init__(self, driver, timeout=10):
        self.driver = driver
        self.timeout = timeout
        # No data-testid? We pivot to User-Centric weights.
        self.WEIGHTS = {
            'aria-label': 1.0,  # Most stable in React/MUI
            'placeholder': 0.9,  # High for text inputs
            'text_intent': 0.8,  # The label text found near the element
            'role': 0.7,  # 'combobox', 'button', 'radio'
            'name': 0.4,  # Often semi-dynamic
            'id': 0.1  # Lowest: Usually dynamic trash (:r0:)
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

    def clean_for_nlp(self, text):
        if not text: return ""
        text = re.sub(r'(?<!^)(?=[A-Z])', ' ', str(text))  # Handle CamelCase
        text = text.replace('_', ' ').replace('-', ' ')
        return re.sub(r'[^a-zA-Z\s]', '', text).lower().strip()

    def _get_deep_elements(self):
        """
        Final Enterprise Scraper: Captures textareas, custom React dropdowns,
        and relates labels to inputs via proximity.
        """
        return self.driver.execute_script("""
            const getSmartXPath = (el) => {
                if (el.getAttribute('aria-label')) return `//*[@aria-label="${el.getAttribute('aria-label')}"]`;
                if (el.placeholder) return `//${el.tagName.toLowerCase()}[@placeholder="${el.placeholder}"]`;
                if (el.name && !/^[0-9]+$/.test(el.name)) return `//${el.tagName.toLowerCase()}[@name="${el.name}"]`;

                const allText = document.querySelectorAll('label, span, p, b, strong');
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
                            closestText = txt.split('\\n')[0].replace(/[":]/g, '');
                        }
                    }
                });

                if (closestText) {
                    return `//*[contains(text(), "${closestText}")]/following::${el.tagName.toLowerCase()}[1]`;
                }
                const allTags = Array.from(document.querySelectorAll(el.tagName.toLowerCase()));
                return `(${el.tagName.toLowerCase()})[${allTags.indexOf(el) + 1}]`;
            };

            const found = [];
            // Expanded Query for React: textarea, combobox, switch, etc.
            const query = 'input, button, select, textarea, [contenteditable="true"], [role="combobox"], [role="listbox"], [role="radio"], [role="checkbox"], [role="switch"], a';

            document.querySelectorAll(query).forEach(el => {
                const rect = el.getBoundingClientRect();
                if (rect.width > 0 || rect.height > 0 || el.isContentEditable) {
                    let role = el.getAttribute('role') || el.type || "";
                    let tag = el.tagName.toLowerCase();

                    // Standardize custom elements
                    if (el.isContentEditable) { tag = 'textarea'; role = 'textbox'; }
                    if (tag === 'div' && (el.className.includes('select') || role === 'combobox')) { tag = 'select'; }

                    found.push({
                        'tag': tag,
                        'id': el.id || "",
                        'name': el.name || "",
                        'aria': el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || "",
                        'placeholder': el.placeholder || (el.getAttribute('data-placeholder') || ""),
                        'text_intent': el.innerText.trim() || "",
                        'role': role,
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
            # 1. Basic Fuzzy Score
            max_fuzzy = 0
            attr_map = {
                'aria-label': el['aria'],
                'placeholder': el['placeholder'],
                'text_intent': el['text_intent'],
                'role': el['role'],
                'name': el.get('name', ""),
                'id': el['id']
            }

            for attr, weight in self.WEIGHTS.items():
                val = attr_map.get(attr, "")
                if val:
                    score = fuzz.token_sort_ratio(clean_intent, self.clean_for_fuzzy(str(val)))
                    max_fuzzy = max(max_fuzzy, score * weight)

            # 2. FROM YOUR SCREENSHOTS: Boost/Penalize logic
            tag, role = el['tag'].lower(), el['role'].lower()

            # Boost form elements, penalize generic links
            adjustment = 0.3 if (tag == 'a' and role != 'button') else 1.2 if (
                    tag in ['input', 'button', 'select', 'textarea'] or role in ['button', 'combobox', 'listbox',
                                                                                 'switch']) else 1.0

            # 3. FROM YOUR SCREENSHOTS: Location Penalty
            penalty = 0.4 if any(
                nav in el['xpath'].lower() for nav in ['header', 'footer', 'nav-menu', 'sidebar']) else 1.0
            penalty = max(penalty, 0.1)  # Your Screenshot Guard

            # 4. NLP Similarity Score
            context_text = self.clean_for_fuzzy(
                f"{el['text_intent']} {el['aria']} {el['placeholder']} {el['role']} {el.get('name', '')}")
            # Calculate similarity between what the user wants and what the element "is"
            sim = user_doc.similarity(nlp(context_text)) if user_doc.vector_norm > 0 else 0.0

            # Final Combined Calculation
            total_score = max_fuzzy * (sim + 0.1) * adjustment * penalty
            matches.append({"total": total_score, "element": el})

        # Sort to get the best match at index 0
        matches.sort(key=lambda x: x['total'], reverse=True)

        if matches and matches[0]['total'] > 10:
            best = matches[0]['element']

            # Map complex tags to simple Spark Assist categories
            if best['role'] in ['combobox', 'listbox'] or best['tag'] == 'select':
                c_type = "DROPDOWN"
            elif any(x in best['role'] for x in ['radio', 'checkbox', 'switch']):
                c_type = "TOGGLE"
            elif best['tag'] in ['button', 'a'] or best['role'] == 'button':
                c_type = "BUTTON"
            else:
                c_type = "TEXTBOX"

            return {
                "intent": intent,
                "component_type": c_type,
                "xpath": best['xpath'],
                "aria": best['aria']
            }

        return None

    def get_step_metadata(self, step_text):
        """Processes the Gherkin line and returns the locator data."""
        results = []
        # Find parameters in <>, "", or {}
        params = re.findall(r"[\"'](.*?)[\"']|<(.*?)>|\{(.*?)\}", step_text)

        for group in params:
            intent = next((item for item in group if item), None)
            if intent:
                meta = self._find_locator_weighted(intent)
                if meta: results.append(meta)

        # Fallback for simple clicks like 'Click Submit'
        if not results:
            match = re.search(r"(?:click|on|select)\s+(?:the\s+)?(\w+)", step_text, re.I)
            if match:
                meta = self._find_locator_weighted(match.group(1))
                if meta: results.append(meta)

        return results
