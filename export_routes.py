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

# ---> ADD THIS NEW HELPER FUNCTION <---
def get_online_store_publication_id(shopify_store_url, shopify_api_key):
    """
    Fetches the GraphQL ID of the 'Online Store' publication (sales channel).
    """
    query = """
    query {
      publications(first: 50) {
        edges {
          node {
            id
            name
          }
        }
      }
    }
    """
    variables = {}
    logger.info(f"Attempting to fetch publications for store: {shopify_store_url}")
    try:
        response = shopify_graphql_request(query, variables, shopify_store_url, shopify_api_key)
        if response and "data" in response and "publications" in response["data"]:
            publications = response["data"]["publications"]["edges"]
            for edge in publications:
                node = edge.get("node", {})
                # Common names for the online store channel
                if node.get("name") in ["Online Store", "Onlinestore", "Boutique en ligne"]:
                    pub_id = node.get("id")
                    logger.info(f"✅ Found 'Online Store' publication ID: {pub_id}")
                    return pub_id
            logger.warning("⚠️ 'Online Store' publication channel not found in the first 50 publications.")
            return None
        else:
            logger.error(f"❌ Failed to fetch publications or unexpected response structure: {response}")
            return None
    except Exception as e:
        logger.exception(f"❌ Error fetching publication ID: {e}")
        return None
# ---> END NEW HELPER FUNCTION <---

# ---> ADD THIS FUNCTION DEFINITION <---
# In export_routes.py

# --- MODIFY this function ---
def get_store_credentials(store_value: str) -> dict | None: # <-- Return type changed to dict | None
    """
    Finds the configuration dictionary (including URL, API key, and Pinterest GID)
    for a given store identifier ('value') from the SHOPIFY_STORES_CONFIG
    environment variable.
    """
    if not SHOPIFY_STORES_CONFIG:
        logger.error("❌ Environment variable SHOPIFY_STORES_CONFIG is not set.")
        return None
    try:
        stores_config = json.loads(SHOPIFY_STORES_CONFIG)
        if not isinstance(stores_config, list):
             logger.error("❌ SHOPIFY_STORES_CONFIG is not a valid JSON list.")
             return None

        for store_info in stores_config:
            # Ensure it's a dict and the value matches
            if isinstance(store_info, dict) and store_info.get("value") == store_value:
                # Basic validation of required fields
                url = store_info.get("shopify_store_url")
                key = store_info.get("shopify_api_key")
                # Pinterest GID is optional in the config, handle missing gracefully
                pinterest_gid = store_info.get("pinterest_collection_gid") # Optional

                if url and key:
                    # Ensure URL has https
                    store_info["shopify_store_url"] = ensure_https(url)
                    logger.info(f"Found config for target store value: '{store_value}' (Pinterest GID: {pinterest_gid or 'Not Set'})")
                    return store_info # <-- Return the whole dictionary
                else:
                    logger.error(f"❌ Missing URL or Key for store value '{store_value}' in config.")
                    return None # Invalid entry

        logger.warning(f"⚠️ Target store value '{store_value}' not found in SHOPIFY_STORES_CONFIG.")
        return None # Store value not found
    except json.JSONDecodeError as json_err:
        logger.error(f"❌ Failed to parse JSON from SHOPIFY_STORES_CONFIG: {json_err}")
        return None
    except Exception as e:
        logger.exception(f"❌ Error getting credentials for store '{store_value}': {e}")
        return None
# --- END MODIFICATION ---
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

# In export_routes.py

# --- Modify this function ---
def update_cloned_product_info_in_sheet(product_id, cloned_gid, cloned_title, new_status, target_store): # <-- ADD target_store parameter
    """
    Updates Sheet1 for a given original product ID with the Status (Col D),
    Cloned Product GID (Col E), Cloned Product Title (Col F), and Target Store (Col G).
    """
    if not product_id:
        logger.warning("⚠️ Cannot update sheet, original product_id missing.")
        return False

    log_title = cloned_title[:50] + '...' if cloned_title else '(empty)'
    # Update log message
    logger.info(f"Attempting sheet update for Original ID {product_id}: Status='{new_status}', GID='{cloned_gid}', Title='{log_title}', TargetStore='{target_store}'")
    try:
        # Use helper to get client/sheet - assuming _get_worksheet exists and works
        # You might need to adapt this if _get_worksheet isn't defined in this file
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(GOOGLE_SHEET_ID).worksheet(SHEET1_NAME)
        # Alternatively, if you have a _get_worksheet helper defined in this file:
        # sheet = _get_worksheet(SHEET1_NAME)
        if not sheet:
             logger.error("Failed to get worksheet object in update_cloned_product_info_in_sheet.")
             return False


        # Find row based on original Product ID (Column A = 1)
        # Assuming _retry_gspread_operation is available or handle errors directly
        # cell = _retry_gspread_operation(sheet.find, str(product_id), in_column=1) # If using retry helper
        cell = sheet.find(str(product_id), in_column=1) # Without retry helper for simplicity here

        if cell:
            row_index = cell.row
            # Define column indices (1-based for range)
            status_col = 4       # D
            gid_col = 5          # E
            title_col = 6        # F
            target_store_col = 7 # G <-- New Column

            # Prepare batch update data for Status(D), GID(E), Title(F), Target Store(G)
            update_data = [
                {"range": gspread.utils.rowcol_to_a1(row_index, status_col),       "values": [[str(new_status or '')]]},
                {"range": gspread.utils.rowcol_to_a1(row_index, gid_col),          "values": [[str(cloned_gid or '')]]},
                {"range": gspread.utils.rowcol_to_a1(row_index, title_col),        "values": [[str(cloned_title or '')]]},
                {"range": gspread.utils.rowcol_to_a1(row_index, target_store_col), "values": [[str(target_store or '')]]} # <-- ADDED Target Store update
            ]
            # Update log message
            logger.debug(f"Found row {row_index} for ID {product_id}. Batch update: Status, GID, Title, Target Store")
            # _retry_gspread_operation(sheet.batch_update, update_data, value_input_option="USER_ENTERED") # If using retry helper
            sheet.batch_update(update_data, value_input_option="USER_ENTERED") # Without retry helper

            # Update log message
            logger.info(f"✅ Updated Sheet1 Row {row_index} (Status, GID, Cloned Title, Target Store) for original ID {product_id}.")
            return True
        else:
            logger.warning(f"⚠️ Could not find original product_id={product_id} in '{SHEET1_NAME}' to update info/status.")
            return False
    except Exception as e:
        # Update log message
        logger.exception(f"❌ Error in update_cloned_product_info_in_sheet for ID {product_id} (Target: {target_store}): {e}")
        return False

# --- END MODIFICATION ---

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

# In export_routes.py

# --- Modify this function ---
# In export_routes.py

# In export_routes.py

# --- Ensure required imports like gspread, ServiceAccountCredentials, Lock etc. are present ---
# --- Ensure constants like GOOGLE_CREDENTIALS_FILE, GOOGLE_SHEET_ID, SHEET1_NAME are defined ---

# --- CORRECTED & IMPROVED function ---
def clone_products_to_target_store(
    product_sales,
    target_store_info,               # Dict with url, key, value
    # online_store_publication_id=None, # Optional: Keep if needed elsewhere, but not used here
    # pinterest_collection_gid=None,   # Optional: Keep if needed elsewhere, but not used here
    pinterest_collection_rest_id=None # USE THIS for REST collection add
    ):
    """
    Clones products via REST, sets status=ACTIVE, published=True,
    and adds to Pinterest collection via REST Collects endpoint.
    Filters products based ONLY on Sheet1 status and GID presence.
    Handles concurrency. Keeps GID handling for sheet updates/Phase 2.

    Args:
        product_sales: List of dictionaries from input source ('Product ID').
        target_store_info: Dictionary with store config (url, api_key, value).
        pinterest_collection_rest_id: REST ID for the target collection.
    """
    # --- Initial Setup ---
    target_store_url = target_store_info.get("shopify_store_url")
    target_api_key = target_store_info.get("shopify_api_key")
    target_store_value = target_store_info.get("value", "UNKNOWN")

    if not target_store_url or not target_api_key:
         logger.error("❌ Missing shopify_store_url or shopify_api_key in target_store_info.")
         return []
    if not product_sales:
        logger.info("No products provided to clone_products_to_target_store.")
        return []

    logger.info(f"Starting REST-based cloning process for {len(product_sales)} potential products to target store '{target_store_value}'.")
    created_products = []
    global currently_processing_ids # Use global lock correctly

    # === Step 1: Deduplication ===
    seen_ids = set()
    unique_sales = []
    duplicate_input_ids = []
    for p in product_sales:
        # Ensure p is a dictionary and has 'Product ID'
        if not isinstance(p, dict):
             logger.warning(f"Skipping non-dictionary item in product_sales: {p}")
             continue
        pid = str(p.get("Product ID", "")).strip() # Use 'Product ID'
        if not pid: logger.warning(f"Skipping item due to missing 'Product ID': {p}"); continue
        if pid in seen_ids: duplicate_input_ids.append(pid); continue
        seen_ids.add(pid)
        unique_sales.append(p)
    logger.info(f"🧠 Initial deduplication: Input={len(product_sales)}, Unique={len(unique_sales)}, Duplicates skipped={len(duplicate_input_ids)}")
    if duplicate_input_ids: logger.debug(f"🧹 Duplicate input IDs skipped: {duplicate_input_ids}")
    if not unique_sales:
        logger.info("No unique products left after deduplication.")
        return []


    # === STEP 2 & 3: Load Sheet1 and Filter (Sheet1 ONLY) ===
    allowed_ids_sheet1 = set()
    blocked_ids_sheet1 = set()
    sheet1_cloned_gids = set() # Store as set now
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(GOOGLE_SHEET_ID)
        sheet1 = sheet.worksheet(SHEET1_NAME)
        sheet1_records = sheet1.get_all_records()
        logger.info(f"Read {len(sheet1_records)} records from {SHEET1_NAME}.")

        for row in sheet1_records:
             pid = str(row.get("Product ID", "")).strip()
             if not pid: continue
             status = row.get("Status", "").strip().upper()
             cloned_gid = row.get("Cloned Product GID", "").strip()

             # Define blocking statuses found *within Sheet1*
             if status in ["DONE", "APPROVED", "TRANSLATED", "ERROR_TRANSLATING", "ERROR_CLONING", "ERROR_FETCHING_SOURCE", "ERROR_EXCEPTION"]:
                 blocked_ids_sheet1.add(pid)
             else: # Includes PENDING, empty status, etc.
                 allowed_ids_sheet1.add(pid)

             if cloned_gid:
                 sheet1_cloned_gids.add(pid) # Add ID to set if GID exists

        logger.info(f"📋 Sheet1 processed. Allowed Status IDs: {len(allowed_ids_sheet1)}, Blocked Status IDs: {len(blocked_ids_sheet1)}, Already Cloned GIDs: {len(sheet1_cloned_gids)}")

    except gspread.exceptions.WorksheetNotFound:
         logger.error(f"❌ Worksheet '{SHEET1_NAME}' not found. Cannot proceed.")
         return []
    except Exception as e:
        logger.exception(f"🔥 Failed loading or processing Sheet1 data for filtering: {e}")
        return []

    # Filter list based only on Sheet1 data
    pre_filter_count = len(unique_sales)
    products_to_process_initially = [
        p for p in unique_sales
        # Keep if ID was found in Sheet1 with allowed status (implicit via allowed_ids set)
        if str(p.get("Product ID","")).strip() in allowed_ids_sheet1
        # AND ensure its ID wasn't found with a blocking status in Sheet1
        and str(p.get("Product ID","")).strip() not in blocked_ids_sheet1
        # AND ensure it doesn't already have a Cloned GID recorded in Sheet1
        and str(p.get("Product ID","")).strip() not in sheet1_cloned_gids
    ]
    logger.info(f"🧹 Filtered based on Sheet1 status/GID from {pre_filter_count} to {len(products_to_process_initially)} items.")
    if not products_to_process_initially:
        logger.info("No products eligible for cloning after Sheet1 filtering.")
        return []


    # === STEP 4: Simultaneous Processing Filter ===
    products_to_actually_clone = [] # Initialize the FINAL list for *this specific run*
    skipped_concurrent = 0
    with currently_processing_lock: # Ensure only one thread/process enters here at a time
        for item in products_to_process_initially:
            pid_str = str(item.get("Product ID", "")).strip()
            if not pid_str: continue

            if pid_str in currently_processing_ids:
                skipped_concurrent += 1
                continue # Skip this product, another process is handling it

            products_to_actually_clone.append(item) # Add to the final list
            currently_processing_ids.add(pid_str)   # Claim this ID within the lock
    logger.info(f"🛡️ Concurrency filter complete: Attempting to clone {len(products_to_actually_clone)}. Skipped {skipped_concurrent}.")
    if not products_to_actually_clone:
        logger.info("No products left to clone after concurrency filter.")
        return []


    # === STEP 5: Clone Products (Loop) ===
    for item in products_to_actually_clone: # Iterate over the final list
        original_pid_str = str(item.get("Product ID", "")).strip()
        if not original_pid_str: continue # Should not happen, but safe check

        # Initialize variables for this product
        cloned_product_gid = None
        cloned_product_title = ""
        cloned_product_rest_id = None
        new_product_handle = None
        product_create_successful = False
        collection_add_success = None

        try:
            logger.info(f"--- Cloning Original Product ID: {original_pid_str} ---")

            # --- Fetch source data ---
            source_product_data = fetch_product_by_id(original_pid_str)
            if not source_product_data:
                update_product_status_in_sheet(original_pid_str, "ERROR_FETCHING_SOURCE")
                continue

            source_title = source_product_data.get("title", "").strip()
            if not source_title:
                 update_product_status_in_sheet(original_pid_str, "ERROR_EMPTY_SOURCE_TITLE")
                 continue

            # --- Check Handle ---
            cloned_handle = f"{slugify(source_title)}-{original_pid_str[-5:]}"
            existing_target_product = fetch_product_by_handle(cloned_handle, target_store_url, target_api_key)
            if existing_target_product:
                update_product_status_in_sheet(original_pid_str, "SKIPPED_HANDLE_EXISTS")
                continue

            # --- Construct REST Payload (Active & Published) ---
            logger.info(f"   Preparing REST POST payload (Active & Published)...")
            # (Payload preparation logic - use your existing detailed logic here)
            title = source_title
            description = source_product_data.get("body_html", "")
            vendor = source_product_data.get("vendor", "Default Vendor")
            product_type = source_product_data.get("product_type", "Default Type")
            tags_list = source_product_data.get("tags", [])
            if isinstance(tags_list, str): tags_list = [t.strip() for t in tags_list.split(',') if t.strip()]
            if not isinstance(tags_list, list): tags_list = []
            if "ClonedForTranslation" not in tags_list: tags_list.append("ClonedForTranslation")
            tags_string = ", ".join(tags_list)
            images_input = [{"src": img.get("src")} for img in source_product_data.get("images", []) if isinstance(img, dict) and img.get("src")]
            rest_options = []
            option_names = []
            source_options = source_product_data.get('options', [])
            if isinstance(source_options, list) and source_options:
                 for i, opt in enumerate(source_options):
                     if isinstance(opt, dict) and opt.get('name'):
                         rest_options.append({"name": opt['name'], "position": opt.get('position', i + 1)})
                         option_names.append(opt['name'])
            rest_variants_initial = []
            source_variants = source_product_data.get('variants', [])
            if isinstance(source_variants, list) and source_variants:
                 for i, sv in enumerate(source_variants):
                     if not isinstance(sv, dict): continue
                     variant_payload = {
                        "price": str(sv.get('price', '0.00')), "sku": f"CLONE-{original_pid_str}-{sv.get('sku', sv.get('id', ''))}",
                        "compare_at_price": str(sv.get('compare_at_price')) if sv.get('compare_at_price') is not None else None,
                        "barcode": sv.get('barcode'), "inventory_policy": "deny" if sv.get('inventory_management') == 'shopify' else "continue",
                        "requires_shipping": sv.get('requires_shipping', True), "taxable": sv.get('taxable', True),
                        "weight": sv.get('weight'), "weight_unit": sv.get('weight_unit', 'kg') if sv.get('weight') is not None else None,
                        **({f"option{idx+1}": sv.get(f"option{idx+1}") for idx in range(len(option_names)) if sv.get(f"option{idx+1}") is not None})
                    }
                     rest_variants_initial.append({k: v for k, v in variant_payload.items() if v is not None})

            product_payload = {
                "product": {
                    "title": title, "body_html": description, "handle": cloned_handle,
                    "status": "active",     # Ensure Active
                    "published": True,      # Ensure Published attempt via REST
                    "vendor": vendor, "product_type": product_type, "tags": tags_string,
                    **({"images": images_input} if images_input else {}),
                    **({"options": rest_options} if rest_options else {}),
                    **({"variants": rest_variants_initial} if rest_variants_initial else {}),
                }
            }
            # --- End Payload Construction ---


            # --- Create Product (REST POST) ---
            logger.info(f"   [API Call - REST] Creating product...")
            create_url = f"{ensure_https(target_store_url)}/admin/api/2024-04/products.json"
            response = shopify_api_request("POST", create_url, api_key=target_api_key, json=product_payload, timeout=90)

            # --- Process Response ---
            if response and response.status_code in [200, 201]:
                new_product = response.json().get("product")
                if new_product:
                    # --- Step 1 (in loop): Extract Info & Log Success ---
                    cloned_product_gid = new_product.get("admin_graphql_api_id")
                    cloned_product_title = new_product.get("title", "")
                    cloned_product_rest_id = new_product.get("id")
                    new_product_handle = new_product.get("handle")
                    product_create_successful = True

                    logger.info(f"  [API Result - REST] Product Creation Successful.")
                    logger.info(f"  ✅ Cloned {original_pid_str} -> GID: {cloned_product_gid}, REST ID: {cloned_product_rest_id} (Status: Active, Published via REST)")
                    created_products.append({
                        "original_id": original_pid_str, "cloned_id": cloned_product_rest_id,
                        "cloned_gid": cloned_product_gid, "title": cloned_product_title,
                        "handle": new_product_handle, "store": target_store_value
                    })

                    # --- Step 2 (in loop): Publishing ---
                    # Publishing is handled by "published: True" in the POST above.
                    logger.info("  Publishing implicitly attempted via 'published: True' flag during creation.")


                    # --- Step 3 (in loop): Add to Collection (REST POST Only) ---
                    collection_add_success = None # Reset status
                    if cloned_product_rest_id and pinterest_collection_rest_id:
                        logger.info(f"  [API Call - REST] Adding product REST ID {cloned_product_rest_id} to collection REST ID {pinterest_collection_rest_id}...")
                        try:
                            collect_payload = {"collect": {"product_id": cloned_product_rest_id,"collection_id": int(pinterest_collection_rest_id)}}
                            collect_endpoint = "collects.json"
                            collect_url = f"{ensure_https(target_store_url)}/admin/api/2024-04/{collect_endpoint}"
                            collect_response = shopify_api_request("POST", collect_url, api_key=target_api_key, json=collect_payload)

                            if collect_response and collect_response.status_code in [200, 201]:
                                collect_data = collect_response.json().get("collect")
                                logger.info(f"  [API Result - REST] Add to collection successful. Collect ID: {collect_data.get('id') if collect_data else 'N/A'}")
                                collection_add_success = True
                            else:
                                logger.error(f"  [API Result - REST] Add to collection failed. Status: {collect_response.status_code if collect_response else 'N/A'}. Check helper logs.")
                                collection_add_success = False
                        except Exception as add_e:
                            logger.exception(f"  [API Result - REST] Exception during add to collection attempt: {add_e}")
                            collection_add_success = False
                    elif not pinterest_collection_rest_id:
                        logger.info("  Skipping add to collection (No target collection REST ID configured).")
                        collection_add_success = True # Not an error if not configured
                    else:
                         logger.warning("  Skipping add to collection (cloned_product_rest_id not available).")
                    # --- END Step 3 ---


                    # --- Step 4 (in loop): Update Google Sheet ---
                    logger.info(f"  Updating Google Sheet for {original_pid_str}...")
                    sheet_updated_successfully = update_cloned_product_info_in_sheet(
                        product_id=original_pid_str,
                        cloned_gid=cloned_product_gid, # Still pass GID
                        cloned_title=cloned_product_title,
                        new_status="PENDING",
                        target_store=target_store_value
                    )
                    if not sheet_updated_successfully:
                         logger.error(f"❌ Failed combined sheet update for {original_pid_str}.")
                    if collection_add_success is False:
                         logger.warning(f"Product {original_pid_str} created but failed add to collection {pinterest_collection_rest_id}.")
                         # Consider updating status e.g., update_product_status_in_sheet(original_pid_str, "PENDING (CollectionFail)")
                    # --- END Step 4 ---

                else: # No 'product' in response
                    logger.error(f"❌ Clone REST POST succeeded but no 'product' data for {original_pid_str}.")
                    update_product_status_in_sheet(original_pid_str, "ERROR_CLONE_RESPONSE")

            else: # POST failed
                status_code = response.status_code if response else 'N/A'
                logger.error(f"❌ Cloning REST POST failed for {original_pid_str}. Status: {status_code}. Check logs.")
                update_product_status_in_sheet(original_pid_str, "ERROR_CLONING")

        except Exception as e:
            logger.exception(f"🔥 Unhandled Exception during cloning loop for product {original_pid_str}: {e}")
            if not product_create_successful and original_pid_str:
                 update_product_status_in_sheet(original_pid_str, "ERROR_EXCEPTION")

        finally:
            # --- Release Lock ---
            with currently_processing_lock:
                if original_pid_str in currently_processing_ids:
                    currently_processing_ids.remove(original_pid_str)
                    logger.debug(f"Released lock for {original_pid_str}.")

    # --- After loop finishes ---
    logger.info(f"🚩 Cloning phase complete. Successfully created {len(created_products)} product clones in target store '{target_store_value}' this run.")
    return created_products

# --- END function ---

# --- END MODIFIED function ---

# --- END MODIFICATION ---

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

# In export_routes.py

# --- Modify this function ---
# In export_routes.py

# --- Modify this function ---
@export_bp.route("/run_export", methods=["POST"])
def run_export():
    """
    Handles the multi-phase export process:
    1. Review Only: Generate Google Sheet of products meeting sales criteria.
    2. Phase 1: Clone products (active & published, added to Pinterest collection).
    3. Phase 2: Translate cloned products.
    """
    try:
        # ... (Keep existing code for getting data, validation) ...
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

        # --- Get Target Store Config (If needed for Phase 1 or 2) ---
        target_store_config = None
        if run_phase_1 or run_phase_2:
            target_store_config = get_store_credentials(store_value) # Use updated function
            if not target_store_config:
                error_msg = f"Could not retrieve valid configuration for target store: '{store_value}'. Check SHOPIFY_STORES_CONFIG env var and store content."
                logger.error(error_msg)
                return jsonify({"error": error_msg}), 400
            logger.info(f"Using configuration for target store: {target_store_config.get('value')}")

        # --- Execute Phase ---

        # Phase: Review Only
        if review_only:
            # ... (Keep existing review_only logic) ...
            logger.info("Executing run_export: review_only phase")
            product_sales = get_sold_product_details(start_date, end_date, min_sales)
            if product_sales is None: return jsonify({"error": "Failed to retrieve sales data."}), 500
            sheet_url = export_sales_to_sheet(product_sales)
            if not sheet_url: return jsonify({"error": "Failed to export sales data to Google Sheet."}), 500
            logger.info(f"Sales sheet generated: {sheet_url}")
            return jsonify({"message": "✅ Sales sheet generated successfully.", "sheet_url": sheet_url})


        # Phase: Clone Only
        elif run_phase_1:
            logger.info("Executing run_export: run_phase_1 (Clone)")
            if not target_store_config: return jsonify({"error": "Target store configuration missing."}), 500

            # Get Online Store Publication ID (using config)
            online_store_publication_id = get_online_store_publication_id(
                target_store_config["shopify_store_url"],
                target_store_config["shopify_api_key"]
            )
            if not online_store_publication_id:
                 logger.warning("Proceeding with cloning, but publishing to Online Store might fail.")

            # --- Get Pinterest Collection GID from config ---
            pinterest_collection_gid = target_store_config.get("pinterest_collection_gid")
            pinterest_collection_rest_id = target_store_config.get("pinterest_collection_rest_id") # <-- Fetch REST ID
    
            if not pinterest_collection_rest_id:
                 logger.warning(f"No 'pinterest_collection_rest_id' found in config for store '{store_value}'. Products cannot be added to the Pinterest collection via REST.")

            if not pinterest_collection_gid:
                logger.warning(f"No 'pinterest_collection_gid' found in config for store '{store_value}'. Products will not be added to the Pinterest collection.")
            # --- End Get Pinterest GID ---

            # Get products from sheet marked for cloning
            products_to_clone = get_pending_products_from_sheet()
            if products_to_clone is None: return jsonify({"error": "Failed to retrieve products from Google Sheet."}), 500
            if not products_to_clone: return jsonify({"message": "No products found in Sheet1 marked for cloning (e.g., PENDING)."}), 200

            # Call the cloning function, passing the required info
            # Note: Pass the config dict as target_store_info
            cloned_products_info = clone_products_to_target_store(
                product_sales=products_to_clone,
                target_store_info=target_store_config, # Pass the whole config dict
                pinterest_collection_rest_id=pinterest_collection_rest_id # Pass the GID
            )
            logger.info(f"Cloning phase complete. Cloned {len(cloned_products_info)} products this run.")
            # Updated message
            return jsonify({"message": f"✅ Cloning done for {len(cloned_products_info)} products to store '{store_value}' (set active, attempted publish & add to collection). Check sheet/logs.", "products": cloned_products_info })

        # Phase: Translate Only
        elif run_phase_2:
            # --- Make sure subsequent calls use the config correctly ---
            logger.info("Executing run_export: run_phase_2 (Translate)")
            if not target_store_config: return jsonify({"error": "Target store configuration missing."}), 500

            # Get translation methods/prompts
            translation_methods = data.get("translation_methods", {})
            prompts = data.get("prompts", {})
            title_method = translation_methods.get("title", "google")
            desc_method = translation_methods.get("description", "chatgpt")
            variant_method = translation_methods.get("variants", "google")
            title_prompt = prompts.get("title", "")
            desc_prompt = prompts.get("description", "")
            logger.info(f"Using translation methods - T: {title_method}, D: {desc_method}, V: {variant_method}")

            # Get products pending translation
            products_to_translate = get_products_pending_translation_from_sheet1()
            if products_to_translate is None: return jsonify({"error": "Failed to retrieve products for translation."}), 500
            if not products_to_translate: return jsonify({"message": "No products found in Sheet1 marked PENDING translation with GID."}), 200

            logger.info(f"Found {len(products_to_translate)} products to attempt translation.")
            successful_translations = 0
            translation_errors = 0

            # --- Loop through products ---
            for product_info in products_to_translate:
                original_product_id = product_info.get('Product ID')
                product_gid = product_info.get('Cloned Product GID')
                logger.debug(f"DEBUG: Processing sheet row data: {product_info}")

                if not product_gid or not original_product_id:
                    logger.warning(f"Missing GID ('{product_gid}') or Original ID ('{original_product_id}') in sheet row. Skipping.")
                    translation_errors += 1
                    if original_product_id: update_product_status_in_sheet(original_product_id, "ERROR_MISSING_DATA")
                    continue

                logger.info(f"--- [START Phase 2 Processing] GID: {product_gid} (Original ID: {original_product_id}) ---")
                overall_success = False # Initialize success for this product loop

                try:
                    # STEP A: Fetch (using config)
                    logger.info(f"  [{product_gid}] STEP A: Fetching product data from target store...")
                    cloned_product_data = fetch_product_by_gid(
                        product_gid,
                        target_store_config["shopify_store_url"], # Use config dict
                        target_store_config["shopify_api_key"]   # Use config dict
                    )

                    # STEP B: Check Fetch
                    if not cloned_product_data:
                        logger.error(f"  [{product_gid}] STEP B FAILED: Fetch returned None. Skipping product.")
                        update_product_status_in_sheet(original_product_id, "ERROR_FETCHING_CLONE")
                        translation_errors += 1
                        continue
                    else:
                         logger.info(f"  [{product_gid}] STEP B SUCCEEDED: Fetch successful. Title: '{cloned_product_data.get('title')}'")


                    # STEP C: Call Title/Desc/Handle Update Function (using config)
                    logger.info(f"  [{product_gid}] STEP C: Calling update_product_title_and_description (T:{title_method}, D:{desc_method})...")
                    # Ensure this function uses the passed url/key correctly
                    td_success, final_title_from_update = update_product_title_and_description(
                         product_gid=product_gid,
                         target_store_url=target_store_config["shopify_store_url"], # Use config dict
                         target_api_key=target_store_config["shopify_api_key"],   # Use config dict
                         target_language=language,
                         product_data=cloned_product_data,
                         title_method=title_method,
                         desc_method=desc_method,
                         title_prompt=title_prompt,
                         desc_prompt=desc_prompt,
                         source_lang=source_lang
                    )
                    logger.info(f"  [{product_gid}] STEP D: Result from update_product_title_and_description: {td_success}")


                    # STEP F: Variant Translation (using config)
                    variant_success = True
                    if variant_method != 'none':
                         logger.info(f"  [{product_gid}] STEP F.1: Attempting to fetch options for variant translation ({variant_method})...")
                         # Ensure this function uses the passed url/key correctly
                         options_to_translate = get_product_option_values(
                               product_gid,
                               shopify_store_url=target_store_config["shopify_store_url"], # Use config dict
                               shopify_api_key=target_store_config["shopify_api_key"]   # Use config dict
                         )

                         if options_to_translate is None:
                              logger.error(f"  [{product_gid}] STEP F.1 FAILED: Could not fetch options via GraphQL. Skipping variant translation.")
                              variant_success = False
                         elif options_to_translate:
                             logger.info(f"  [{product_gid}] STEP F.2: Found {len(options_to_translate)} options. Starting translation loop...")
                             all_options_succeeded = True
                             for option_data in options_to_translate:
                                 if not isinstance(option_data, dict) or not option_data.get("id") or not option_data.get("name"):
                                      logger.warning(f"  [{product_gid}] Skipping invalid option data structure: {option_data}")
                                      continue
                                 logger.info(f"  [{product_gid}] STEP F.3: Calling update_product_option_values for Option '{option_data.get('name')}' (ID: {option_data.get('id')})...")
                                 logger.debug(f"  [{product_gid}] Option data passed: {option_data}")
                                 # Ensure this function uses the passed url/key correctly
                                 single_option_success = update_product_option_values(
                                       product_gid=product_gid,
                                       option=option_data,
                                       target_language=language,
                                       source_language=source_lang,
                                       translation_method=variant_method,
                                       shopify_store_url=target_store_config["shopify_store_url"], # Use config dict
                                       shopify_api_key=target_store_config["shopify_api_key"]   # Use config dict
                                 )
                                 logger.info(f"  [{product_gid}] STEP F.4: Result for option '{option_data.get('name')}': {single_option_success}")
                                 if not single_option_success:
                                      all_options_succeeded = False
                                      logger.error(f"  [{product_gid}] Update failed for option '{option_data.get('name')}', stopping variant updates for this product.")
                                      break
                             variant_success = all_options_succeeded
                         else:
                             logger.info(f"  [{product_gid}] STEP F.1: Product has no options defined in Shopify.")
                             variant_success = True
                    else:
                         logger.info(f"  [{product_gid}] STEP F: Skipping variant translation (method is 'none').")

                   # STEP G: Update Sheet and Counters
                    overall_success = td_success and variant_success
                    final_status = "TRANSLATED" if overall_success else "ERROR_TRANSLATING"
                    title_to_write = final_title_from_update

                    # Get the target store value from the config dict available in this scope
                    target_store_value_for_update = target_store_config.get("value", "UNKNOWN") # <-- Get value here

                    # Update log message slightly
                    logger.info(f"  [{product_gid}] STEP G.1: Overall success: {overall_success}. Preparing sheet update for original ID {original_product_id} with Status='{final_status}', Title='{title_to_write[:50]}...', TargetStore='{target_store_value_for_update}'")

                    if original_product_id:
                        # Call the function that updates Status, GID, Title, AND Target Store
                        sheet_updated_successfully = update_cloned_product_info_in_sheet(
                            product_id=original_product_id,
                            cloned_gid=product_gid,
                            cloned_title=title_to_write,
                            new_status=final_status,
                            target_store=target_store_value_for_update # <-- PASS the target store value
                        )
                        logger.info(f"  [{product_gid}] STEP G.2: Sheet update call finished (Success: {sheet_updated_successfully}).")
                    else:
                         logger.warning(f"  [{product_gid}] STEP G: Cannot update sheet, original_product_id missing.")

                    # Update counters based on overall success
                    if overall_success: successful_translations += 1; time.sleep(1.5)
                    else: translation_errors += 1

                except Exception as translate_err:
                     logger.exception(f"❌ Uncaught Exception during translation loop for GID {product_gid}: {translate_err}")
                     translation_errors += 1
                     if original_product_id: update_product_status_in_sheet(original_product_id, "ERROR_EXCEPTION")
                     overall_success = False


                logger.info(f"--- [END Phase 2 Processing] GID: {product_gid} ---")
            # --- End Loop ---

            final_message = f"🌍 Translation phase complete. Attempted: {len(products_to_translate)}. Successful: {successful_translations}. Errors: {translation_errors}."
            logger.info(final_message)
            return jsonify({"message": final_message, "products_translated_count": successful_translations, "errors": translation_errors})

        else:
             logger.warning("⚠️ No valid run phase (review_only, run_phase_1, run_phase_2) specified.")
             return jsonify({"error": "Invalid run phase specified"}), 400

    except Exception as e:
        logger.exception("🔥 Unhandled Error in /run_export")
        return jsonify({"error": f"An unexpected server error occurred: {str(e)}"}), 500

# --- END MODIFICATION ---

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