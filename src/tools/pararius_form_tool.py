# FILE: ./src/tools/pararius_form_tool.py

import base64  # <-- Re-importing base64 for your function
import datetime
import os
import time

from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


# --- !! STEP 1: RESTORE YOUR ORIGINAL SCREENSHOT FUNCTION !! ---
def save_full_page_screenshot(driver: webdriver.Chrome, out_path: str) -> str:
    """Capture a full-page PNG using Chrome DevTools Protocol only.

    - Reads full content size via Page.getLayoutMetrics
    - Temporarily overrides device metrics to match content size
    - Captures screenshot from surface
    - Clears override and writes PNG to out_path
    Returns out_path.
    """
    try:
        driver.execute_cdp_cmd("Page.enable", {})
    except Exception:
        pass

    metrics = driver.execute_cdp_cmd("Page.getLayoutMetrics", {})
    content = metrics.get("contentSize", {})
    # Use a fixed wide width for good layout, but dynamic height
    width = int(content.get("width", 1400))
    height = int(content.get("height", 1600))

    driver.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride",
        {
            "mobile": False,
            "width": width,
            "height": height,
            "deviceScaleFactor": 1,
            "scale": 1,
        },
    )

    try:
        # Use captureBeyondViewport=True for the full page
        result = driver.execute_cdp_cmd(
            "Page.captureScreenshot",
            {
                "format": "png",
                "fromSurface": True,
                "captureBeyondViewport": True,  # This is the key
            },
        )
        with open(out_path, "wb") as f:
            f.write(base64.b64decode(result["data"]))
    finally:
        try:
            driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})
        except Exception:
            pass

    return out_path


# --- END OF SCREENSHOT FUNCTION ---


# --- 2. Define Input Schema (Pydantic Model) ---
class ParariusFormInput(BaseModel):
    # (Schema is unchanged)
    username: str = Field(description="The user's email address for login.")
    password: str = Field(description="The user's password for login.")
    listing_url: str = Field(description="The exact URL of the Pararius listing contact page.")
    message_body: str = Field(description="The personalized message for the landlord.")
    salutation: str = Field(description="Salutation. '0' for Sir, '1' for Madam.", default="0")
    employment_status: str = Field(
        description="Employment status code (e.g., '3' for Student).", default="3"
    )
    gross_income: str = Field(
        description="Gross income range (e.g., '[1000,1500]').", default="[1000,1500]"
    )
    guarantor: str = Field(description="Guarantor status code (e.g., '3' for abroad).", default="3")
    living_situation: str = Field(
        description="Preferred living situation (e.g., '1' for No).", default="1"
    )
    has_pets: bool = Field(description="User has pets.", default=False)
    start_date: str = Field(
        description="Desired start date in YYYY-MM-DD format.", default="2025-12-01"
    )
    rental_duration: str = Field(
        description="Desired rental duration code (e.g., '5' for 1-2 years).", default="5"
    )
    current_situation: str = Field(
        description="Current housing situation (e.g., 'i_dont_rent_or_own_a_roof_yet').",
        default="i_dont_rent_or_own_a_roof_yet",
    )


class ParariusFormTool(BaseTool):
    name: str = "pararius_login_and_contact_filler"
    description: str = (
        "Logs into Pararius.com using email/password, then navigates to a contact form. "
        "Fills only the motivation by default (keeps profile fields blank), optionally fills "
        "personal contact info if present, and takes a full-page screenshot as proof."
    )
    args_schema: type[BaseModel] = ParariusFormInput

    def _run(
        self,
        username: str,
        password: str,
        listing_url: str,
        message_body: str,
        salutation: str,
        employment_status: str,
        gross_income: str,
        guarantor: str,
        living_situation: str,
        has_pets: bool,
        start_date: str,
        rental_duration: str,
        current_situation: str,
    ) -> str:
        """Login -> Navigate -> Fill (only motivation by default) -> Screenshot."""

        try:
            service = Service(ChromeDriverManager().install())
            options = webdriver.ChromeOptions()

            # --- !! BACK TO HEADLESS MODE !! ---
            # Your CDP screenshot function works best in headless mode.
            # We are betting that the *previous* crash was due to the
            # "element click intercepted" error, which is now fixed.
            options.add_argument("--headless")

            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--window-size=1400,1000")  # Start with a good size

            driver = webdriver.Chrome(service=service, options=options)
            wait = WebDriverWait(driver, 10)  # 10-second wait

        except Exception as e:
            return f"Error initializing WebDriver: {e}."

        try:
            # --- !! STEP 0: HANDLE COOKIE BANNER !! ---
            driver.get("https://www.pararius.com/login")
            print("Browser opened at /login. Looking for cookie banner...")
            try:
                cookie_button_locator = (By.ID, "onetrust-accept-btn-handler")
                cookie_button = wait.until(EC.element_to_be_clickable(cookie_button_locator))
                cookie_button.click()
                print("Cookie banner 'Agree' button clicked.")
                time.sleep(1)
            except TimeoutException:
                print("Cookie banner not found. Assuming it's already accepted.")
            except Exception as e:
                print(f"Warning: Could not close cookie banner. {e}")

            # --- !! STEP 1: LOGIN PROCESS !! ---
            email_button_locator = (By.LINK_TEXT, "Continue with Email")
            email_button = wait.until(EC.element_to_be_clickable(email_button_locator))
            email_button.click()
            print("Clicked 'Continue with Email'.")

            email_field_locator = (By.NAME, "email")
            pass_field_locator = (By.NAME, "password")
            submit_login_locator = (By.XPATH, "//button[@type='submit' and contains(., 'Sign in')]")

            email_field = wait.until(EC.visibility_of_element_located(email_field_locator))
            email_field.send_keys(username)
            print("Filled: Email")

            pass_field = driver.find_element(*pass_field_locator)
            pass_field.send_keys(password)
            print("Filled: Password")

            submit_login_button = driver.find_element(*submit_login_locator)
            submit_login_button.click()
            print("Clicked 'Sign in'. Waiting for login to complete...")

            wait.until(EC.staleness_of(submit_login_button))
            print("Login successful.")

            # --- !! STEP 2: NAVIGATE TO CONTACT FORM !! ---
            print(f"Now navigating to contact form: {listing_url}")
            driver.get(listing_url)

            msg_locator = (By.NAME, "contact_agent_huurprofiel_form[motivation]")
            msg_element = wait.until(EC.visibility_of_element_located(msg_locator))
            print("Contact form loaded successfully.")

            # --- !! STEP 3: FILL THE FORM !! ---
            # Always fill motivation
            msg_element.clear()
            msg_element.send_keys(message_body)
            print("Filled: Motivation")

            # Optionally fill personal contact info (if those fields exist on page)
            _personal_info = {
                "name": "Test Student",
                "email": "test.student@example.com",
                "telephone": "+31600000000",
            }
            for field_name, value in _personal_info.items():
                try:
                    el = driver.find_element(By.NAME, field_name)
                    el.clear()
                    el.send_keys(value)
                    print(f"Filled personal info: {field_name}")
                except Exception:
                    # Field not present; skip silently
                    pass

            # Keep the Pararius profile fields EMPTY unless explicitly requested
            # By default we DO NOT fill profile fields unless required by future schema.

            # --- !! STEP 4: SCREENSHOT (Your Original CDP Method) !! ---
            print("Taking full-page screenshot...")
            time.sleep(1)  # Wait 1 second for UI to settle

            # Extract listing ID from URL for organized storage
            # Example URL: https://www.pararius.com/apartment-for-rent/delft/abc123/contact
            listing_id = listing_url.rstrip('/').split('/')[-2] if '/' in listing_url else 'unknown'
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Save to shared images volume (mounted at /app/images in Docker)
            # Use /app/images for Docker, fallback to ./images for local development
            base_images_path = "/app/images" if os.path.exists("/app/images") else "./images"
            screenshot_folder = os.path.join(base_images_path, listing_id)
            
            if not os.path.exists(screenshot_folder):
                os.makedirs(screenshot_folder, exist_ok=True)

            screenshot_name = os.path.join(screenshot_folder, f"application_{timestamp}.png")

            # Use your provided full-page capture function
            save_full_page_screenshot(driver, screenshot_name)

            print(f"Successfully saved FULL-PAGE screenshot to {screenshot_name}")

            # --- 5. DO NOT SUBMIT ---
            print("Form filling complete. Screenshot taken. Intentionally not submitting.")
            # We don't need to sleep, headless closes instantly
            # time.sleep(2)

            # Return relative path for database storage
            # Convert absolute path to relative path for backend serving
            # /app/images/listing-id/application.png -> images/listing-id/application.png
            relative_path = screenshot_name.replace("/app/images/", "images/").replace("./images/", "images/")
            
            return (
                f"Successfully LOGGED IN and FILLED form for {listing_url}. "
                f"Screenshot saved as {relative_path}."
            )

        except Exception as e:
            # We can't save a screenshot in headless mode if it fails,
            # but we can log the error
            return f"Error during browser automation: {e}."

        finally:
            driver.quit()


# Export a ready-to-use tool instance for the tools package
pararius_form_tool = ParariusFormTool()
