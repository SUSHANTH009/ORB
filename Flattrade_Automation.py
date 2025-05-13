import logging
import time
import re
import os
import json
import hashlib
import datetime
import requests
from urllib.parse import urlparse, parse_qs
import pyotp
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Default token file path
DEFAULT_TOKEN_FILE = "flattrade_token.json"

class FlattradeLoginAutomation:
    
    def __init__(self, headless=True):
        self.setup_driver(headless)
    
    def setup_driver(self, headless):
        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        
        try:
            self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
            logger.info("Chrome WebDriver initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Chrome WebDriver: {str(e)}")
            raise
    
    def wait_for_element(self, by, value, timeout=15, condition="presence"):
        """Wait for element with explicit condition"""
        try:
            wait = WebDriverWait(self.driver, timeout)
            if condition == "presence":
                element = wait.until(EC.presence_of_element_located((by, value)))
            elif condition == "clickable":
                element = wait.until(EC.element_to_be_clickable((by, value)))
            elif condition == "visible":
                element = wait.until(EC.visibility_of_element_located((by, value)))
            else:
                raise ValueError(f"Invalid wait condition: {condition}")
            
            # Highlight element for debugging
            self.highlight_element(element)
            return element
        except TimeoutException as e:
            logger.error(f"Timed out waiting for element {value} to be {condition}: {str(e)}")
            raise
    
    def highlight_element(self, element, duration=0.5):
        """Highlight an element for visual debugging"""
        try:
            original_style = element.get_attribute("style")
            self.driver.execute_script(
                "arguments[0].setAttribute('style', 'border: 2px solid red; background: yellow');",
                element
            )
            time.sleep(duration)
            self.driver.execute_script(
                f"arguments[0].setAttribute('style', '{original_style}');",
                element
            )
        except Exception as e:
            logger.debug(f"Highlighting element failed: {str(e)}")
    
    def navigate_to_login_page(self, url):
        try:
            logger.info(f"Navigating to {url}")
            self.driver.get(url)
            # Wait for page to load completely
            WebDriverWait(self.driver, 15).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            # Additional wait to ensure all JS is loaded
            time.sleep(3)  # Increased wait time for JS framework to initialize
            logger.info("Login page loaded successfully")
        except Exception as e:
            logger.error(f"Failed to navigate to login page: {str(e)}")
            raise
    
    def fill_input_field_with_vue_handling(self, field_id, value):
        """Special method to handle Vue.js reactive form fields"""
        try:
            # Find the input field
            input_field = self.wait_for_element(By.ID, field_id, condition="visible")
            
            # First try: Direct input
            self.try_direct_input(input_field, value)
            
            # Check if the value was set correctly
            actual_value = input_field.get_attribute("value")
            if actual_value == value:
                logger.info(f"Successfully filled {field_id} with value: {value}")
                return True
            
            # Second try: Clear and input with JavaScript
            logger.info(f"Direct input didn't work for {field_id}, trying JavaScript approach")
            self.try_javascript_input(input_field, value)
            
            # Check again if the value was set
            actual_value = input_field.get_attribute("value")
            if actual_value == value:
                logger.info(f"Successfully filled {field_id} with value using JavaScript: {value}")
                return True
            
            # Third try: Vue.js event dispatching
            logger.info(f"JavaScript input didn't work for {field_id}, trying Vue event dispatch")
            self.try_vue_event_dispatch(input_field, value)
            
            # Final check
            actual_value = input_field.get_attribute("value")
            if actual_value == value:
                logger.info(f"Successfully filled {field_id} with value using Vue events: {value}")
                return True
                
            logger.error(f"Failed to set value for {field_id}. Expected: {value}, Got: {actual_value}")
            return False
            
        except Exception as e:
            logger.error(f"Error filling input field {field_id}: {str(e)}")
            return False
    
    def try_direct_input(self, element, value):
        """Try direct input with various clearing methods"""
        try:
            # First clear using different methods
            element.clear()
            
            # Also try to select all text and delete
            element.send_keys(Keys.CONTROL + "a")
            element.send_keys(Keys.DELETE)
            
            # Now send the value with a slight delay between characters
            for char in value:
                element.send_keys(char)
                time.sleep(0.1)  # Small delay between characters
                
            # Click away to trigger blur event
            self.driver.execute_script("arguments[0].blur();", element)
            time.sleep(0.5)
        except Exception as e:
            logger.warning(f"Direct input failed: {str(e)}")
    
    def try_javascript_input(self, element, value):
        """Try setting value using JavaScript"""
        try:
            # Set value directly and trigger input event
            self.driver.execute_script(f"arguments[0].value = '{value}';", element)
            self.driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", element)
            self.driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", element)
            time.sleep(0.5)
        except Exception as e:
            logger.warning(f"JavaScript input failed: {str(e)}")
    
    def try_vue_event_dispatch(self, element, value):
        """Try manipulating Vue.js component directly"""
        try:
            # More complex Vue.js event simulation
            js_code = f"""
            // Set the value
            arguments[0].value = '{value}';
            
            // Create and dispatch events that Vue is listening for
            var inputEvent = new Event('input', {{ bubbles: true, cancelable: true }});
            arguments[0].dispatchEvent(inputEvent);
            
            // Force Vue to update its internal state
            var changeEvent = new Event('change', {{ bubbles: true }});
            arguments[0].dispatchEvent(changeEvent);
            
            // Try to find the Vue component instance and update it directly
            var el = arguments[0];
            while (el) {{
                if (el.__vue__) {{
                    try {{
                        el.__vue__.$set(el.__vue__, 'value', '{value}');
                        el.__vue__.$forceUpdate();
                    }} catch (e) {{
                        console.error('Vue component update error:', e);
                    }}
                    break;
                }}
                el = el.parentElement;
            }}
            """
            self.driver.execute_script(js_code, element)
            time.sleep(1)  # Wait for Vue to process updates
        except Exception as e:
            logger.warning(f"Vue event dispatch failed: {str(e)}")
    
    def click_button_safely(self, button_id):
        """Click a button with multiple fallback methods"""
        try:
            # Try standard click
            button = self.wait_for_element(By.ID, button_id, condition="clickable")
            button.click()
            logger.info(f"Clicked {button_id} button successfully")
            return True
        except Exception as e:
            logger.warning(f"Standard click failed: {str(e)}")
            try:
                # Try JavaScript click
                button = self.driver.find_element(By.ID, button_id)
                self.driver.execute_script("arguments[0].click();", button)
                logger.info(f"Clicked {button_id} button using JavaScript")
                return True
            except Exception as js_error:
                logger.error(f"JavaScript click also failed: {str(js_error)}")
                # Try to find any button that might be the login button
                try:
                    # Find by text content
                    login_buttons = self.driver.find_elements(By.XPATH, "//button[contains(.,'Login')]")
                    if login_buttons:
                        self.driver.execute_script("arguments[0].click();", login_buttons[0])
                        logger.info("Clicked login button found by text")
                        return True
                    return False
                except Exception:
                    return False
    
    def generate_totp(self, secret):
        try:
            totp = pyotp.TOTP(secret)
            code = totp.now()
            logger.info("TOTP code generated successfully")
            return code
        except Exception as e:
            logger.error(f"Failed to generate TOTP code: {str(e)}")
            raise
    
    def extract_code_from_url(self, url):
        try:
            # Method 1: Using parse_qs
            parsed_url = urlparse(url)
            query_params = parse_qs(parsed_url.query)
            if 'code' in query_params:
                code = query_params['code'][0]
                logger.info("Successfully extracted code from URL using parse_qs")
                return code
            
            # Method 2: Using regex as fallback
            code_match = re.search(r'code=([^&]+)', url)
            if code_match:
                code = code_match.group(1)
                logger.info("Successfully extracted code from URL using regex")
                return code
            
            logger.warning("No code parameter found in URL")
            return None
        except Exception as e:
            logger.error(f"Failed to extract code from URL: {str(e)}")
            return None
    
    def wait_for_url_containing(self, substring, timeout=30):
        start_time = time.time()
        while time.time() - start_time < timeout:
            current_url = self.driver.current_url
            if substring in current_url:
                logger.info(f"URL contains '{substring}': {current_url}")
                return current_url
            time.sleep(0.5)
        
        logger.warning(f"Timed out waiting for URL to contain '{substring}'")
        return None
    
    def login_and_extract_code(self, user_id, password, totp_code=None, totp_secret=None):
        if not totp_code and totp_secret:
            totp_code = self.generate_totp(totp_secret)
        elif not totp_code and not totp_secret:
            logger.error("Either totp_code or totp_secret must be provided")
            return None
        
        try:
            # Wait for login form to be fully loaded
            time.sleep(3)
            
            # Fill User ID - Use the exact ID from the HTML
            user_id_result = self.fill_input_field_with_vue_handling("input-19", user_id)
            if not user_id_result:
                logger.error("Failed to fill User ID field")
                return None
            
            # Fill Password - Use the exact ID from the HTML
            password_result = self.fill_input_field_with_vue_handling("pwd", password)
            if not password_result:
                logger.error("Failed to fill Password field")
                return None
            
            # Fill TOTP - Use the exact ID from the HTML
            totp_result = self.fill_input_field_with_vue_handling("pan", totp_code)
            if not totp_result:
                logger.error("Failed to fill TOTP field")
                return None
            
            # Click the login button - Use the exact ID from the HTML
            if not self.click_button_safely("sbmt"):
                logger.error("Failed to click login button")
                return None
            
            # Wait for redirection containing code
            redirect_url = self.wait_for_url_containing("code=")
            
            if redirect_url:
                # Extract code from redirect URL
                code = self.extract_code_from_url(redirect_url)
                if code:
                    logger.info(f"Successfully extracted code: {code[:5]}...{code[-5:]} (truncated for security)")
                    return code
                else:
                    logger.error("Failed to extract code from redirect URL")
                    return None
            else:
                # Check for error messages
                try:
                    error_elements = self.driver.find_elements(By.CSS_SELECTOR, ".col[style*='color: red;']")
                    for error in error_elements:
                        if error.text.strip():
                            logger.error(f"Login error: {error.text}")
                    
                    # Check if we're still on the login page
                    if "auth.flattrade.in" in self.driver.current_url:
                        logger.error("Still on login page - login unsuccessful")
                    
                    return None
                except Exception as e:
                    logger.error(f"Error checking for login failure: {str(e)}")
                    return None
        
        except Exception as e:
            logger.error(f"Login and code extraction process failed: {str(e)}")
            return None
    
    def close(self):
        """Close the browser"""
        if hasattr(self, 'driver'):
            self.driver.quit()
            logger.info("Browser closed")


def generate_api_token(request_code, api_key, secret_key):
    """Generate API token using the request code"""
    url = "https://authapi.flattrade.in/trade/apitoken"
    api_secret = api_key + request_code + secret_key
    api_secret = hashlib.sha256(api_secret.encode()).hexdigest()
    
    payload = {
        "api_key": api_key, 
        "request_code": request_code, 
        "api_secret": api_secret
    }
    
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            logger.info("Token received successfully")
            return response.json()
        else:
            logger.error(f"Failed to get token: {response.status_code}, {response.text}")
            return None
    except Exception as e:
        logger.error(f"Exception while getting token: {str(e)}")
        return None


def save_token_to_json(token_data, filename=DEFAULT_TOKEN_FILE):
    """Save token data to JSON file with timestamp"""
    try:
        # Add timestamp to token data
        token_data['timestamp'] = datetime.datetime.now().isoformat()
        
        with open(filename, 'w') as f:
            json.dump(token_data, f)
        logger.info(f"Token data saved to {filename}")
        return True
    except Exception as e:
        logger.error(f"Failed to save token data: {str(e)}")
        return False


def check_token_validity(filename=DEFAULT_TOKEN_FILE):
    """
    Check if token file exists and is valid for today
    Returns: 
        - True if token is valid for today
        - False if token is expired or doesn't exist
    """
    # If token file doesn't exist, it's not valid
    if not os.path.exists(filename):
        logger.info("Token file doesn't exist.")
        return False
        
    try:
        # Read the token file
        with open(filename, 'r') as f:
            token_data = json.load(f)
        
        # Check if timestamp exists
        if 'timestamp' not in token_data:
            logger.info("Token file doesn't have timestamp. Considering it invalid.")
            return False
        
        # Parse the timestamp
        token_date = datetime.datetime.fromisoformat(token_data['timestamp']).date()
        
        # If token is from today, it's valid
        today = datetime.datetime.now().date()
        if token_date == today:
            logger.info("Token is valid for today.")
            return True
        else:
            logger.info("Token is from a previous day. Considering it expired.")
            return False
    except Exception as e:
        logger.error(f"Error checking token validity: {str(e)}")
        return False


def get_token(force_refresh=False):
    """
    Get the API token, either from file or by generating a new one.
    
    Args:
        force_refresh (bool): If True, force a token refresh regardless of validity
        
    Returns:
        dict: Token data including the token and timestamp, or None if token retrieval fails
    """
    # If token is valid and we're not forcing refresh, return it from file
    if not force_refresh and check_token_validity():
        try:
            with open(DEFAULT_TOKEN_FILE, 'r') as f:
                token_data = json.load(f)
            logger.info("Retrieved valid token from file")
            return token_data
        except Exception as e:
            logger.error(f"Error reading token file: {str(e)}")
            # If we can't read the file, we'll generate a new token
    
    # If we get here, we need to generate a new token
    logger.info("Generating new token...")
    
    # Your credentials - in production, you should load these from environment variables
    # or a secure configuration store
    USER_ID = "FZ14410"
    PASSWORD = "Ritesh@2003"
    TOTP_CODE = "29102003"
    APIKEY = "916e7d9973c34ab3a97da5ed33800672"
    SECRETKEY = "2025.8ca038c33f034d76a3cae68f21488df6250b838ebaad4264"
    
    login_url = f"https://auth.flattrade.in/?app_key={APIKEY}"
    
    automation = None
    try:
        # Initialize the automation class with headless mode
        automation = FlattradeLoginAutomation(headless=True)
        
        # Navigate to login page
        automation.navigate_to_login_page(login_url)
        
        # Perform login and extract code
        request_code = automation.login_and_extract_code(USER_ID, PASSWORD, TOTP_CODE)
        
        if request_code:
            logger.info("Successfully extracted request code")
            
            # Generate API token using the request code
            token_data = generate_api_token(request_code, APIKEY, SECRETKEY)
            
            if token_data and 'token' in token_data:
                # Save token to JSON file
                save_token_to_json(token_data)
                
                logger.info("Successfully generated and saved token")
                return token_data
            else:
                logger.error("Failed to generate token or token not in response")
                return None
        else:
            logger.error("Failed to extract request code")
            return None
        
    except Exception as e:
        logger.error(f"Token generation failed: {str(e)}")
        return None
    
    finally:
        # Make sure browser is closed properly
        if automation:
            automation.close()


if __name__ == "__main__":
    # When run as a script, simply get the token
    token_data = get_token()
    if token_data and 'token' in token_data:
        print("=" * 50)
        print(f"Token: {token_data['token']}")
        print(f"Generated at: {token_data['timestamp']}")
        print("=" * 50)
    else:
        print("Failed to get token. Check the logs for details.")