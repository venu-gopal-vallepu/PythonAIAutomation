import easyocr
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from thefuzz import fuzz


class AIAutomationFramework:
    def __init__(self, driver, confidence_threshold=50):
        self.driver = driver
        self.reader = easyocr.Reader(['en'])
        self.screenshot_path = "latest_view.png"
        self.confidence_threshold = confidence_threshold
        # The Set to store unique identified locators
        self.locator_repo = set()

    def _get_ocr_data(self):
        """Captures the visual state for semantic context."""
        self.driver.save_screenshot(self.screenshot_path)
        return self.reader.readtext(self.screenshot_path)

    def _verify_locator(self, strategy, selector):
        """Pings the browser to confirm the element exists."""
        try:
            element = WebDriverWait(self.driver, 2).until(
                EC.presence_of_element_located((strategy, selector))
            )
            return element
        except:
            return None

    def _find_locator_only(self, user_step, ocr_results):
        """Pure Discovery Logic: Matches Step -> OCR -> DOM."""

        # 1. Match User Step to OCR Text
        best_ocr_match = ""
        highest_ocr_score = 0

        for (bbox, text, prob) in ocr_results:
            # Calculate how well this specific OCR text matches the user's step
            current_score = fuzz.partial_ratio(user_step.lower(), text.lower())

            # If this is the best we've seen so far, remember it
            if current_score > highest_ocr_score and current_score > 80:
                highest_ocr_score = current_score
                best_ocr_match = text

        # Now we proceed only with the absolute best visual match found on the screen
        relevant_ocr_text = best_ocr_match

        search_target = relevant_ocr_text if relevant_ocr_text else user_step

        # 2. Enhanced Scraper (Tag independent discovery)
        elements = self.driver.execute_script("""
            return Array.from(document.querySelectorAll('input, button, a, img, select, [role="button"]')).map(el => {
                let parentText = el.parentElement ? el.parentElement.innerText : "";
                return {
                    'tag': el.tagName,
                    'id': el.id,
                    'name': el.name,
                    'className': el.className,
                    'placeholder': el.placeholder || "",
                    'text': el.innerText || "",
                    'alt': el.alt || "",
                    'src': el.src || "",
                    'parentText': parentText
                };
            });
        """)

        matches = []
        for el in elements:
            # Combine all clues for fuzzy matching
            search_blob = f"{el['id']} {el['name']} {el['placeholder']} {el['text']} {el['alt']} {el['src']} {el['parentText']}".lower()
            score = fuzz.partial_ratio(search_target.lower(), search_blob)
            if score > self.confidence_threshold:
                matches.append((score, el))

        matches.sort(key=lambda x: x[0], reverse=True)

        # 3. Try multiple strategies until one is verified
        for score, el in matches:
            strategies = []
            if el['id']: strategies.append((By.ID, el['id']))
            if el['name']: strategies.append((By.NAME, el['name']))

            # XPath fallbacks for tricky elements like logos or specific text
            if el['tag'] == 'IMG' and el['alt']:
                strategies.append((By.XPATH, f"//img[@alt='{el['alt']}']"))
            elif el['text'] and len(el['text']) < 50:
                strategies.append((By.XPATH, f"//*[contains(text(),'{el['text'][:15]}')]"))

            for strat, val in strategies:
                if self._verify_locator(strat, val):
                    return (strat, val), score

        return None, 0

    def discover_all_locators(self, test_steps):
        """Processes all steps and fills the unique locator repository."""
        print(f"\n{'=' * 60}\nSTARTING LOCATOR DISCOVERY PHASE\n{'=' * 60}")

        # Fresh OCR scan
        ocr_results = self._get_ocr_data()

        for step in test_steps:
            print(f"SEARCHING FOR: {step}")
            loc_info, confidence = self._find_locator_only(step, ocr_results)

            if loc_info:
                strategy, selector = loc_info
                # Add to unique set
                self.locator_repo.add((strategy, selector))
                print(f"✅ FOUND: {strategy}='{selector}' (Confidence: {confidence}%)")
            else:
                print(f"❌ NOT FOUND: No stable locator matches this step.")
            print("-" * 60)

        # Final Summary
        print(f"\n{'=' * 60}\nFINAL UNIQUE OBJECT REPOSITORY\n{'=' * 60}")
        for idx, (strat, sel) in enumerate(self.locator_repo, 1):
            print(f"{idx}. {strat}: {sel}")


# --- EXECUTION ---
def test_locator_extraction(setup):
    driver = setup['driver']
    driver.get("https://opensource-demo.orangehrmlive.com/web/index.php/auth/login")
    time.sleep(3)

    framework = AIAutomationFramework(driver)

    # Simple list of elements we want to find
    elements_to_find = [
        "Orange HRM logo",
        "Username",
        "Password",
        "Login button"
    ]

    framework.discover_all_locators(elements_to_find)
