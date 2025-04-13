import os
import json
import logging
import requests
from flask import Blueprint, request, jsonify, render_template
from shopify_api import fetch_product_by_id
from utils import slugify
from google_sheets import move_done_to_sheet2, export_sales_to_sheet
from export_variants_utils import get_product_option_values, update_product_option_values, apply_translation_method
from google_sheets import get_pending_products_from_sheet
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from threading import Lock
from google_sheets import get_products_pending_translation_from_sheet1, mark_product_translation_done_in_sheet, update_product_status_in_sheet
from post_processing import post_process_description
import time
from bs4 import BeautifulSoup
import html
import re

print("\u2705 export_routes.py loaded and Blueprint registered.")

export_bp = Blueprint("export", __name__)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SHOPIFY_STORES_CONFIG = os.getenv("SHOPIFY_STORES_CONFIG")
SHOPIFY_STORE_URL = os.getenv("SHOPIFY_STORE_URL")
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
GOOGLE_SHEET_ID = "11PVJZkYeZfEtcuXZ7U4xiV1r_axgAIaSe88VgFF189E"

def ensure_https(url):
    url = url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        return f"https://{url}"
    return url

# ---> ADD THIS FUNCTION DEFINITION <---
def get_store_credentials(store_value: str) -> tuple[str | None, str | None]:
    """
    Finds the URL and API key for a given store identifier ('value')
    from the SHOPIFY_STORES_CONFIG environment variable.
    """
    if not SHOPIFY_STORES_CONFIG: # Check if env var is loaded
        logger.error("❌ Environment variable SHOPIFY_STORES_CONFIG is not set.")
        return None, None
    try:
        stores_config = json.loads(SHOPIFY_STORES_CONFIG)
        if not isinstance(stores_config, list):
             logger.error("❌ SHOPIFY_STORES_CONFIG is not a valid JSON list.")
             return None, None

        for store_info in stores_config:
            if isinstance(store_info, dict) and store_info.get("value") == store_value:
                url = ensure_https(store_info.get("shopify_store_url")) # Use ensure_https
                key = store_info.get("shopify_api_key")
                if url and key:
                    logger.info(f"Found credentials for target store value: '{store_value}'")
                    return url, key
                else:
                    logger.error(f"❌ Missing URL or Key for store value '{store_value}' in config.")
                    return None, None
        logger.warning(f"⚠️ Target store value '{store_value}' not found in SHOPIFY_STORES_CONFIG.")
        return None, None
    except json.JSONDecodeError as json_err:
        logger.error(f"❌ Failed to parse JSON from SHOPIFY_STORES_CONFIG: {json_err}")
        return None, None
    except Exception as e:
        logger.exception(f"❌ Error getting credentials for store '{store_value}': {e}")
        return None, None
# ---> END ADDED FUNCTION <---

def extract_name_from_title(title: str) -> str | None:
    """
    Extracts the 'name' part (typically before a separator like '|')
    from a product title string.
    """
    if not title or not isinstance(title, str):
        logger.debug("extract_name_from_title: Input title is empty or not a string.")
        return None
    # Split by common separators: |, –, -
    parts = re.split(r'\s*[\|–\-]\s*', title, maxsplit=1)
    if len(parts) > 1:
        name = parts[0].strip()
        logger.debug(f"extract_name_from_title: Extracted '{name}' from '{title}'")
        return name
    else:
        logger.debug(f"extract_name_from_title: No separator found in '{title}'.")
        return None


def shopify_graphql_request(query, variables, shopify_store_url, shopify_api_key):
    endpoint = f"{ensure_https(shopify_store_url)}/admin/api/2023-04/graphql.json"
    headers = {
        "X-Shopify-Access-Token": shopify_api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "query": query,
        "variables": variables
    }

    response = requests.post(endpoint, json=payload, headers=headers)

    if response.status_code != 200:
        logger.error(f"❌ Shopify GraphQL error: {response.status_code} - {response.text}")
        response.raise_for_status()

    return response.json()

# CORRECTED version in export_routes.py (or shopify_api.py?)
def shopify_api_request(method, url, api_key, **kwargs): # Define api_key parameter
    """
    Generic helper for Shopify REST API requests using a specific key.
    """
    # Pop potential 'json' or 'timeout' from kwargs if they exist
    json_payload = kwargs.pop("json", None)
    timeout = kwargs.pop("timeout", 30) # Default timeout 30s

    # Set headers, using the explicitly passed api_key
    headers = kwargs.pop("headers", {}) # Get any other headers passed via kwargs
    headers["X-Shopify-Access-Token"] = api_key
    headers.setdefault("Content-Type", "application/json")

    # Ensure no unexpected kwargs remain (like api_key itself)
    if 'api_key' in kwargs:
        del kwargs['api_key'] # Remove it if it somehow got passed in kwargs too

    try:
        # Make the request, passing json/timeout explicitly if they existed
        response = requests.request(
            method,
            url,
            headers=headers,
            json=json_payload, # Pass json payload correctly
            timeout=timeout,
            **kwargs # Pass any remaining relevant kwargs (e.g., params)
        )

        # Log non-2xx responses as errors
        if not 200 <= response.status_code < 300:
            logger.error(f"Shopify API error ({method} {url}): {response.status_code} {response.text[:500]}...") # Log more info
        return response
    except requests.exceptions.Timeout:
        logger.error(f"❌ Timeout during Shopify request ({method} {url}) after {timeout}s")
        return None
    except requests.exceptions.RequestException as e:
        logger.exception(f"❌ Network error during Shopify request to {url}: {e}")
        return None
    except Exception as e:
         logger.exception(f"❌ Unexpected error during Shopify request to {url}: {e}")
         return None

# In export_routes.py

# --- Modify this function ---
def update_product_gid_in_sheet(product_id, cloned_gid, cloned_title): # Add cloned_title parameter
    """
    Updates Sheet1 for a given original product ID with the Cloned Product GID (Col E)
    and the Cloned Product Title (Col F).
    """
    # --- ADDED Title Parameter and Update Logic ---
    logger.info(f"Attempting sheet update for Original ID {product_id}: GID='{cloned_gid}', Title='{cloned_title[:50]}...'")
    try:
        # Ensure GSpread/Credentials setup is correct
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(GOOGLE_SHEET_ID).worksheet(SHEET1_NAME) # Use constant

        cell = sheet.find(str(product_id), in_column=1) # Find by Original Product ID in Col A
        if cell:
            row_index = cell.row
            # Prepare batch update data (Col E=5 for GID, Col F=6 for Title)
            update_data = [
                {"range": f"E{row_index}", "values": [[str(cloned_gid or '')]]},
                {"range": f"F{row_index}", "values": [[str(cloned_title or '')]]} # Update Column F
            ]
            logger.debug(f"Found row {row_index} for ID {product_id}. Preparing batch update: {update_data}")
            # Consider adding retry logic here using _retry_gspread_operation if defined/imported
            sheet.batch_update(update_data)
            logger.info(f"✅ Updated Sheet1 Row {row_index} (GID & Cloned Title) for original ID {product_id}.")
            return True
        else:
            logger.warning(f"⚠️ Could not find original product_id={product_id} in '{SHEET1_NAME}' to update cloned info.")
            return False
    except Exception as e:
        logger.exception(f"❌ Error in update_product_gid_in_sheet for Product ID {product_id}: {e}")
        return False
    # --- END MODIFICATION ---


def get_sheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

    try:
        path = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
        logger.info(f"🔐 Using credentials from: {path}")
        creds = ServiceAccountCredentials.from_json_keyfile_name(path, scope)
        return gspread.authorize(creds)

    except Exception as e1:
        logger.warning(f"⚠️ Could not load creds using env path. Reason: {repr(e1)}")
        # Fallback
        try:
            creds = ServiceAccountCredentials.from_service_account_file(
                "/Users/saschavanwell/.config/gspread/service_account.json", scopes=scope
            )
            return gspread.authorize(creds)
        except Exception as e2:
            logger.warning(f"⚠️ Could not load fallback Google Sheets creds either. Reason: {repr(e2)}")
            return None

@export_bp.route("/export")
def export():
    return render_template("export.html")

@export_bp.route("/get_stores", methods=["GET"])
def get_stores():
    try:
        with open("stores.json", "r") as f:
            stores = json.load(f)
        return jsonify(stores)
    except Exception:
        logger.exception("\u274c Failed to load store list.")
        return jsonify({"error": "Failed to load stores"}), 500

def fetch_product_by_handle(handle, shopify_store_url, shopify_api_key):
    url = f"{ensure_https(shopify_store_url)}/admin/api/2023-04/products.json?handle={handle}"
    headers = {
        "X-Shopify-Access-Token": shopify_api_key,
        "Content-Type": "application/json"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        products = response.json().get("products", [])
        return products[0] if products else None
    return None

def get_sold_product_details(start_date, end_date, min_sales):
    logger.info(f"\U0001f9fe Fetching sales from {start_date} to {end_date} with ≥ {min_sales} sales")
    endpoint = (f"{ensure_https(SHOPIFY_STORE_URL)}/admin/api/2023-04/orders.json?status=any"
                f"&created_at_min={start_date}T00:00:00Z"
                f"&created_at_max={end_date}T23:59:59Z"
                f"&fields=line_items")
    headers = {"X-Shopify-Access-Token": SHOPIFY_API_KEY}
    response = requests.get(endpoint, headers=headers)
    if response.status_code != 200:
        logger.error(f"\u274c Failed to fetch orders: {response.status_code}")
        return []

    orders = response.json().get("orders", [])
    counter = {}
    for order in orders:
        for li in order.get("line_items", []):
            pid = li["product_id"]
            t = li["title"]
            key = (pid, t)
            counter[key] = counter.get(key, 0) + 1

    return [{"product_id": pid, "title": title, "sales_count": count} for (pid, title), count in counter.items() if count >= min_sales]

currently_processing_lock = Lock()
currently_processing_ids = set()

SHEET1_NAME = "Sheet1"  # Or your actual name for the main sheet
SHEET2_NAME = "Sheet2"

# In export_routes.py

# --- Ensure required imports like os, json, logging, gspread, ServiceAccountCredentials ---
# --- Ensure constants GOOGLE_CREDENTIALS_FILE, GOOGLE_SHEET_ID, SHEET1_NAME are defined ---

logger = logging.getLogger(__name__) # Ensure logger is defined

def update_cloned_product_info_in_sheet(product_id, cloned_gid, cloned_title, new_status):
    """
    Updates Sheet1 for a given original product ID with the Status (Col D),
    Cloned Product GID (Col E), and Cloned Product Title (Col F).
    """
    if not product_id:
        logger.warning("⚠️ Cannot update sheet, original product_id missing.")
        return False

    log_title = cloned_title[:50] + '...' if cloned_title else '(empty)'
    logger.info(f"Attempting sheet update for Original ID {product_id}: Status='{new_status}', GID='{cloned_gid}', Title='{log_title}'")
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(GOOGLE_SHEET_ID).worksheet(SHEET1_NAME)

        # Find row based on original Product ID (Column A = 1)
        cell = sheet.find(str(product_id), in_column=1) # Use find for efficiency
        if cell:
            row_index = cell.row
            # Prepare batch update data for Status(D), GID(E), Title(F)
            update_data = [
                {"range": f"D{row_index}", "values": [[str(new_status or '')]]},   # Column D
                {"range": f"E{row_index}", "values": [[str(cloned_gid or '')]]},    # Column E
                {"range": f"F{row_index}", "values": [[str(cloned_title or '')]]} # Column F
            ]
            logger.debug(f"Found row {row_index} for ID {product_id}. Batch update: {update_data}")
            # Consider adding retry logic here
            sheet.batch_update(update_data, value_input_option="USER_ENTERED")
            logger.info(f"✅ Updated Sheet1 Row {row_index} (Status, GID, Cloned Title) for original ID {product_id}.")
            return True
        else:
            logger.warning(f"⚠️ Could not find original product_id={product_id} in '{SHEET1_NAME}' to update info/status.")
            return False
    except Exception as e:
        logger.exception(f"❌ Error in update_cloned_product_info_in_sheet for ID {product_id}: {e}")
        return False

def clean_title_output(title):
    """ Cleans final titles: removes extra prefixes, placeholders, punctuation. """
    if not title: return ""

    # Remove prefixes added by some AI models (if post_process_title didn't catch them)
    try:
        prefixes = [r"Neuer Titel:", r"Product Title:", r"Title:", r"Titel:", r"Translated Title:"]
        prefix_pattern = r"^\s*(?:" + "|".join(prefixes) + r")\s*"
        title = re.sub(prefix_pattern, "", title, flags=re.IGNORECASE).strip()
    except Exception as e: logger.error(f"Error removing prefixes in clean_title_output: {e}")

    # Remove wrapping quotes/brackets
    title = re.sub(r'^[\'"“”‘’\[\]\(\){}<>]+|[\'"“”‘’\[\]\(\){}<>]+$', '', title).strip()

    # Remove specific placeholders (add more as needed)
    try:
        placeholders = ["[Produktname]", "[Brand]", "[Marke]"] # Add other languages if seen
        for placeholder in placeholders:
             placeholder_pattern = r"(?i)\s*\[?\s*" + re.escape(placeholder.strip('[] ')) + r"\s*\]?\s*"
             title = re.sub(placeholder_pattern, "", title).strip()
    except Exception as e: logger.error(f"Error removing placeholders in clean_title_output: {e}")

    # Remove parentheses symbols
    title = title.replace('(', '').replace(')', '')

    # Remove common trailing punctuation/symbols & consolidate spaces
    title = title.strip().rstrip(",.;:!?-*")
    title = ' '.join(title.split())

    # Handle incomplete endings (Optional, maybe remove if not needed)
    # incomplete_endings = ("et", "à", "de", "avec", "pour", "en", "sur", "dans")
    # if title and len(title.split()) > 1:
    #    words = title.split(); last_word = words[-1]
    #    if last_word.lower() in incomplete_endings and not title[-1] in ".!?…": title += "..."

    return title.strip()    
    
def post_process_title(ai_output: str) -> str:
    """ Extracts and cleans title, robust to different AI outputs. """
    if not ai_output: return ""
    logger.info(f"🔍 post_process_title Raw: '''{ai_output}'''")

    try: text = BeautifulSoup(ai_output, "html.parser").get_text(separator=' ')
    except Exception: text = ai_output
    text = re.sub(r"\*\*", "", text); text = ' '.join(text.split()).strip()
    logger.info(f"🧼 post_process_title Cleaned: '''{text}'''")

    # ---> Initialize title variable <---
    title = ""

    # Strategy 1: Extract 'Name | Anything', clean trail
    pattern_extract_broad = r"([A-ZÄÖÜ][a-zäöüß]*(?:\s+[A-ZÄÖÜ][a-zäöüß]+)*)\s*\|\s*(.*)"
    match = re.search(pattern_extract_broad, text)
    if match:
        name_part = match.group(1).strip(); product_part_raw = match.group(2).strip()
        # --- Add your trailing junk patterns here ---
        trailing_junk_patterns = [ r"\s*\.?\s*Anpassungen.*$", r"\s*\.?\s*Überarbeitet.*$", r"\s*\.?\s*SEO-Opt.*$", r"\s*\*\*.*$", r"\s*-\s*Struktur.*$", r"\s*-\s*Keyword.*$" ]
        product_part_cleaned = product_part_raw
        for junk_pattern in trailing_junk_patterns: product_part_cleaned = re.sub(junk_pattern, "", product_part_cleaned, flags=re.IGNORECASE).strip()
        product_part_cleaned = product_part_cleaned.strip('"').strip().rstrip('.').strip()
        # --- End junk patterns ---
        if len(name_part)>1 and len(product_part_cleaned) > 3 and len(product_part_cleaned) < 150:
            title = f"{name_part} | {product_part_cleaned}" # Assign valid result
            logger.info(f"✅ post_process_title: Extracted Broadly -> '{title}'")
            return title # Return early on good match

    # Strategy 2: Extract between labels (only if title empty)
    if not title:
        pattern_between = r"(?i)(?:Produkttitel:|Product Title:)\s*(.*?)\s*(?:Kurze Einführung:|Short Introduction:|$)"
        match = re.search(pattern_between, text)
        if match:
             candidate = match.group(1).strip().rstrip(':,')
             logger.info(f"🧩 post_process_title: Matched between labels -> '{candidate}'")
             if len(candidate) > 5 and '|' in candidate: title = candidate # Assign if valid
             else: logger.warning(f"⚠️ Match between labels ignored (format issue): '{candidate}'")
        if title: return title # Return if found

    # Strategy 3: Extract after label (only if title empty)
    if not title:
        pattern_after = r"(?i)(?:Produkttitel:|Product Title:)\s*(.*)"
        match = re.search(pattern_after, text)
        if match:
            candidate = match.group(1).strip().rstrip(':,')
            # Check candidate doesn't contain next label BEFORE assigning
            if not re.search(r"(?i)(Kurze Einführung:|Short Introduction:)", candidate):
                logger.info(f"🧩 post_process_title: Matched after label -> '{candidate}'")
                if len(candidate) > 5 and '|' in candidate: title = candidate # Assign if valid
                else: logger.warning(f"⚠️ Match after label ignored (format issue): '{candidate}'")
            else: logger.warning(f"⚠️ Match after label contained intro label: '{candidate}'")
        if title: return title # Return if found

    # Strategy 4: Final Fallback (only if title still empty)
    if not title:
        common_non_title = r"(?i)(Kurze Einführung|Short Introduction|Vorteile|Advantages)"
        if '|' in text and len(text) < 150 and len(text) > 5 and not re.search(common_non_title, text):
            logger.warning(f"⚠️ post_process_title: No pattern/label matched, using plausible cleaned text: '{text}'")
            title = text # Assign cleaned text
        else:
            logger.error(f"❌ post_process_title: All methods failed. Input: '{text[:100]}...'")
            title = "" # Ensure empty string on total failure

    return title # Return final determined title (could be empty)

def clone_products_to_target_store(product_sales, target_store_info):
    """
    Clones products defined in product_sales (from Sheet1) to the target store.
    Fetches full data from the SOURCE store. Uses CORRECT dictionary keys ('Product ID').
    Updates Sheet1 with Cloned GID and Cloned Title upon success.

    Args:
        product_sales: List of dictionaries from Sheet1 (must contain 'Product ID').
        target_store_info: Dictionary with 'value', 'shopify_store_url', 'shopify_api_key'.

    Returns:
        List of dictionaries containing info about successfully cloned products.
    """
    if not product_sales: # Handle empty input list
        logger.info("No products provided to clone_products_to_target_store.")
        return []

    logger.info(f"Starting cloning process for {len(product_sales)} potential products to target store '{target_store_info['value']}'.")
    created_products = []
    # processed_ids_current_run = set() # Not needed if using global set correctly
    global currently_processing_ids # Access global set

    # === STEP 1: Deduplicate Input (Using CORRECT Key) ===
    seen_ids = set()
    unique_sales = []
    duplicate_input_ids = []
    for p in product_sales:
        pid = str(p.get("Product ID", "")).strip() # Use 'Product ID'
        if not pid: logger.warning(f"Skipping item due to missing 'Product ID': {p}"); continue
        if pid in seen_ids: duplicate_input_ids.append(pid); continue
        seen_ids.add(pid)
        unique_sales.append(p)
    logger.info(f"🧠 Initial deduplication: Received={len(product_sales)}, Unique={len(unique_sales)}, Duplicates skipped={len(duplicate_input_ids)}")
    if duplicate_input_ids: logger.debug(f"🧹 Duplicate input IDs skipped: {duplicate_input_ids}")


    # === STEP 2 & 3: Load Sheets and Filter (Using CORRECT Key) ===
    allowed_ids_sheet1, blocked_ids = set(), set()
    sheet1_cloned_gids = {}
    try:
        # Assuming _get_worksheet helper exists in google_sheets.py or define client/sheet here
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(GOOGLE_SHEET_ID)
        sheet1_records = sheet.worksheet(SHEET1_NAME).get_all_records()
        sheet2_records = sheet.worksheet(SHEET2_NAME).get_all_records()

        for row in sheet1_records:
             pid = str(row.get("Product ID", "")).strip() # Use 'Product ID'
             if not pid: continue
             status = row.get("Status", "").strip().upper()
             cloned_gid = row.get("Cloned Product GID", "").strip()
             if status in ["DONE", "APPROVED"]: blocked_ids.add(pid)
             else: allowed_ids_sheet1.add(pid)
             if cloned_gid: sheet1_cloned_gids[pid] = cloned_gid

        blocked_ids.update(str(row.get("Product ID", "")).strip() for row in sheet2_records if row.get("Product ID")) # Use 'Product ID'
        logger.info(f"📋 Sheets loaded. Allowed: {len(allowed_ids_sheet1)}, Blocked: {len(blocked_ids)}, Already Cloned GID: {len(sheet1_cloned_gids)}")

    except Exception as e:
        logger.exception(f"🔥 Failed loading Google Sheets for filtering: {e}")
        return [] # Return empty on sheet error

    # Filter list based on loaded sets
    pre_filter_count = len(unique_sales)
    products_to_process_initially = [
        p for p in unique_sales
        # Use 'Product ID' with .get() for safety
        if str(p.get("Product ID","")).strip() in allowed_ids_sheet1
        and str(p.get("Product ID","")).strip() not in blocked_ids
        and str(p.get("Product ID","")).strip() not in sheet1_cloned_gids
    ]
    logger.info(f"🧹 Filtered by Sheets from {pre_filter_count} to {len(products_to_process_initially)} items.")


    # === STEP 4: Simultaneous Processing Filter (Using CORRECT Key) ===
    products_to_actually_clone = []
    skipped_concurrent = 0
    with currently_processing_lock:
        for item in products_to_process_initially:
            pid_str = str(item.get("Product ID", "")).strip() # Use 'Product ID'
            if not pid_str: continue

            if pid_str in currently_processing_ids:
                skipped_concurrent += 1
                continue
            products_to_actually_clone.append(item)
            currently_processing_ids.add(pid_str) # Add to set within lock
    logger.info(f"🛡️ Concurrency filter complete: Attempting to clone {len(products_to_actually_clone)}. Skipped {skipped_concurrent}.")


    # === STEP 5: Clone Products (Loop through filtered list) ===
    for item in products_to_actually_clone:
        original_pid_str = str(item.get("Product ID", "")).strip() # Use 'Product ID'
        if not original_pid_str: continue # Should have been filtered, but safe check

        try:
            logger.info(f"--- Cloning Original Product ID: {original_pid_str} ---")

            # Fetch source data using original_pid_str
            source_product_data = fetch_product_by_id(original_pid_str) # Assumes uses SOURCE creds
            if not source_product_data:
                logger.warning(f"⚠️ Could not fetch source data for {original_pid_str}, skipping.")
                update_product_status_in_sheet(original_pid_str, "ERROR_FETCHING_SOURCE")
                continue

            source_title = source_product_data.get("title", "").strip()
            if not source_title:
                 logger.warning(f"⚠️ Source product {original_pid_str} has empty title, skipping.")
                 update_product_status_in_sheet(original_pid_str, "ERROR_EMPTY_SOURCE_TITLE")
                 continue

            # Prepare handle and payload
            cloned_handle = f"{slugify(source_title)}-{original_pid_str[-5:]}"
            logger.info(f"[{original_pid_str}] Generated handle for target: '{cloned_handle}'")

            # Check target handle
            existing_target_product = fetch_product_by_handle(
                cloned_handle, target_store_info["shopify_store_url"], target_store_info["shopify_api_key"]
            )
            if existing_target_product:
                logger.warning(f"⚠️ Handle '{cloned_handle}' already exists in target store. Skipping.")
                update_product_status_in_sheet(original_pid_str, "SKIPPED_HANDLE_EXISTS")
                continue

            # Construct payload (Use your full payload structure)
            product_payload = { "product": { "title": source_title, "body_html": source_product_data.get("body_html", ""), "handle": cloned_handle, "status": "draft", "images": [{"src": img["src"]} for img in source_product_data.get("images", []) if img.get("src")], "options": [{"name": o.get("name", ""), "values": o.get("values", [])} for o in source_product_data.get("options", []) if o.get("name") and o.get("values")], "variants": [ {"option1": v.get("option1"), "option2": v.get("option2"), "option3": v.get("option3"), "price": v.get("price"), "sku": f"CLONE-{original_pid_str}-{v.get('sku', v.get('id', ''))}", "inventory_management": v.get("inventory_management"), "inventory_policy": v.get("inventory_policy"), "requires_shipping": v.get("requires_shipping", True), "weight": v.get("weight"), "weight_unit": v.get("weight_unit")} for v in source_product_data.get("variants", []) ], "product_type": source_product_data.get("product_type", ""), "vendor": source_product_data.get("vendor", ""), "tags": "ClonedForTranslation", }}
            if not product_payload["product"]["options"]: del product_payload["product"]["options"]
            if not product_payload["product"]["variants"]: del product_payload["product"]["variants"]

            # Create product API call
            create_url = f"{ensure_https(target_store_info['shopify_store_url'])}/admin/api/2024-04/products.json"
            # Modified line:
            response = shopify_api_request("POST", create_url, api_key=target_store_info["shopify_api_key"], json=product_payload, timeout=90) # Increased to 90

            # Process Response
            if response and response.status_code in [200, 201]:
                new_product = response.json().get("product")
                if new_product:
                    cloned_product_gid = new_product.get("admin_graphql_api_id")
                    cloned_product_title = new_product.get("title", "")
                    cloned_product_rest_id = new_product.get("id")

                    logger.info(f"✅ Cloned {original_pid_str} to {target_store_info['value']} -> GID: {cloned_product_gid}")
                    created_products.append({ "original_id": original_pid_str, "cloned_id": cloned_product_rest_id, "cloned_gid": cloned_product_gid, "title": cloned_product_title, "handle": new_product.get("handle"), "store": target_store_info["value"] })

                    # Inside clone_products_to_target_store -> try block -> if new_product:

                    # *** Update Sheet1 (Status, GID, Title) using the combined function ***
                    sheet_updated_successfully = update_cloned_product_info_in_sheet(
                        product_id=original_pid_str,
                        cloned_gid=cloned_product_gid,
                        cloned_title=cloned_product_title,
                        new_status="PENDING"  # <-- ADD THIS ARGUMENT
                    )
                    # *** REMOVED the redundant 'if sheet_updated: update_product_status_in_sheet(...)' block ***
                    if not sheet_updated_successfully:
                         # Log if the combined update failed, but don't call status update again
                         logger.error(f"❌ Failed combined sheet update (GID/Title/Status) for {original_pid_str} after cloning.")
                         # Status remains whatever it was before, or consider setting ERROR_SHEET_UPDATE here if needed
                else:
                    logger.error(f"❌ Clone succeeded (Status {response.status_code}) but no product data in response for {original_pid_str}.")
                    update_product_status_in_sheet(original_pid_str, "ERROR_CLONE_RESPONSE")
            else: # Cloning API call failed
                status_code = response.status_code if response else 'N/A'
                err_text = response.text if response else "No response"
                logger.error(f"❌ Cloning failed for {original_pid_str} to store {target_store_info['value']}. Status: {status_code}. Response: {err_text[:500]}")
                update_product_status_in_sheet(original_pid_str, "ERROR_CLONING")

        except Exception as e:
            logger.exception(f"🔥 Exception during cloning loop for product {original_pid_str}: {e}")
            if original_pid_str: update_product_status_in_sheet(original_pid_str, "ERROR_EXCEPTION")

        finally:
            # --- Unlock processing for this ID ---
            # This runs regardless of try/except outcome for IDs processed by this loop
            with currently_processing_lock:
                if original_pid_str in currently_processing_ids:
                    currently_processing_ids.remove(original_pid_str)
                    logger.debug(f"Removed {original_pid_str} from currently_processing_ids after processing.")
                else:
                     # If ID wasn't in the set, log a warning as it might indicate an issue
                     # with how IDs were added in Step 4 vs how the loop is running.
                     logger.warning(f"ID {original_pid_str} was unexpectedly NOT in currently_processing_ids in finally block.")
            # --- End Unlock ---

    logger.info(f"🚩 Cloning phase complete. Successfully created {len(created_products)} product clones in target store this run.")
    return created_products


@export_bp.route("/generate_sales_sheet", methods=["POST"])
def generate_sales_sheet():
    try:
        data = request.get_json()
        start_date = data.get("start_date")
        end_date = data.get("end_date")
        min_sales = int(data.get("min_sales", 1))

        if not start_date or not end_date:
            return jsonify({"error": "Missing start or end date."}), 400

        sales_data = get_sold_product_details(start_date, end_date, min_sales)
        sheet_url = export_sales_to_sheet(sales_data)
        return jsonify({"sheet_url": sheet_url})
    except Exception as e:
        logger.exception("🔥 Error in generate_sales_sheet")
        return jsonify({"error": str(e)}), 500
    
def fetch_product_by_gid(product_gid, shopify_store_url, shopify_api_key):
    query = """
    query getProduct($id: ID!) {
      product(id: $id) {
        id
        title
        bodyHtml
        images(first: 5) {
          edges {
            node {
              src
            }
          }
        }
      }
    }
    """
    variables = {"id": product_gid}

    response = shopify_graphql_request(query, variables, shopify_store_url, shopify_api_key)
    product = response["data"]["product"]

    # Extract image URLs from GraphQL edge structure
    images = product.get("images", {}).get("edges", [])
    product["images"] = [{"src": edge["node"]["src"]} for edge in images]

    return product

def apply_title_constraints(title):
     logger.debug(f"Applying constraints to title: '{title}'")
     MAX_TITLE_WORDS = 15; final_title_constrained = title
     if "|" in title: parts = title.split("|", 1); brand = parts[0].strip(); product_part = parts[1].strip() if len(parts)>1 else ""; product_words = product_part.split();
     if len(product_words) > MAX_TITLE_WORDS: product_part = " ".join(product_words[:MAX_TITLE_WORDS]); final_title_constrained = f"{brand} | {product_part}"
     if len(final_title_constrained) > 255: final_title_constrained = final_title_constrained[:255].rsplit(" ", 1)[0]
     return final_title_constrained.strip()


def update_product_title_and_description(
    product_gid,          # GID of the product to update in target store
    target_store_url,     # URL of the target store
    target_api_key,       # API Key for target store
    target_language,      # Language to translate to
    product_data,         # Pre-fetched data for the product
    title_method,         # Method config/string for title
    desc_method,          # Method config/string for description
    title_prompt="",      # Custom prompt for title
    desc_prompt="",       # Custom prompt for description
    source_lang="auto"    # Source language for Google/DeepL
    # Removed variant arguments
):
    """
    Translates title/description using apply_translation_method, generates handle,
    post-processes the description, and updates the product via GraphQL.

    Returns: True if update successful/not needed, False otherwise.
    """
    logger.info(f"--- [{product_gid}] ENTERING update_product_title_and_description (using apply_translation_method) ---")
    if not product_data: logger.error(f"[{product_gid}] Missing product_data."); return False

    original_title = product_data.get("title", "")
    original_body = product_data.get("bodyHtml", "") # GraphQL key
    original_handle = product_data.get("handle", "")
    # product_rest_id = product_data.get("legacyResourceId") # Not using REST ID anymore

    updates_payload = {"id": product_gid} # Use GID for GraphQL update input ID
    final_processed_title = original_title # Fallback
    title_translation_failed = False
    body_processing_failed = False

    # Determine actual method name strings for logic/logging if config dict passed
    title_method_name = title_method.get("method").lower() if isinstance(title_method, dict) else str(title_method).lower()
    desc_method_name = desc_method.get("method").lower() if isinstance(desc_method, dict) else str(desc_method).lower()


    # --- 1. Translate Title ---
    if title_method_name != 'none':
        try:
            logger.info(f"  [{product_gid}] STEP 1.1: Calling apply_translation_method for title ({title_method_name})...")
            translated_title_raw = apply_translation_method( # Use the imported function
                original_text=original_title,
                method=title_method, # Pass method config/string
                custom_prompt=title_prompt,
                source_lang=source_lang,
                target_lang=target_language,
                field_type="title"
                # Pass product_title=original_title if apply_translation_method needs it for context here
            )
            logger.info(f"  [{product_gid}] STEP 1.2: Raw title result: '{translated_title_raw[:80]}...'")

            if translated_title_raw:
                 # Clean and constrain using helpers
                 # Use post_process_title if needed for robustness (e.g., remove labels if apply_translation_method doesn't)
                 temp_title = post_process_title(translated_title_raw) # Assumes imported
                 cleaned_title = clean_title_output(temp_title) # Assumes imported
                 final_title_constrained = apply_title_constraints(cleaned_title) # Assumes defined/imported
                 processed_title_candidate = final_title_constrained.strip()
                 if processed_title_candidate: final_processed_title = processed_title_candidate
                 else: logger.warning(f"  [{product_gid}] Title empty after cleaning/constraints.")
            else: logger.warning(f"  [{product_gid}] Title translation result empty.")
        except Exception as e:
            logger.exception(f"❌ STEP 1 ERROR: Translating title for {product_gid}")
            title_translation_failed = True
            final_processed_title = original_title # Use original on error
    else:
         logger.info(f"  [{product_gid}] STEP 1: Skipping title translation (method is 'none').")
         final_processed_title = original_title

    logger.info(f"  [{product_gid}] STEP 1.3: Final title for context/update: '{final_processed_title}'")
    if final_processed_title != original_title:
        updates_payload["title"] = final_processed_title # Add 'title' to GraphQL input

    # --- 2. Generate Handle ---
    try:
        logger.info(f"  [{product_gid}] STEP 2.1: Generating handle...")
        if final_processed_title:
            new_handle = slugify(final_processed_title) # Ensure slugify imported
            logger.info(f"  [{product_gid}] Slugify -> Output: '{new_handle}'. Original: '{original_handle}'")
            if new_handle and new_handle != original_handle:
                 updates_payload["handle"] = new_handle # Add 'handle' to GraphQL input
                 logger.info(f"  [{product_gid}] STEP 2.2: Handle added to updates.")
            else: logger.info(f"  [{product_gid}] STEP 2.2: Handle unchanged.")
        else: logger.warning(f"  [{product_gid}] STEP 2.1: Cannot generate handle, title empty.")
    except Exception as e: logger.exception(f"❌ STEP 2 ERROR: Generating handle")

    # --- 3. Translate Description ---
    final_body = original_body # Fallback
    if desc_method_name != 'none':
        try:
            logger.info(f"  [{product_gid}] STEP 3.1: Calling apply_translation_method for desc ({desc_method_name})...")
            translated_description_raw = ""
            if not original_body: logger.warning(f"  [{product_gid}] Original body is empty.")
            else:
                translated_description_raw = apply_translation_method( # Use imported function
                    original_text=original_body,
                    method=desc_method, # Pass method config/string
                    custom_prompt=desc_prompt,
                    source_lang=source_lang,
                    target_lang=target_language,
                    product_title=final_processed_title, # Pass final title for context
                    field_type="description",
                    description=original_body # Pass original body for lang detect if needed
                )
            logger.info(f"  [{product_gid}] STEP 3.2: Raw desc length: {len(translated_description_raw or '')}")

            # --- 4. Post-process Description ---
            if translated_description_raw:
                logger.info(f"  [{product_gid}] STEP 4.1: Calling post_process_description...")
                name_for_desc = extract_name_from_title(final_processed_title) # Ensure imported
                # Ensure post_process_description is imported
                processed_body = post_process_description(
                    original_html=original_body,
                    new_html=translated_description_raw,
                    method=desc_method_name, # Pass method NAME string
                    product_data=product_data,
                    target_lang=target_language,
                    final_product_title=final_processed_title, # Pass final title
                    product_name=name_for_desc # Pass name
                )
                logger.info(f"  [{product_gid}] STEP 4.2: Final body length after post-processing: {len(processed_body or '')}")
                if processed_body and processed_body.strip() != original_body:
                    final_body = processed_body.strip()
                    updates_payload["bodyHtml"] = final_body # Add 'bodyHtml' to GraphQL input
                else: logger.info(f"  [{product_gid}] Body unchanged/empty post-processing.")
            else: logger.warning(f"  [{product_gid}] Raw desc was empty.")

        except Exception as e:
             logger.exception(f"❌ STEP 3/4 ERROR: Translating/processing body for {product_gid}")
             body_processing_failed = True
    else:
        logger.info(f"  [{product_gid}] STEP 3: Skipping description translation (method is 'none').")

    # --- 5. Perform Shopify GraphQL Update ---
    gql_update_success = True # Default true if no update needed
    if len(updates_payload) <= 1 : # Only contains 'id', no actual updates
        logger.info(f"  [{product_gid}] STEP 5.1: No Title/Body/Handle changes needed for GraphQL update.")
    else:
        # Define the GraphQL Mutation
        mutation = """
        mutation productUpdate($input: ProductInput!) {
          productUpdate(input: $input) {
            product { id title handle }
            userErrors { field message }
          }
        }"""
        variables = {"input": updates_payload}

        logger.info(f"  [{product_gid}] STEP 5.1: Sending GraphQL update for fields: {list(updates_payload.keys() - {'id'})}")
        logger.debug(f"  [{product_gid}] Update Payload: {variables}")
        # Ensure shopify_graphql_request helper is imported/defined
        response_json = shopify_graphql_request(mutation, variables, target_store_url, target_api_key)

        # Check GraphQL response
        if (response_json and "data" in response_json and
            response_json["data"].get("productUpdate") and
            not response_json["data"]["productUpdate"].get("userErrors")):
            updated_product_info = response_json["data"]["productUpdate"].get("product")
            logger.info(f"✅ STEP 5.2: Successfully updated product via GraphQL for {product_gid}. New Title: {updated_product_info.get('title')}")
            gql_update_success = True
        else:
            errors = response_json.get("data", {}).get("productUpdate", {}).get("userErrors") if response_json else "No response or data key"
            logger.error(f"❌ STEP 5.2: Failed GraphQL update for {product_gid}. Errors: {errors}")
            gql_update_success = False
    # --- End Update ---

    # Near the end of update_product_title_and_description
    logger.info(f"--- [{product_gid}] EXITING update_product_title_and_description ---")
    # Calculate overall success boolean
    overall_success = gql_update_success and not title_translation_failed and not body_processing_failed
    # Return BOTH the success status AND the final processed title string
    return overall_success, final_processed_title

# --- Main Export Route ---
@export_bp.route("/run_export", methods=["POST"])
def run_export():
    """
    Handles the multi-phase export process:
    1. Review Only: Generate Google Sheet of products meeting sales criteria.
    2. Phase 1: Clone products from source store (using Sheets data) to target store.
    3. Phase 2: Translate cloned products in the target store (using Sheets data).
    Uses environment variables for store config. Correctly handles dict keys.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid request body. Expecting JSON."}), 400
        logger.info(f"Received /run_export request data: {data}")

        # --- Extract parameters ---
        start_date = data.get("start_date")
        end_date = data.get("end_date")
        min_sales = int(data.get("min_sales", 1))
        store_value = data.get("store") # Target store identifier (e.g., "store_es")
        language = data.get("language", "de") # Target language
        source_lang = data.get("source_language", "auto") # Source lang for some APIs

        review_only = data.get("review_only", False)
        run_phase_1 = data.get("run_phase_1", False)
        run_phase_2 = data.get("run_phase_2", False)

        # --- Validation ---
        if not any([review_only, run_phase_1, run_phase_2]):
             return jsonify({"error": "No valid run phase specified (review_only, run_phase_1, or run_phase_2)"}), 400
        if (run_phase_1 or run_phase_2) and not store_value:
            return jsonify({"error": "Missing required field: store (target store value)"}), 400
        if review_only and (not start_date or not end_date):
            return jsonify({"error": "Missing required fields: start_date or end_date for review_only"}), 400

        # --- Get Target Store Credentials (If needed for Phase 1 or 2) ---
        target_store = None
        if run_phase_1 or run_phase_2:
            target_store_url, target_api_key = get_store_credentials(store_value) # Uses helper
            if not target_store_url or not target_api_key:
                error_msg = f"Could not retrieve valid credentials for target store: '{store_value}'. Check SHOPIFY_STORES_CONFIG env var."
                logger.error(error_msg)
                return jsonify({"error": error_msg}), 400
            # Store as dict for passing to helpers
            target_store = {
                "value": store_value,
                "shopify_store_url": target_store_url,
                "shopify_api_key": target_api_key
            }
            logger.info(f"Using credentials for target store: {target_store.get('value')}")

        # --- Execute Phase ---

        # Phase: Review Only (Generate Sheet)
        if review_only:
            logger.info("Executing run_export: review_only phase")
            product_sales = get_sold_product_details(start_date, end_date, min_sales) # Uses SOURCE store creds implicitly
            if product_sales is None: return jsonify({"error": "Failed to retrieve sales data."}), 500
            sheet_url = export_sales_to_sheet(product_sales) # Assumes this uses GOOGLE creds implicitly
            if not sheet_url: return jsonify({"error": "Failed to export sales data to Google Sheet."}), 500
            logger.info(f"Sales sheet generated: {sheet_url}")
            return jsonify({"message": "✅ Sales sheet generated successfully.", "sheet_url": sheet_url})

        # Phase: Clone Only
        elif run_phase_1:
            logger.info("Executing run_export: run_phase_1 (Clone)")
            if not target_store: return jsonify({"error": "Target store credentials missing."}), 500

            # Get products from sheet marked 'PENDING' (check function's exact logic)
            products_to_clone = get_pending_products_from_sheet()
            if products_to_clone is None: return jsonify({"error": "Failed to retrieve products from Google Sheet."}), 500
            if not products_to_clone: return jsonify({"message": "No products found in Sheet1 marked for cloning (e.g., PENDING)."}), 200

            # Call the cloning function (ensure it's imported/defined correctly)
            cloned_products_info = clone_products_to_target_store(products_to_clone, target_store)
            logger.info(f"Cloning phase complete. Cloned {len(cloned_products_info)} products this run.")
            return jsonify({"message": f"✅ Cloning done for {len(cloned_products_info)} products to store '{store_value}'. Check sheet/logs for details.", "products": cloned_products_info })

        # Phase: Translate Only
        elif run_phase_2:
            logger.info("Executing run_export: run_phase_2 (Translate)")
            if not target_store: return jsonify({"error": "Target store credentials missing."}), 500

            # Get translation methods/prompts correctly from JSON 'data'
            translation_methods = data.get("translation_methods", {})
            prompts = data.get("prompts", {})
            title_method = translation_methods.get("title", "google")
            desc_method = translation_methods.get("description", "chatgpt")
            variant_method = translation_methods.get("variants", "google")
            title_prompt = prompts.get("title", "")
            desc_prompt = prompts.get("description", "")
            logger.info(f"Using translation methods - T: {title_method}, D: {desc_method}, V: {variant_method}")

            # Get products pending translation (Status='PENDING', has GID)
            # Ensure get_products_pending_translation_from_sheet1 exists/imported
            products_to_translate = get_products_pending_translation_from_sheet1()
            if products_to_translate is None: return jsonify({"error": "Failed to retrieve products for translation."}), 500
            if not products_to_translate: return jsonify({"message": "No products found in Sheet1 marked PENDING translation with GID."}), 200

            logger.info(f"Found {len(products_to_translate)} products to attempt translation.")
            successful_translations = 0
            translation_errors = 0

            # --- Loop through products ---
            for product_info in products_to_translate:
                # --- Use Correct Keys ---
                original_product_id = product_info.get('Product ID')
                product_gid = product_info.get('Cloned Product GID')

                # Log the data being processed
                logger.info(f"DEBUG: Processing sheet row data: {product_info}") # <-- ADDED LOG

                if not product_gid or not original_product_id:
                    logger.warning(f"Missing GID ('{product_gid}') or Original ID ('{original_product_id}') in sheet row. Skipping.")
                    translation_errors += 1
                    if original_product_id: update_product_status_in_sheet(original_product_id, "ERROR_MISSING_DATA")
                    continue

                logger.info(f"--- [START Phase 2 Processing] GID: {product_gid} (Original ID: {original_product_id}) ---")

                try:
                    # STEP A: Fetch
                    logger.info(f"  [{product_gid}] STEP A: Fetching product data from target store...")
                    cloned_product_data = fetch_product_by_gid(
                        product_gid, target_store["shopify_store_url"], target_store["shopify_api_key"]
                    )

                    # STEP B: Check Fetch
                    if not cloned_product_data:
                        logger.error(f"  [{product_gid}] STEP B FAILED: Fetch returned None. Skipping product.")
                        update_product_status_in_sheet(original_product_id, "ERROR_FETCHING_CLONE")
                        translation_errors += 1
                        continue
                    else:
                         logger.info(f"  [{product_gid}] STEP B SUCCEEDED: Fetch successful. Title: '{cloned_product_data.get('title')}'")

                    # STEP C: Call Title/Desc/Handle Update Function
                    logger.info(f"  [{product_gid}] STEP C: Calling update_product_title_and_description (T:{title_method}, D:{desc_method})...")
                    # Ensure update_product_title_and_description is defined correctly and imported
                    td_success, final_title_from_update = update_product_title_and_description(
                         product_gid=product_gid,
                         target_store_url=target_store["shopify_store_url"],
                         target_api_key=target_store["shopify_api_key"],
                         target_language=language,
                         product_data=cloned_product_data,
                         title_method=title_method,
                         desc_method=desc_method,
                         title_prompt=title_prompt,
                         desc_prompt=desc_prompt,
                         source_lang=source_lang
                    )

                    # STEP D: Log Title/Desc/Handle Update Result
                    logger.info(f"  [{product_gid}] STEP D: Result from update_product_title_and_description: {td_success}")

                    # ---> START REPLACEMENT BLOCK FOR STEP F <---
                    variant_success = True # Assume success unless options exist and translation fails
                    if variant_method != 'none':
                         logger.info(f"  [{product_gid}] STEP F.1: Attempting to fetch options for variant translation ({variant_method})...")
                         # *** CALL get_product_option_values to get correct structure ***
                         # Ensure get_product_option_values is imported from export_variants_utils.py
                         options_to_translate = get_product_option_values(
                               product_gid,
                               shopify_store_url=target_store["shopify_store_url"],
                               shopify_api_key=target_store["shopify_api_key"]
                         )

                         # Check if fetching options failed (returned None)
                         if options_to_translate is None:
                              logger.error(f"  [{product_gid}] STEP F.1 FAILED: Could not fetch options via GraphQL. Skipping variant translation.")
                              variant_success = False # Mark as failure if fetch fails
                         # Check if options list is not empty
                         elif options_to_translate:
                             logger.info(f"  [{product_gid}] STEP F.2: Found {len(options_to_translate)} options. Starting translation loop...")
                             all_options_succeeded = True # Track success for all options of this product
                             # *** ADD LOOP to process each option individually ***
                             for option_data in options_to_translate:
                                 # Basic validation of the option data structure
                                 if not isinstance(option_data, dict) or not option_data.get("id") or not option_data.get("name"):
                                      logger.warning(f"  [{product_gid}] Skipping invalid option data structure: {option_data}")
                                      continue

                                 logger.info(f"  [{product_gid}] STEP F.3: Calling update_product_option_values for Option '{option_data.get('name')}' (ID: {option_data.get('id')})...")
                                 logger.debug(f"  [{product_gid}] Option data passed: {option_data}")
                                 # Ensure update_product_option_values is imported from export_variants_utils.py
                                 single_option_success = update_product_option_values(
                                       product_gid=product_gid,
                                       option=option_data, # Pass SINGLE option dict
                                       target_language=language,
                                       source_language=source_lang,
                                       translation_method=variant_method,
                                       shopify_store_url=target_store["shopify_store_url"],
                                       shopify_api_key=target_store["shopify_api_key"]
                                 )
                                 logger.info(f"  [{product_gid}] STEP F.4: Result for option '{option_data.get('name')}': {single_option_success}")
                                 if not single_option_success:
                                      all_options_succeeded = False
                                      logger.error(f"  [{product_gid}] Update failed for option '{option_data.get('name')}', stopping variant updates for this product.")
                                      break # Stop processing variants for this product if one fails
                             # *** END LOOP ***
                             variant_success = all_options_succeeded # Overall variant success for this product
                         else:
                             # options_to_translate is an empty list []
                             logger.info(f"  [{product_gid}] STEP F.1: Product has no options defined in Shopify.")
                             variant_success = True # No options is not an error
                    else:
                         logger.info(f"  [{product_gid}] STEP F: Skipping variant translation (method is 'none').")
                    # ---> END REPLACEMENT BLOCK FOR STEP F <---


                   # --- NEW STEP G BLOCK (updates status AND title) ---
                    overall_success = td_success and variant_success
                    final_status = "TRANSLATED" if overall_success else "ERROR_TRANSLATING"

                    title_to_write = final_title_from_update

                    logger.info(f"  [{product_gid}] STEP G.1: Overall success: {overall_success}. Preparing sheet update for original ID {original_product_id} with Status='{final_status}' and Title='{title_to_write[:50]}...'")

                    if original_product_id:
                        # Call the function that updates Status, GID, and Title
                        # Make sure this function ('update_cloned_product_info_in_sheet') is defined correctly in this file
                        sheet_updated_successfully = update_cloned_product_info_in_sheet(
                            product_id=original_product_id,
                            cloned_gid=product_gid,       # Pass the GID
                            cloned_title=title_to_write,  # Pass the FINAL title
                            new_status=final_status       # Pass the Status
                        )
                        logger.info(f"  [{product_gid}] STEP G.2: Sheet update call finished (Success: {sheet_updated_successfully}).")
                    else:
                         logger.warning(f"  [{product_gid}] STEP G: Cannot update sheet, original_product_id missing.")
                    # --- End Sheet Update ---

                    # Update counters based on overall success
                    if overall_success: successful_translations += 1; time.sleep(1.5)
                    else: translation_errors += 1

                except Exception as translate_err:
                    # ... (keep existing exception handling) ...
                    # Update counters
                    if overall_success: successful_translations += 1; time.sleep(1.5)
                    else: translation_errors += 1

                except Exception as translate_err:
                     logger.exception(f"❌ Uncaught Exception during translation loop for GID {product_gid}: {translate_err}")
                     translation_errors += 1
                     if original_product_id: update_product_status_in_sheet(original_product_id, "ERROR_EXCEPTION")

                logger.info(f"--- [END Phase 2 Processing] GID: {product_gid} ---")
            # --- End Loop ---

            final_message = f"🌍 Translation phase complete. Attempted: {len(products_to_translate)}. Successful: {successful_translations}. Errors: {translation_errors}."
            logger.info(final_message)
            return jsonify({"message": final_message, "products_translated_count": successful_translations, "errors": translation_errors})

        else:
             # No valid phase specified
             logger.warning("⚠️ No valid run phase (review_only, run_phase_1, run_phase_2) specified.")
             return jsonify({"error": "Invalid run phase specified"}), 400

    except Exception as e:
        logger.exception("🔥 Unhandled Error in /run_export")
        return jsonify({"error": f"An unexpected server error occurred: {str(e)}"}), 500

# --- Add Route for Cleanup ---
@export_bp.route("/cleanup_sheet", methods=["POST"])
def cleanup_sheet():
     """ Endpoint to trigger moving DONE items from Sheet1 to Sheet2 """
     try:
          move_done_to_sheet2() # Call the function from google_sheets.py
          return jsonify({"success": True, "message": "Cleanup process initiated. Check logs."})
     except Exception as e:
          logger.exception("❌ Error triggering sheet cleanup:")
          return jsonify({"error": f"Failed to trigger cleanup: {str(e)}"}), 500

# --- Ensure NO module-level calls like move_done_to_sheet2() here ---