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
        PROXIMITY & SEMANTIC SCANNER:
        Final Version: Added 'name' attribute and tightened proximity bounds.
        """
        return self.driver.execute_script("""
            const getSmartXPath = (el) => {
                // 1. Stable Attributes (Aria, Placeholder, and now NAME)
                if (el.getAttribute('aria-label')) return `//*[@aria-label="${el.getAttribute('aria-label')}"]`;
                if (el.placeholder) return `//${el.tagName.toLowerCase()}[@placeholder="${el.placeholder}"]`;

                // If the name is a real string (not just a number), use it
                if (el.name && !/^[0-9]+$/.test(el.name)) {
                    return `//${el.tagName.toLowerCase()}[@name="${el.name}"]`;
                }

                // 2. PROXIMITY LOGIC
                const allText = document.querySelectorAll('label, span, p, b, strong');
                let closestText = "";
                let minDistance = 150; // Max radius of 150px
                const elRect = el.getBoundingClientRect();

                allText.forEach(t => {
                    const txt = t.innerText.trim();
                    // Ensure we only grab small labels, not huge paragraphs
                    if (txt.length > 1 && txt.length < 50 && t.children.length === 0) {
                        const tRect = t.getBoundingClientRect();
                        const dist = Math.sqrt(
                            Math.pow(elRect.left - tRect.left, 2) + 
                            Math.pow(elRect.top - tRect.top, 2)
                        );
                        if (dist < minDistance) {
                            minDistance = dist;
                            closestText = txt.split('\\n')[0].replace(/[":]/g, ''); // Clean colon/quotes
                        }
                    }
                });

                // 3. Construct Relative Anchor
                if (closestText) {
                    const tag = el.tagName.toLowerCase();
                    return `//*[contains(text(), "${closestText}")]/following::${tag}[1]`;
                }

                // 4. Fallback: Tag + Index
                const allTags = Array.from(document.querySelectorAll(el.tagName.toLowerCase()));
                return `(${el.tagName.toLowerCase()})[${allTags.indexOf(el) + 1}]`;
            };

            const found = [];
            const query = 'input, button, select, [role="combobox"], [role="radio"], [role="checkbox"], a';
            document.querySelectorAll(query).forEach(el => {
                const rect = el.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                    const role = el.getAttribute('role') || el.type || "";

                    found.push({
                        'tag': el.tagName.toLowerCase(),
                        'id': el.id || "",
                        'name': el.name || "", // <--- CRITICAL: Scrape the 'name' attribute
                        'aria': el.getAttribute('aria-label') || "",
                        'placeholder': el.placeholder || "",
                        'text_intent': el.innerText.trim() || "",
                        'role': role,
                        'xpath': getSmartXPath(el)
                    });
                }
            });
            return found;
        """)

    def _find_locator_weighted(self, intent):
        """
        THE BRAIN: Uses NLP, Fuzzy Matching, and Penalties to find the
        correct element in a React app without data-testids.
        """
        nlp = self._get_nlp()
        elements = self._get_deep_elements()
        clean_intent = self.clean_for_nlp(intent)
        user_doc = nlp(clean_intent)

        matches = []
        for el in elements:
            max_fuzzy = 0
            # Data map from the JavaScript scraper
            attr_map = {
                'aria-label': el['aria'],
                'placeholder': el['placeholder'],
                'text_intent': el['text_intent'],  # Label found near the element
                'role': el['role'],
                'name': el.get('name', ""),
                'id': el['id']
            }

            # 1. ATTR WEIGHTING: Fuzzy match the intent against attributes
            for attr, weight in self.WEIGHTS.items():
                val = attr_map.get(attr, "")
                if val:
                    score = fuzz.token_sort_ratio(clean_intent, self.clean_for_nlp(str(val)))
                    weighted_score = score * weight
                    if weighted_score > max_fuzzy:
                        max_fuzzy = weighted_score

            # 2. THE PENALTY SYSTEM: Restored Scenarios
            penalty = 1.0

            # PENALTY A: Proximity Mismatch
            # If the label we found near the element (e.g. 'Country') doesn't match
            # our Gherkin intent ('Regions'), we penalize it heavily.
            if el['text_intent']:
                label_sim = fuzz.token_sort_ratio(clean_intent, self.clean_for_nlp(el['text_intent']))
                if label_sim < 60:
                    penalty *= 0.5

                    # PENALTY B: Global Navigation (Header/Footer/Sidebar)
            # Demotes elements found in non-main content areas.
            if any(nav in el['xpath'].lower() for nav in ['header', 'footer', 'nav-menu', 'sidebar']):
                # Only penalize if the intent looks like a form interaction
                if any(x in clean_intent for x in ['select', 'type', 'enter', 'input']):
                    penalty *= 0.4

            # PENALTY C: Container vs Leaf
            # Prefer 'select' or 'input' tags over generic 'div' wrappers
            if el['tag'] == 'div' and el['role'] not in ['combobox', 'radio', 'checkbox']:
                penalty *= 0.8

            # 3. NLP CONTEXTUAL SIMILARITY
            # We look at the total "vibe" of the element's metadata
            context_text = self.clean_for_nlp(
                f"{el['text_intent']} {el['aria']} {el['placeholder']} {el['role']} {el.get('name', '')}"
            )
            target_doc = nlp(context_text)
            sim = user_doc.similarity(target_doc) if user_doc.vector_norm > 0 and target_doc.vector_norm > 0 else 0.0

            # 4. FINAL SCORE CALCULATION
            # Combining Fuzzy (60%) and Semantic (40%) and applying Penalty
            total_score = (max_fuzzy * (sim + 0.1)) * penalty
            matches.append({"total": total_score, "element": el})

        # Sort results: Highest score first
        matches.sort(key=lambda x: x['total'], reverse=True)

        # 5. MAPPING TO SPARK COMPONENTS
        if matches and matches[0]['total'] > 10:
            best = matches[0]['element']

            comp_type = "TEXTBOX"  # Default
            if best['role'] in ['combobox', 'listbox', 'dropdown'] or best['tag'] == 'select':
                comp_type = "DROPDOWN"
            elif 'radio' in best['role'] or 'checkbox' in best['role'] or best['tag'] in ['checkbox', 'radio']:
                comp_type = "TOGGLE"
            elif best['tag'] in ['button', 'a'] or best['role'] == 'button':
                comp_type = "BUTTON"

            return {
                "intent": intent,
                "component_type": comp_type,
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
