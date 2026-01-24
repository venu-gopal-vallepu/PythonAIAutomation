import os
import re
import time
import cv2
import easyocr
import numpy as np
import spacy
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from thefuzz import fuzz

# Load medium model for word vectors
try:
    nlp = spacy.load("en_core_web_md")
except OSError:
    os.system("python -m spacy download en_core_web_md")
    nlp = spacy.load("en_core_web_md")

# Pre-calculate Centroids outside for performance
VIS_CENTROID = nlp("logo branding icon image graphic picture banner").vector
INP_CENTROID = nlp("textbox input field textarea typing entry").vector
ACT_CENTROID = nlp("button link click submit press toggle").vector


class AIAutomationFramework:
    def __init__(self, driver, confidence_threshold=40):
        self.driver = driver
        self.reader = easyocr.Reader(['en'])
        self.screenshot_path = "discovery_view.png"
        self.confidence_threshold = confidence_threshold
        self.locator_repo = set()

        self.WEIGHTS = {
            'id': 1.0, 'name': 0.9, 'alt': 0.9,
            'placeholder': 0.8, 'labelText': 0.8,
            'text': 0.7, 'src': 0.5, 'className': 0.2
        }

    def _is_unstable(self, attr, value):
        if not value or len(value) < 6: return False
        if attr not in ['id', 'name', 'src']: return False
        digits = len(re.findall(r'\d', value))
        return digits > 5 and (digits / len(value) > 0.4)

    def _get_ocr_data(self):
        self.driver.save_screenshot(self.screenshot_path)
        results = self.reader.readtext(self.screenshot_path)
        img = cv2.imread(self.screenshot_path)

        for (bbox, text, prob) in results:
            top_left = tuple(map(int, bbox[0]))
            bottom_right = tuple(map(int, bbox[2]))
            color = (0, 255, 0) if prob > 0.7 else (0, 0, 255)
            cv2.rectangle(img, top_left, bottom_right, color, 2)
            cv2.putText(img, f"{text}", (top_left[0], top_left[1] - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

        cv2.imwrite("debug_ocr_view.png", img)
        return results

    def _calculate_distance(self, ocr_bbox, el_rect):
        ocr_points = np.array(ocr_bbox)
        ocr_center = np.mean(ocr_points, axis=0)
        el_center = [el_rect['x'] + (el_rect['width'] / 2), el_rect['y'] + (el_rect['height'] / 2)]
        return np.linalg.norm(ocr_center - el_center)

    def _verify_locator(self, strategy, selector):
        try:
            element = WebDriverWait(self.driver, 1.5).until(
                EC.visibility_of_element_located((strategy, selector))
            )
            return element if element.is_displayed() and element.is_enabled() else None
        except:
            return None

    def _find_locator_weighted(self, user_step, ocr_results):
        # 1. Centroid-Based Intent Categorization
        user_doc = nlp(user_step.lower())
        u_vec = user_doc.vector

        def cosine_sim(v1, v2):
            return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))

        scores = {
            "visual": cosine_sim(u_vec, VIS_CENTROID),
            "input": cosine_sim(u_vec, INP_CENTROID),
            "action": cosine_sim(u_vec, ACT_CENTROID)
        }
        primary_intent = max(scores, key=scores.get)

        # 2. OCR Anchor Detection
        anchor_box = None
        highest_ocr_score = 0
        for (bbox, text, prob) in ocr_results:
            score = fuzz.partial_ratio(user_step.lower(), text.lower())
            if score > highest_ocr_score and score > 75:
                highest_ocr_score, anchor_box = score, bbox

        # 3. DOM Scraper with Visibility Filtering
        elements = self.driver.execute_script("""
            return Array.from(document.querySelectorAll('input, button, a, img, select, [role="button"], svg')).filter(el => {
                const s = window.getComputedStyle(el);
                return el.offsetWidth > 0 && el.offsetHeight > 0 && s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
            }).map(el => {
                let r = el.getBoundingClientRect();
                let lbl = el.id ? document.querySelector(`label[for="${el.id}"]`) : null;
                return {
                    'tag': el.tagName.toLowerCase(), 'id': el.id, 'name': el.name,
                    'placeholder': el.placeholder || "", 'text': el.innerText || "",
                    'alt': el.alt || "", 'src': el.src || "", 'role': el.getAttribute('role') || "",
                    'labelText': lbl ? lbl.innerText : "",
                    'rect': { 'x': r.left, 'y': r.top, 'width': r.width, 'height': r.height }
                };
            });
        """)

        # 4. Batch Semantic Processing
        identities = [f"{el['tag']} {el['alt']} {el['placeholder']} {el['text']} {el['labelText']}".lower() for el in
                      elements]
        element_docs = list(nlp.pipe(identities))

        matches = []
        for i, el in enumerate(elements):
            semantic_sim = user_doc.similarity(element_docs[i])

            # Apply Dynamic Intent Penalties
            if primary_intent == "visual" and el['tag'] not in ['img', 'svg', 'picture', 'canvas']:
                semantic_sim *= 0.2
            elif primary_intent == "input" and el['tag'] not in ['input', 'textarea', 'select']:
                semantic_sim *= 0.2
            elif primary_intent == "action" and el['tag'] not in ['button', 'a'] and el['role'] != 'button':
                semantic_sim *= 0.2

            # Weighted Attribute Scoring
            attr_score = 0
            for attr, weight in self.WEIGHTS.items():
                val = str(el.get(attr, "")).lower()
                if val:
                    w = 0.05 if self._is_unstable(attr, val) else weight
                    attr_score += (fuzz.partial_ratio(user_step.lower(), val) * w)

            # Proximity Calculation
            proximity_bonus = 0
            if anchor_box:
                dist = self._calculate_distance(anchor_box, el['rect'])
                proximity_bonus = max(0, 100 * (1 - (dist / 500)))

            # Semantic Boost Fallback for Logos
            if not anchor_box and primary_intent == "visual" and el['tag'] in ['img', 'svg']:
                final_score = (attr_score + (semantic_sim * 150))
            else:
                final_score = (attr_score * semantic_sim) + proximity_bonus

            if final_score > self.confidence_threshold:
                matches.append((final_score, el))

        matches.sort(key=lambda x: x[0], reverse=True)

        # 5. Verification Waterfall
        for score, el in matches:
            strategies = []
            if el['id'] and not self._is_unstable('id', el['id']): strategies.append((By.ID, el['id']))
            if el['name']: strategies.append((By.NAME, el['name']))

            if el['tag'] in ['img', 'svg']:
                if el['alt']: strategies.append((By.XPATH, f"//img[@alt='{el['alt']}']"))
                if el['src']:
                    fname = el['src'].split('/')[-1].split('?')[0]
                    if len(fname) > 3: strategies.append((By.XPATH, f"//img[contains(@src, '{fname}')]"))
            elif el['text'] and len(el['text']) < 50:
                strategies.append((By.XPATH, f"//*[contains(text(),'{el['text'][:15]}')]"))

            for strat, val in strategies:
                if self._verify_locator(strat, val): return (strat, val), score
        return None, 0

    def discover_repository(self, steps):
        print(f"\n{'=' * 60}\nAI DISCOVERY ENGINE: CENTROID-VISIBLE MODE\n{'=' * 60}")
        ocr_results = self._get_ocr_data()
        for step in steps:
            loc_info, score = self._find_locator_weighted(step, ocr_results)
            if loc_info:
                self.locator_repo.add(loc_info[1])
                print(f"STEP: {step} | ✅ {loc_info[0]}='{loc_info[1]}' | Score: {score:.2f}")
            else:
                print(f"STEP: {step} | ❌ NOT FOUND")


# --- Test Execution ---
def test_locator_extraction(setup):
    driver = setup['driver']
    try:
        driver.get("https://opensource-demo.orangehrmlive.com/web/index.php/auth/login")
        time.sleep(4)  # Allow React to hydrate
        discovery = AIAutomationFramework(driver)
        discovery.discover_repository([
            "Verify company logo",
            "Enter user name",
            "Enter Password",
            "Click on Login button"
        ])
    finally:
        driver.quit()
