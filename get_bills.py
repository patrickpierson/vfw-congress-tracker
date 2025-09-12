# This script scrapes a list of bills from the VFW VoterVoice website.
# It uses Selenium to handle dynamically loaded content, as the bill list
# is populated by JavaScript after the initial page load.
#
# To run this script, you need to install the required libraries:
# pip install selenium webdriver-manager

import sys
import csv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# Set this to True to enable detailed debugging output.
DEBUG = True

def scrape_vfw_bills():
    """
    Scrapes the list of bills supported by the VFW from their website using Selenium.
    Returns a list of dictionaries, where each dictionary represents a bill
    and contains its title, number, and support status.
    """
    url = "https://votervoice.net/VFW/bills"

    # Set up headless Chrome options for a non-GUI environment
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--log-level=3')

    # Use webdriver-manager to automatically handle the WebDriver installation
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as e:
        print(f"Failed to set up WebDriver: {e}", file=sys.stderr)
        return None

    try:
        if DEBUG:
            print(f"Opening URL with headless browser: {url}")
        driver.get(url)

        # Use WebDriverWait to wait for the dynamic content to appear.
        # This is the key difference from the previous non-working version.
        if DEBUG:
            print("Waiting for the 'jsSpotlightContainer' to be visible...")
        
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CLASS_NAME, "jsSpotlightContainer"))
        )

        if DEBUG:
            print("Container found. Now parsing the page content.")

        # Get the page source after the JavaScript has loaded the content
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')

        bill_container = soup.find('div', class_='jsSpotlightContainer')
        
        if not bill_container:
            print("No bill container with class 'jsSpotlightContainer' found after waiting.")
            return []

        table = bill_container.find('table')

        if not table:
            print("No bill list table found within the container.")
            return []

        bill_rows = table.find_all('tr')
        
        if not bill_rows:
            print("No bills found in the table.")
            return []
        
        if DEBUG:
            print(f"Found {len(bill_rows)} rows. Starting to parse each row.")

        bills = []
        for i, row in enumerate(bill_rows):
            if DEBUG:
                print(f"--- Parsing Row {i+1} ---")
            
            bill_data = {}
            cells = row.find_all('td')
            
            if len(cells) >= 2:
                title_link = cells[0].find('a')
                status_span = cells[1].find('span')
                
                if title_link and status_span:
                    full_title = title_link.get_text(strip=True)
                    
                    parts = full_title.split(':', 1)
                    if len(parts) > 1:
                        bill_data['bill_number'] = parts[0].strip()
                        title = parts[1].strip()
                        session_span = cells[0].find('span')
                        if session_span:
                            title = title.replace(session_span.get_text(strip=True), '').strip()
                        bill_data['bill_title'] = title
                    else:
                        bill_data['bill_number'] = "N/A"
                        bill_data['bill_title'] = full_title
                    
                    status = status_span.get('title', 'N/A')
                    bill_data['status'] = status.replace('We ', '').strip()
            
            if bill_data:
                bills.append(bill_data)
                if DEBUG:
                    print("Extracted Data:")
                    for key, value in bill_data.items():
                        print(f"  {key}: {value}")
        
        if DEBUG:
            print("--- End of Parsing ---")

        return bills

    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        return None
    finally:
        if 'driver' in locals():
            driver.quit()

if __name__ == "__main__":
    vfw_bills = scrape_vfw_bills()

    if vfw_bills:
        filename = "vfw_bills.csv"
        fieldnames = ['bill_number', 'bill_title', 'status']

        try:
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(vfw_bills)
            print(f"\nSuccessfully scraped bills and saved to '{filename}'.")
        except IOError as e:
            print(f"An error occurred while writing to the CSV file: {e}", file=sys.stderr)
    elif vfw_bills is not None:
        print("\nNo bills found on the page.")
    else:
        print("\nFailed to scrape bills. Please check the error message above.")
