import json
import os
import re
import time
import easyocr
import numpy as np
import spacy
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from thefuzz import fuzz

# --- INITIALIZATION ---
try:
    nlp = spacy.load("en_core_web_md")
except OSError:
    os.system("python -m spacy download en_core_web_md")
    nlp = spacy.load("en_core_web_md")

VIS_CENTROID = nlp("logo branding icon image graphic picture banner").vector
INP_CENTROID = nlp("textbox input field textarea typing entry username password").vector
ACT_CENTROID = nlp("button link click submit press toggle signin login").vector


class AIAutomationFramework:
    def __init__(self, driver, confidence_threshold=40):
        self.driver = driver
        self.reader = easyocr.Reader(['en'])
        self.screenshot_path = "discovery_view.png"
        self.repo_path = "locator_repository.json"
        self.confidence_threshold = confidence_threshold

        self.WEIGHTS = {
            'id': 1.0, 'name': 0.9, 'aria-label': 0.9,
            'alt': 0.8, 'placeholder': 0.8, 'labelText': 0.8,
            'text': 0.7, 'src': 0.5, 'role': 0.4
        }

    def _highlight(self, element, color="#00FF00", duration=1.0):
        original_style = element.get_attribute('style')
        self.driver.execute_script(
            f"arguments[0].setAttribute('style', 'border: 3px solid {color}; box-shadow: 0 0 15px {color};');",
            element
        )
        time.sleep(duration)
        self.driver.execute_script("arguments[0].setAttribute('style', arguments[1]);", element, original_style)

    def _extract_action_data(self, user_step):
        quoted = re.findall(r'"([^"]*)"', user_step)
        if quoted: return quoted[0]
        doc = nlp(user_step)
        for ent in doc.ents:
            return ent.text
        return None

    def _get_deep_elements(self):
        return self.driver.execute_script("""
            const foundElements = [];
            function findRecursive(root) {
                const items = root.querySelectorAll('input, button, a, img, select, textarea, [role="button"], [role="tab"], [role="checkbox"], svg, span, div');
                items.forEach(el => {
                    const s = window.getComputedStyle(el);
                    if (el.offsetWidth > 0 && el.offsetHeight > 0 && s.display !== 'none' && s.visibility !== 'hidden') {
                        let r = el.getBoundingClientRect();
                        let lbl = el.id ? document.querySelector(`label[for="${el.id}"]`) : null;
                        foundElements.push({
                            'tag': el.tagName.toLowerCase(), 'id': el.id, 'name': el.name,
                            'placeholder': el.placeholder || "", 'text': el.innerText || "",
                            'alt': el.alt || "", 'src': el.src || "", 'role': el.getAttribute('role') || "",
                            'aria-label': el.getAttribute('aria-label') || "",
                            'labelText': lbl ? lbl.innerText : "",
                            'rect': { 'x': r.left, 'y': r.top, 'width': r.width, 'height': r.height }
                        });
                    }
                    if (el.shadowRoot) findRecursive(el.shadowRoot);
                });
            }
            findRecursive(document);
            return foundElements;
        """)

    def _get_ocr_data(self):
        self.driver.save_screenshot(self.screenshot_path)
        return self.reader.readtext(self.screenshot_path)

    def _calculate_distance(self, ocr_bbox, el_rect):
        ocr_center = np.mean(np.array(ocr_bbox), axis=0)
        el_center = [el_rect['x'] + (el_rect['width'] / 2), el_rect['y'] + (el_rect['height'] / 2)]
        return np.linalg.norm(ocr_center - el_center)

    def _verify_locator(self, strategy, selector):
        """
        Scans all elements matching the selector and returns the first visible/enabled one.
        """
        try:
            # 1. Find ALL elements matching the strategy
            elements = WebDriverWait(self.driver, 1.2).until(
                EC.presence_of_all_elements_located((strategy, selector))
            )

            # 2. Iterate to find the actual interactive one
            for element in elements:
                if element.is_displayed() and element.is_enabled():
                    return element

            return None
        except:
            return None

    def _is_unstable(self, attr, value):
        if not value or len(value) < 6: return False
        if attr not in ['id', 'name', 'src']: return False
        digits = len(re.findall(r'\d', value))
        return digits > 5 and (digits / len(value) > 0.4)

    def _find_locator_weighted(self, user_step, ocr_results):
        user_doc = nlp(user_step.lower())
        u_vec = user_doc.vector

        def cosine_sim(v1, v2):
            return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))

        scores = {"visual": cosine_sim(u_vec, VIS_CENTROID), "input": cosine_sim(u_vec, INP_CENTROID),
                  "action": cosine_sim(u_vec, ACT_CENTROID)}
        primary_intent = max(scores, key=scores.get)

        anchor_box = None
        for (bbox, text, prob) in ocr_results:
            if fuzz.partial_ratio(user_step.lower(), text.lower()) > 75:
                anchor_box = bbox
                break

        elements = self._get_deep_elements()
        identities = [
            f"{el['tag']} {el['alt']} {el['aria-label']} {el['placeholder']} {el['text']} {el['labelText']}".lower() for
            el in elements]
        element_docs = list(nlp.pipe(identities))

        matches = []
        for i, el in enumerate(elements):
            semantic_sim = user_doc.similarity(element_docs[i])
            if semantic_sim < 0.15: continue

            penalty = 1.0
            if primary_intent == "visual" and el['tag'] not in ['img', 'svg']:
                penalty = 0.2
            elif primary_intent == "input" and el['tag'] not in ['input', 'textarea', 'select']:
                penalty = 0.2
            elif primary_intent == "action" and el['tag'] not in ['button', 'a'] and el['role'] != 'button':
                penalty = 0.2

            adj_semantic = semantic_sim * penalty

            parent_text = self.driver.execute_script("""
                let el = document.elementFromPoint(arguments[0], arguments[1]);
                let p = el ? el.closest('tr, div, section, li, form, [role="gridcell"]') : null;
                return p ? p.innerText.split('\\n').slice(0,2).join(' ') : "";
            """, el['rect']['x'] + 2, el['rect']['y'] + 2)
            parent_bonus = (fuzz.partial_ratio(user_step.lower(), parent_text.lower()) * 0.3) if parent_text else 0

            attr_score = sum(fuzz.partial_ratio(user_step.lower(), str(el.get(k, "")).lower()) * v
                             for k, v in self.WEIGHTS.items() if el.get(k))

            proximity_bonus = 0
            if anchor_box:
                dist = self._calculate_distance(anchor_box, el['rect'])
                proximity_bonus = max(0, 100 * (1 - (dist / 500)))

            final_score = (attr_score * adj_semantic) + proximity_bonus + parent_bonus
            matches.append({"total": round(final_score, 2), "element": el})

        matches.sort(key=lambda x: x['total'], reverse=True)

        for report in matches:
            el = report['element']
            tag, txt, aria = el['tag'], el['text'].strip(), el.get('aria-label', "").strip()
            strategies = []

            if el['id'] and not self._is_unstable('id', el['id']): strategies.append((By.ID, el['id']))
            if el['name']: strategies.append((By.NAME, el['name']))
            if txt:
                strategies.append((By.XPATH, f"//{tag}[normalize-space(.)='{txt}']"))
                strategies.append((By.XPATH, f"//{tag}[contains(normalize-space(.),'{txt[:15]}')]"))
            if aria: strategies.append((By.XPATH, f"//{tag}[@aria-label='{aria}']"))
            if tag in ['img', 'svg'] and el['alt']: strategies.append((By.XPATH, f"//{tag}[@alt='{el['alt']}']"))

            for strat, val in strategies:
                found_el = self._verify_locator(strat, val)
                if found_el:
                    self._highlight(found_el)
                    return {"strategy": strat, "value": val}, report['total']
        return None, 0

    def discover_repository(self, steps):
        repo = {}
        if os.path.exists(self.repo_path):
            with open(self.repo_path, 'r') as f: repo = json.load(f)

        ocr_results = self._get_ocr_data()
        print(f"\n{'=' * 60}\nAI UNIVERSAL ENGINE: EXECUTION START\n{'=' * 60}")

        for step in steps:
            data_val = self._extract_action_data(step)

            if step in repo:
                cached = repo[step]
                found = self._verify_locator(cached['strategy'], cached['value'])
                if found:
                    self._highlight(found, color="#FFFF00", duration=0.5)
                    print(f"STEP: {step} | ✅ CACHE HIT | Data: {data_val}")
                    continue

            loc_info, score = self._find_locator_weighted(step, ocr_results)
            if loc_info:
                repo[step] = {"strategy": loc_info['strategy'], "value": loc_info['value'], "score": score}
                with open(self.repo_path, 'w') as f:
                    json.dump(repo, f, indent=4)
                print(f"STEP: {step} | ✨ DISCOVERED: {loc_info['strategy']}='{loc_info['value']}' | Score: {score}")
            else:
                print(f"STEP: {step} | ❌ NOT FOUND")


# --- TEST EXECUTION BLOCK ---
def test_locator_extraction(setup):
    # Setup WebDriver
    driver = setup['driver']
    try:
        # Navigate
        print("Navigating to OrangeHRM...")
        driver.get("https://opensource-demo.orangehrmlive.com/web/index.php/auth/login")
        time.sleep(5)  # Allow page to settle

        # Initialize and Run
        discovery = AIAutomationFramework(driver)
        discovery.discover_repository([
            "Verify company logo",
                "Enter username as 'Admin'",
            "Type 'admin123' in the password field",
            "Click on Login button"
        ])

        print("\nDiscovery Complete! Check 'locator_repository.json' for results.")

    finally:
        time.sleep(2)
        driver.quit()
