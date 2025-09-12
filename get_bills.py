import sys
import csv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import requests
import json
import configparser
import os

# Set this to True to enable detailed debugging output.
DEBUG = True

def get_api_key():
    """
    Reads the API key from the config.ini file.
    Returns the API key string or None if it's not found.
    """
    config = configparser.ConfigParser()
    config_file_path = 'config.ini'

    if not os.path.exists(config_file_path):
        print(f"Error: The configuration file '{config_file_path}' was not found.")
        return None

    try:
        config.read(config_file_path)
        api_key = config.get('API', 'api_key')
        return api_key
    except (configparser.NoSectionError, configparser.NoOptionError) as e:
        print(f"Error reading config file: {e}")
        return None

def scrape_vfw_bills(api_key):
    """
    Scrapes the list of bills supported by the VFW from their website using Selenium.
    Returns a list of dictionaries, where each dictionary represents a bill
    and contains its title, number, and support status.
    """
    if not api_key:
        print("API key is missing. Aborting scrape.", file=sys.stderr)
        return None

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

                    bill_type, bill_number = split_bill_id(bill_data['bill_number'])
                    cosponsors = get_cosponsors(bill_type, bill_number, api_key)
                    states = get_states_from_json(cosponsors)
                    bill_data['cosponsors'] = states

                    bill_data['url'] = legislation_url(bill_type, bill_number, api_key)
            
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

def split_bill_id(bill_id_str):
    """
    Splits a bill ID string into its type and number.
    
    Args:
        bill_id_str: The input string, e.g., 'H.R. 3132' or 'S. 649'.

    Returns:
        A tuple containing the lowercase bill type ('hr' or 's') and the
        bill number (as a string).
    """
    # Split the string into two parts based on the space
    parts = bill_id_str.split(' ')

    # The first part is the type (e.g., 'H.R.', 'S.')
    bill_type_raw = parts[0]

    # The second part is the number (e.g., '3132', '649')
    bill_number = parts[1]

    # Clean up the bill type: convert to lowercase and remove the period
    bill_type = bill_type_raw.lower().replace('.', '')

    return bill_type, bill_number

def legislation_url(bill_type, bill_number, api_key):
    """
    Fetches the list of cosponsors for a specific bill from the Congress.gov API.

    Args:
        bill_type (str): The type of the bill (e.g., 'hr', 's', 'hres').
        bill_number (int): The number of the bill (e.g., 1).
        api_key (str): Your personal API key for the Congress.gov API.

    Returns:
        string: A url containing the legislation.
    """
    # Construct the base URL using an f-string for easy readability.
    base_url = "https://api.congress.gov/v3/bill/119/{bill_type}/{bill_number}"
    
    # Define the parameters to be sent with the GET request.
    params = {
        'api_key': api_key,
        'format': 'json'  # Explicitly request JSON format.
    }
    # Use a try-except block to handle potential network or API errors.
    try:
        # Make the GET request to the API endpoint.
        print(f"Attempting to fetch data for bill {bill_type.upper()} {bill_number}...")
        response = requests.get(base_url.format(bill_type=bill_type, bill_number=bill_number), params=params)

        # Raise an exception for bad status codes (4xx or 5xx).
        response.raise_for_status()

        # Check if the request was successful (status code 200).
        if response.status_code == 200:
            print("Successfully fetched data.")
            # Parse the JSON response and return it.
            return response.json().get('bill').get('legislationUrl')
        else:
            print(f"Error: API returned status code {response.status_code}")
            return None

    except requests.exceptions.RequestException as e:
        # Handle exceptions related to the request, like connection errors or invalid URLs.
        print(f"An error occurred: {e}")
        return None
    except json.JSONDecodeError:
        # Handle cases where the response is not valid JSON.
        print("Error: Could not decode JSON from the response.")
        return None
    

def get_cosponsors(bill_type, bill_number, api_key):
    """
    Fetches the list of cosponsors for a specific bill from the Congress.gov API.

    Args:
        bill_type (str): The type of the bill (e.g., 'hr', 's', 'hres').
        bill_number (int): The number of the bill (e.g., 1).
        api_key (str): Your personal API key for the Congress.gov API.

    Returns:
        dict: A dictionary containing the JSON data from the API response if successful,
              otherwise None.
    """
    # Construct the base URL using an f-string for easy readability.
    base_url = "https://api.congress.gov/v3/bill/119/{bill_type}/{bill_number}/cosponsors"
    
    # Define the parameters to be sent with the GET request.
    params = {
        'api_key': api_key,
        'format': 'json'  # Explicitly request JSON format.
    }
    
    # Use a try-except block to handle potential network or API errors.
    try:
        # Make the GET request to the API endpoint.
        print(f"Attempting to fetch data for bill {bill_type.upper()} {bill_number}...")
        response = requests.get(base_url.format(bill_type=bill_type, bill_number=bill_number), params=params)

        # Raise an exception for bad status codes (4xx or 5xx).
        response.raise_for_status()

        # Check if the request was successful (status code 200).
        if response.status_code == 200:
            print("Successfully fetched data.")
            # Parse the JSON response and return it.
            return response.json()
        else:
            print(f"Error: API returned status code {response.status_code}")
            return None

    except requests.exceptions.RequestException as e:
        # Handle exceptions related to the request, like connection errors or invalid URLs.
        print(f"An error occurred: {e}")
        return None
    except json.JSONDecodeError:
        # Handle cases where the response is not valid JSON.
        print("Error: Could not decode JSON from the response.")
        return None

def get_states_from_json(json_data):
    """
    Parses a JSON string to extract a list of states.

    Args:
        json_data: A string containing the JSON data.

    Returns:
        A string of comma-separated state abbreviations.
    """
    cosponsors = json_data.get('cosponsors', [])
    states = [cosponsor.get('state') for cosponsor in cosponsors if cosponsor.get('state')]
    unique_states = sorted(list(set(states)))
    return ", ".join(unique_states)

if __name__ == "__main__":
    api_key = get_api_key()
    if api_key:
        vfw_bills = scrape_vfw_bills(api_key)

        if vfw_bills:
            filename = "vfw_bills.csv"
            fieldnames = ['bill_number', 'bill_title', 'status', 'cosponsors', 'url']

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