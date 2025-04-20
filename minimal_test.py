# File: minimal_test.py
import requests
import json # To pretty-print the output if successful
import os

# --- HARDCODE the details for this specific test ---
store_url = "https://92c6ce-58.myshopify.com"
product_id = "14885448483140" # An ID that fails in the main script
api_version = "2024-04"

# --- Test WITHOUT API Key first (like your successful curl) ---
print("--- TEST 1: Making request WITHOUT X-Shopify-Access-Token ---")
endpoint = f"/admin/api/{api_version}/products/{product_id}.json"
full_url = f"{store_url.rstrip('/')}{endpoint}"
headers_no_key = {
    # Sending minimal headers, similar to basic curl
    'User-Agent': 'Minimal Python Test Script' # Example User-Agent
}

print(f"Requesting URL: {full_url}")
print(f"Using Headers: {headers_no_key}")

try:
    response_no_key = requests.get(full_url, headers=headers_no_key, timeout=30)
    print(f"\nStatus Code (No Key): {response_no_key.status_code}")
    print("\nResponse Content (No Key - First 500 chars):")
    print(response_no_key.text[:500] + "...")
except Exception as e:
    print(f"\nError during request (No Key): {e}")

print("\n" + "="*40 + "\n")

# --- Test WITH API Key ---
print("--- TEST 2: Making request WITH X-Shopify-Access-Token ---")
# Use the key that worked in your first curl test and that your script loads
api_key = os.getenv("SHOPIFY_API_KEY") # Load from .env via os (make sure .env is correct!)

if not api_key:
    print("SHOPIFY_API_KEY not found in environment for Test 2! Check .env file.")
else:
    headers_with_key = {
        "X-Shopify-Access-Token": api_key,
        "Content-Type": "application/json", # Add standard headers
        "Accept": "application/json",
        'User-Agent': 'Minimal Python Test Script'
    }
    print(f"Requesting URL: {full_url}")
    print(f"Using Headers: {headers_with_key}") # Verify key is present

    try:
        response_with_key = requests.get(full_url, headers=headers_with_key, timeout=30)
        print(f"\nStatus Code (With Key): {response_with_key.status_code}")
        print("\nResponse Content (With Key - First 500 chars):")
        print(response_with_key.text[:500] + "...")

    except Exception as e:
        print(f"\nError during request (With Key): {e}")

print("\n" + "="*40 + "\n")