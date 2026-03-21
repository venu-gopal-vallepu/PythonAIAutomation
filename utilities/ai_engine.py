import os
import re
import time
import json
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from thefuzz import fuzz


class AIAutomationFramework:
    def __init__(self, driver, timeout=10):
        self.driver = driver
        self.timeout = timeout
        # STABILITY-FIRST WEIGHTS: React IDs are penalized; data-testids are King.
        self.WEIGHTS = {
            'data-testid': 1.0,
            'aria-label': 0.9,
            'role': 0.8,
            'placeholder': 0.7,
            'text_intent': 0.6,
            'name': 0.4,
            'id': 0.1  # Penalized because React IDs are often dynamic/generated
        }
        self._nlp = None

    def _get_nlp(self):
        if self._nlp is None:
            import spacy
            try:
                self._nlp = spacy.load("en_core_web_md")
            except OSError:
                print("Downloading NLP Model (Organization Standard Requirement)...")
                os.system("python -m spacy download en_core_web_md")
                self._nlp = spacy.load("en_core_web_md")
        return self._nlp

    def clean_for_nlp(self, text):
        if not text: return ""
        # Handle CamelCase, underscores, and dashes
        text = re.sub(r'(?<!^)(?=[A-Z])', ' ', str(text))
        text = text.replace('_', ' ').replace('-', ' ')
        return re.sub(r'[^a-zA-Z\s]', '', text).lower().strip()

    def _get_deep_elements(self):
        """
        SCRIPTS: Captures UI metadata.
        Note: Includes logic to detect if an ID looks auto-generated (React/MUI).
        """
        return self.driver.execute_script("""
            const getXPath = (el) => {
                if (el.id && !/^(mui-|id-|:r)/.test(el.id)) return `//*[@id="${el.id}"]`;
                const paths = [];
                for (; el && el.nodeType === 1; el = el.parentNode) {
                    let index = 0;
                    for (let sib = el.previousSibling; sib; sib = sib.previousSibling) {
                        if (sib.nodeType === 1 && sib.tagName === el.tagName) index++;
                    }
                    const tagName = el.tagName.toLowerCase();
                    const pathIndex = index > 0 ? `[${index + 1}]` : "";
                    paths.unshift(tagName + pathIndex);
                }
                return paths.length ? "/" + paths.join("/") : null;
            };

            const results = [];
            const query = 'input, button, select, [role="combobox"], [role="radio"], [role="checkbox"], [data-testid]';
            document.querySelectorAll(query).forEach(el => {
                const rect = el.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                    // Label Discovery Logic
                    let label = "";
                    if (el.id) {
                        const l = document.querySelector(`label[for="${el.id}"]`);
                        label = l ? l.innerText : "";
                    }
                    if (!label) {
                        label = el.closest('div')?.innerText.split('\\n')[0] || el.placeholder || "";
                    }

                    results.push({
                        'tag': el.tagName.toLowerCase(),
                        'id': el.id || "",
                        'data-testid': el.getAttribute('data-testid') || "",
                        'aria': el.getAttribute('aria-label') || el.getAttribute('title') || "",
                        'role': el.getAttribute('role') || "",
                        'placeholder': el.placeholder || "",
                        'text_intent': label.trim(),
                        'xpath': getXPath(el)
                    });
                }
            });
            return results;
        """)

    def _find_locator_weighted(self, intent):
        nlp = self._get_nlp()
        elements = self._get_deep_elements()
        clean_intent = self.clean_for_nlp(intent)
        user_doc = nlp(clean_intent)

        matches = []
        for el in elements:
            max_fuzzy = 0
            attr_map = {
                'data-testid': el['data-testid'],
                'aria-label': el['aria'],
                'role': el['role'],
                'placeholder': el['placeholder'],
                'text_intent': el['text_intent'],
                'name': el.get('name', ""),
                'id': el['id']
            }

            for attr, weight in self.WEIGHTS.items():
                val = attr_map.get(attr, "")
                if val:
                    # Token sort handles "User Name" vs "Name User"
                    score = fuzz.token_sort_ratio(clean_intent, self.clean_for_nlp(str(val)))
                    if (score * weight) > max_fuzzy: max_fuzzy = score * weight

            # Similarity Context
            context_text = self.clean_for_nlp(f"{el['text_intent']} {el['aria']} {el['role']}")
            target_doc = nlp(context_text)
            sim = user_doc.similarity(target_doc) if user_doc.vector_norm > 0 and target_doc.vector_norm > 0 else 0.0

            total_score = max_fuzzy * (sim + 0.1)
            matches.append({"total": total_score, "element": el})

        matches.sort(key=lambda x: x['total'], reverse=True)

        if matches and matches[0]['total'] > 15:  # Confidence Threshold
            best = matches[0]['element']

            # CATEGORIZATION: Tells Spark which BasePage tool to use
            c_type = "TEXTBOX"
            if best['role'] in ['combobox', 'listbox'] or best['tag'] == 'select':
                c_type = "DROPDOWN"
            elif 'radio' in best['role'] or best['tag'] == 'input' and 'radio' in best.get('type', ''):
                c_type = "TOGGLE"

            return {
                "intent": intent,
                "component_type": c_type,
                "data-testid": best['data-testid'],
                "aria": best['aria'],
                "xpath": best['xpath'],
                "id": best['id'] if not re.search(r'(mui-|id-|:r)', best['id']) else ""
            }
        return None

    def get_step_metadata(self, step_text):
        """The entry point for Conftest hooks."""
        results = []
        # Extract anything in quotes, brackets, or braces
        params = re.findall(r"[\"'](.*?)[\"']|<(.*?)>|\{(.*?)\}", step_text)

        for p_group in params:
            intent = next((i for i in p_group if i), None)
            if intent:
                meta = self._find_locator_weighted(intent)
                if meta: results.append(meta)

        # Simple click intent extraction
        if not results:
            action_match = re.search(r"(?:click|select|on)\s+(?:the\s+)?(\w+)", step_text, re.I)
            if action_match:
                meta = self._find_locator_weighted(action_match.group(1))
                if meta: results.append(meta)

        return results