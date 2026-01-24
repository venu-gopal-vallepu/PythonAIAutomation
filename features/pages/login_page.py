from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class login_page:
    def __init__(self, driver):
        self.driver = driver
        self.wait = WebDriverWait(driver, 10)

    def user_is_navigated_to_application(self):
        # BDD: User is navigated to application
        # SYSTEM STEP: Manual implementation required.
        pass

    def user_enters_username__admin_(self):
        # BDD: user enters username "Admin"
        self.wait.until(EC.element_to_be_clickable((By.NAME, 'username'))).send_keys('Admin')

    def user_enter_password__admin123_(self):
        # BDD: user enter password "Admin123"
        self.wait.until(EC.element_to_be_clickable((By.NAME, 'password'))).send_keys('Admin123')

    def user_clicks_on_login_button(self):
        # BDD: user clicks on login button
        self.wait.until(EC.element_to_be_clickable((By.XPATH, '//button[contains(normalize-space(.),'Login')]'))).click()

    def login_should_be_successfull(self):
        # BDD: Login should be successfull
        self.wait.until(EC.element_to_be_clickable((By.XPATH, '//button[contains(normalize-space(.),'Login')]'))).click()
