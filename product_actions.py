# product_actions.py

import os
import requests
import logging
import time
import argparse
from openai import OpenAI
from dotenv import load_dotenv

# --- Logging Setup ---
# Placed near the top for consistency
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Load .env and DEFINE CONFIG GLOBALLY ---
load_dotenv() # Load environment variables from .env file

# Load essential connection details
SHOPIFY_STORE_URL = os.getenv("SHOPIFY_STORE_URL")
SHOPIFY_API_ACCESS_TOKEN = os.getenv("SHOPIFY_API_KEY")
API_VERSION = "2024-01" # Use a specific, reasonably current Shopify API version (Adjust if needed)

# --- Load Target Collection ID ---
TARGET_COLLECTION_ID_STR = os.getenv("TARGET_COLLECTION_ID")
TARGET_COLLECTION_NAME = os.getenv("TARGET_COLLECTION_NAME", 'READY FOR PINTEREST')
TARGET_COLLECTION_ID = None
try:
    if TARGET_COLLECTION_ID_STR:
        TARGET_COLLECTION_ID = int(TARGET_COLLECTION_ID_STR)
    # Add log for TARGET ID confirmation
    if TARGET_COLLECTION_ID:
        logger.info(f"✅ Globally loaded TARGET_COLLECTION_ID: {TARGET_COLLECTION_ID}")
    else:
        logger.error("❌ Failed to load TARGET_COLLECTION_ID globally from .env.")
except (ValueError, TypeError):
    logger.error(f"❌ Invalid TARGET_COLLECTION_ID in .env: '{TARGET_COLLECTION_ID_STR}'.")
    TARGET_COLLECTION_ID = None

# --- Load Source Collection ID ---
SOURCE_COLLECTION_ID_STR = os.getenv("SOURCE_COLLECTION_ID") # Reads from .env
SOURCE_COLLECTION_NAME = os.getenv("SOURCE_COLLECTION_NAME", 'NEEDS TO BE DONE')

SOURCE_COLLECTION_ID = None # Initialize
try:
    if SOURCE_COLLECTION_ID_STR:
        SOURCE_COLLECTION_ID = int(SOURCE_COLLECTION_ID_STR) # Convert to integer
    # ---> ADD THIS LOG LINE <---
    if SOURCE_COLLECTION_ID:
        logger.info(f"✅ Globally loaded SOURCE_COLLECTION_ID: {SOURCE_COLLECTION_ID}")
    else:
        logger.error("❌ Failed to load SOURCE_COLLECTION_ID globally from .env. Removal will be skipped.")
    # ---> END OF ADDED LOG LINE <---
except (ValueError, TypeError):
    logger.error(f"❌ Invalid SOURCE_COLLECTION_ID in .env: '{SOURCE_COLLECTION_ID_STR}'. Must be numeric.")
    SOURCE_COLLECTION_ID = None # Ensure it's None on error

# Convert IDs to integers, handle potential errors during loading
TARGET_COLLECTION_ID = None # Initialize
try:
    if TARGET_COLLECTION_ID_STR:
        TARGET_COLLECTION_ID = int(TARGET_COLLECTION_ID_STR)
except (ValueError, TypeError):
    logger.error(f"❌ Invalid TARGET_COLLECTION_ID in .env: '{TARGET_COLLECTION_ID_STR}'. Must be numeric.")
    # TARGET_COLLECTION_ID remains None

SOURCE_COLLECTION_ID = None # Initialize
try:
    if SOURCE_COLLECTION_ID_STR:
        SOURCE_COLLECTION_ID = int(SOURCE_COLLECTION_ID_STR)
except (ValueError, TypeError):
    logger.error(f"❌ Invalid SOURCE_COLLECTION_ID in .env: '{SOURCE_COLLECTION_ID_STR}'. Must be numeric.")
    # SOURCE_COLLECTION_ID remains None

# --- Load API Keys Globally ---
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# --- DeepSeek Client Initialization (Global) ---
deepseek_client = None
if DEEPSEEK_API_KEY:
    try:
        # Common base URL for DeepSeek's OpenAI-compatible endpoint is often /v1
        deepseek_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com/v1")
        logger.info("✅ DeepSeek Client Initialized.")
    except Exception as e:
        logger.error(f"❌ Failed to initialize DeepSeek Client: {e}")
else:
    logger.warning("⚠️ DEEPSEEK_API_KEY not found. DeepSeek features will be disabled.")


# --- Allowed Product Types (Global Constant) ---
ALLOWED_PRODUCT_TYPES = {
    "Jackets Women", "Jackets Men", "Sweaters Women", "Sweaters Men",
    "Hat Women", "Hat Men", "Training suit Women", "Training suit Men",
    "Dresses", "Shoes Women", "Shoes Men", "Pants Women", "Pants Men",
    "One Pieces Women", "Blazer Women", "Blazer Men", "Earrings Women",
    "Bags Women", "Belts Women", "Necklaces Women",
    "T-shirts Men", "Knitted Sweaters Women", "Hair Accessories Women",
    "Glasses", "Halloween", "Bras", "Bikinis",
    "Bracelets Women", "Blouses Women", "Active Wear",
    "Accessories", "Skirts Women", "Sweater vests", "Sets Women", "Sets Men"
}

# --- AI Function ---
def get_ai_type_from_description(product_description, allowed_types_list, product_title=""):
    """
    Uses the initialized DeepSeek client (via OpenAI library) to determine the
    best product type based PRIMARILY on the product description.
    """
    logger.info(f"Attempting DeepSeek categorization based on description...")

    # --- 1. Check if DeepSeek client is available ---
    if not deepseek_client: # Check the global variable directly
        logger.error("❌ DeepSeek client is not initialized. Cannot determine type.")
        return None

    # --- 2. Check if description is valid ---
    if not product_description:
        logger.warning("Product description is empty. Cannot determine type from it.")
        return None

    # --- 3. Prepare Prompt for DeepSeek ---
    allowed_types_str = ", ".join(list(allowed_types_list)) # Use passed-in list
    description_snippet = product_description[:1000]

    prompt = f"""Analyze the following product description:
--- DESCRIPTION START ---
{description_snippet}
--- DESCRIPTION END ---

The product title is "{product_title}" (use for context only if needed).

Based *primarily on the product description*, select the single most appropriate category for this product from the following list:
[{allowed_types_str}]

Your response MUST be ONLY the chosen category name from the list, exactly as it appears in the list. Do not add explanations or any other text.
Category:"""

    # --- 4. Prepare Messages for API ---
    messages = [{"role": "user", "content": prompt}]
    determined_type = None
    llm_response_text = None

    try:
        # --- 5. Call DeepSeek API ---
        logger.debug("Calling deepseek_client.chat.completions.create for categorization...")
        response = deepseek_client.chat.completions.create(
            model="deepseek-chat", # Or specific model name
            messages=messages,
            max_tokens=60,
            temperature=0.1,
            n=1,
            stream=False
        )
        # --- 6. Extract Response ---
        if response.choices and len(response.choices) > 0:
             message = response.choices[0].message
             if message and message.content:
                  llm_response_text = message.content.strip()
                  logger.debug(f"Raw DeepSeek classification response: '{llm_response_text}'")

    except Exception as e:
        logger.error(f"Error during DeepSeek API call for categorization: {e}", exc_info=True)

    # --- 7. Validate Response ---
    if llm_response_text:
        potential_type = llm_response_text
        if potential_type in allowed_types_list: # Validate against the provided list
            determined_type = potential_type
            logger.info(f"DeepSeek determined type from description: '{determined_type}'")
        else:
            logger.warning(f"DeepSeek response '{potential_type}' not found exactly in allowed list.")
            logger.debug(f"Prompt used for failed categorization: {prompt}")
    else:
        logger.warning("DeepSeek returned empty or no valid content for description-based categorization.")

    # --- 8. Handle Failure/Fallback ---
    if not determined_type:
        logger.warning("DeepSeek categorization from description failed or response invalid, type not determined.")
        determined_type = None

    return determined_type

# --- Helper Function ---
def ensure_https(url):
    """Ensures a URL starts with https://."""
    if not url:
        return None
    url = url.strip()
    if url.startswith("http://"):
        return url.replace("http://", "https://", 1)
    if not url.startswith("https://"):
        return f"https://{url}"
    return url

# --- Shopify API Request Function ---
def shopify_request(method, endpoint, json_payload=None):
    """Makes an authenticated request to the Shopify Admin API."""
    if not SHOPIFY_STORE_URL or not SHOPIFY_API_ACCESS_TOKEN:
        logger.error("Shopify Store URL or API Access Token not configured.")
        return None

    base_url = ensure_https(SHOPIFY_STORE_URL)
    if not base_url:
         logger.error("Invalid Shopify Store URL.")
         return None

    # Ensure endpoint starts with /admin/api/
    if not endpoint.startswith("/admin/api/"):
         # Basic correction if API version prefix is missing
         if endpoint.startswith("/"):
              endpoint = f"/admin/api/{API_VERSION}{endpoint}"
         else:
              endpoint = f"/admin/api/{API_VERSION}/{endpoint}"


    url = f"{base_url}{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": SHOPIFY_API_ACCESS_TOKEN,
    }

    try:
        # Increase timeout from 30 to 60 seconds (or higher if needed)
        response = requests.request(method, url, headers=headers, json=json_payload, timeout=60)

        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 10))
            logger.warning(f"Rate limit hit. Retrying after {retry_after} seconds.")
            time.sleep(retry_after)
            # Also increase timeout on retry
            response = requests.request(method, url, headers=headers, json=json_payload, timeout=60)

        return response

    except requests.exceptions.RequestException as e:
        logger.exception(f"HTTP Request failed: {e}")
        return None
    except Exception as e:
        logger.exception(f"An unexpected error occurred during the API request: {e}")
        return None

# --- Actual API Functions ---
def platform_api_update_product_type(product_id, product_type):
    """Updates a product's type via the Shopify API."""
    logger.info(f"Attempting to update product ID '{product_id}' with product type: '{product_type}'")
    endpoint = f"/admin/api/{API_VERSION}/products/{product_id}.json"
    payload = {"product": {"id": product_id, "product_type": product_type}}
    response = shopify_request("PUT", endpoint, json_payload=payload)

    if response and response.status_code == 200:
        logger.info(f"Successfully updated product type for {product_id}")
        return True
    else:
        status = response.status_code if response else "No Response"
        text = response.text if response else ""
        logger.error(f"Failed to update product type for {product_id}: {status} - {text}")
        return False

def platform_api_add_product_to_collection(product_id, collection_id):
    """Adds a product to a specified collection via the Shopify API using the Collect endpoint."""
    # Use TARGET_COLLECTION_NAME for logging clarity if adding to target
    coll_name_log = TARGET_COLLECTION_NAME if collection_id == TARGET_COLLECTION_ID else f"ID {collection_id}"
    logger.info(f"Attempting to add product ID '{product_id}' to collection '{coll_name_log}' (ID: {collection_id})")
    endpoint = f"/admin/api/{API_VERSION}/collects.json"
    payload = {"collect": {"product_id": product_id, "collection_id": collection_id}}
    response = shopify_request("POST", endpoint, json_payload=payload)

    if response and response.status_code in [200, 201]: # 200 OK is also possible if already added sometimes
        logger.info(f"Successfully added/confirmed product {product_id} in collection {collection_id}")
        return True
    elif response and response.status_code == 422 and "already exists" in response.text.lower():
         logger.warning(f"Product {product_id} is likely already in collection {collection_id} (422 - already exists). Considering successful.")
         return True
    else:
        status = response.status_code if response else "No Response"
        text = response.text if response else ""
        logger.error(f"Failed to add product {product_id} to collection {collection_id}: {status} - {text}")
        return False

def platform_api_find_collect_id(product_id, collection_id):
    """Finds the specific 'Collect' ID linking a product to a specific collection."""
    if not collection_id: # Prevent API call with invalid ID
        logger.error(f"Invalid collection_id (None or empty) provided to find_collect_id for product {product_id}")
        return None
    try:
        collection_id_int = int(collection_id)
    except (ValueError, TypeError):
        logger.error(f"Invalid collection_id type provided to find_collect_id: {collection_id}")
        return None

    logger.debug(f"Searching for Collect linking Product ID {product_id} and Collection ID {collection_id_int}")
    endpoint = f"/admin/api/{API_VERSION}/collects.json?product_id={product_id}&collection_id={collection_id_int}"
    response = shopify_request("GET", endpoint)

    if response and response.status_code == 200:
        try:
            data = response.json()
            if data.get("collects") and len(data["collects"]) > 0:
                collect_id = data["collects"][0]["id"]
                logger.debug(f"Found Collect ID: {collect_id}")
                return collect_id
            else:
                logger.info(f"Product {product_id} not found in Collection {collection_id_int} (no Collect entry).")
                return None
        except Exception as e:
            logger.error(f"Error parsing Collects response for Product {product_id}, Collection {collection_id_int}: {e}")
            return None
    else:
        status = response.status_code if response else "No Response"
        text = response.text if response else ""
        logger.error(f"Failed to fetch Collects for Product {product_id}, Collection {collection_id_int}: {status} - {text}")
        return None

def platform_api_remove_product_from_collection(product_id, collection_id):
    """Removes a product from a specified collection by deleting its Collect entry."""
    if not collection_id: # Prevent API call with invalid ID
        logger.error(f"Invalid collection_id (None or empty) provided to remove_product for product {product_id}")
        return False
    try:
        collection_id_int = int(collection_id)
    except (ValueError, TypeError):
        logger.error(f"Invalid collection_id type provided to remove_product: {collection_id}")
        return False

    # Use SOURCE_COLLECTION_NAME for logging clarity if removing from source
    coll_name_log = SOURCE_COLLECTION_NAME if collection_id_int == SOURCE_COLLECTION_ID else f"ID {collection_id_int}"
    logger.info(f"Attempting to remove product ID '{product_id}' from collection '{coll_name_log}' (ID: {collection_id_int})")
    collect_id_to_delete = platform_api_find_collect_id(product_id, collection_id_int)

    if collect_id_to_delete is None:
        # Log message already handled in find_collect_id
        # If it wasn't found, the goal (product not in collection) is achieved.
        return True

    logger.debug(f"Found Collect ID {collect_id_to_delete}. Attempting deletion.")
    endpoint = f"/admin/api/{API_VERSION}/collects/{collect_id_to_delete}.json"
    response = shopify_request("DELETE", endpoint)

    if response and response.status_code == 200:
        logger.info(f"Successfully removed product {product_id} from collection {collection_id_int} (deleted Collect ID: {collect_id_to_delete})")
        return True
    elif response and response.status_code == 404:
        logger.warning(f"Collect ID {collect_id_to_delete} not found (404) during delete. Already removed?")
        return True # Consider success
    else:
        status = response.status_code if response else "No Response"
        text = response.text if response else ""
        logger.error(f"Failed to remove Collect ID {collect_id_to_delete} (Product {product_id}, Collection {collection_id_int}): {status} - {text}")
        return False

# --- Core Workflow Functions ---
def assign_product_type(product_id, product_type):
    """Assigns a specified product type to a product if it's valid."""
    logger.info(f"Attempting to assign type '{product_type}' to product '{product_id}'...")
    if product_type in ALLOWED_PRODUCT_TYPES:
        logger.info(f"Product type '{product_type}' is valid.")
        success = platform_api_update_product_type(product_id, product_type)
        if success:
            logger.info(f"Successfully assigned product type for product '{product_id}'.")
            return True
        else:
            # Error logged in platform_api_update_product_type
            return False
    else:
        logger.error(f"Error: Product type '{product_type}' is not in the allowed list for product '{product_id}'.")
        return False
    
def get_all_product_ids_from_collection(collection_id, limit=250):
    """
    Fetch all product IDs from a manual (custom) collection via the Collects API.
    Handles Shopify's pagination (cursor-based).
    Returns a list of product IDs.
    """
    if not collection_id:
        logger.error("Collection ID is None, cannot fetch products.")
        return []
    product_ids = []
    page_info = None
    page = 1
    while True:
        endpoint = f"/collects.json?collection_id={collection_id}&fields=product_id&limit={limit}"
        if page_info:
            endpoint += f"&page_info={page_info}"
        logger.debug(f"[DEBUG] Requesting endpoint: {endpoint}")
        response = shopify_request("GET", endpoint)
        if not response or response.status_code != 200:
            logger.error(f"No response for collection {collection_id}. Check API credentials and URL.")
            break
        data = response.json()
        collects = data.get("collects", [])
        ids_this_page = [c["product_id"] for c in collects if "product_id" in c]
        product_ids.extend(ids_this_page)
        logger.info(f"Page {page}: Fetched {len(ids_this_page)} products.")
        # Shopify pagination: look for 'Link' header with 'rel="next"'
        link_header = response.headers.get("Link")
        if not link_header or 'rel="next"' not in link_header:
            break
        # Extract the next page_info
        import re
        match = re.search(r'<[^>]*page_info=([^&>]+)[^>]*>; rel="next"', link_header)
        if match:
            page_info = match.group(1)
            page += 1
        else:
            break
    logger.info(f"Total fetched: {len(product_ids)} unique product IDs from collection {collection_id}.")
    return list(set(product_ids))


def move_product_to_pinterest_collection(product_id, from_collection_id=None, target_collection_id=None, target_collection_name=None):
    """
    Moves a product to the target Pinterest collection and removes it from the source collection (if provided).

    Args:
        product_id (int or str): The Shopify product ID.
        from_collection_id (int or str, optional): The source collection to remove from (if any).
        target_collection_id (int or str, optional): The target Pinterest collection ID (defaults to global).
        target_collection_name (str, optional): The name of the Pinterest collection (for logs).
    Returns:
        bool: True if add+remove succeeded (or add succeeded, even if not present in source), False if add fails.
    """
    # Use provided target, or fallback to globals
    target_collection_id = target_collection_id or TARGET_COLLECTION_ID
    target_collection_name = target_collection_name or TARGET_COLLECTION_NAME

    if not target_collection_id:
        logger.error(f"TARGET_COLLECTION_ID is not set. Cannot move product {product_id}.")
        return False

    # Add to target collection
    logger.info(f"Adding product '{product_id}' to '{target_collection_name}' (ID: {target_collection_id})...")
    added = platform_api_add_product_to_collection(product_id, target_collection_id)
    if not added:
        logger.error(f"Failed to add product {product_id} to collection {target_collection_id}")
        return False

    # Optionally remove from source collection
    if from_collection_id:
        logger.info(f"Removing product '{product_id}' from source collection (ID: {from_collection_id}) after add...")
        removed = platform_api_remove_product_from_collection(product_id, from_collection_id)
        if removed:
            logger.info(f"Product {product_id} removed from source collection {from_collection_id}")
        else:
            logger.warning(f"Product {product_id} could not be removed from source {from_collection_id} (may not have been present).")
    else:
        logger.debug(f"No source collection provided for removal for product {product_id}.")

    return True


if __name__ == "__main__":
    # You can override with test IDs here, or use .env globals

    TEST_SOURCE_COLLECTION_ID = 640471302468    # <--- replace with your test source
    TEST_TARGET_COLLECTION_ID = 642374697284   # <--- replace with your test target
    logger.info(f"TEST MODE: Moving all products from collection {TEST_SOURCE_COLLECTION_ID} ➔ {TEST_TARGET_COLLECTION_ID}")

    product_ids = get_all_product_ids_from_collection(TEST_SOURCE_COLLECTION_ID)
    logger.info(f"Found {len(product_ids)} product(s) to move from source collection.")

    moved = 0
    failed = 0
    for pid in product_ids:
        try:
            pid_int = int(pid)
        except Exception as e:
            logger.error(f"Invalid product ID '{pid}', skipping. Error: {e}")
            failed += 1
            continue
        # THIS is your function call, with from+to ID!
        success = move_product_to_pinterest_collection(
            pid_int,
            from_collection_id=TEST_SOURCE_COLLECTION_ID,
            target_collection_id=TEST_TARGET_COLLECTION_ID,
            target_collection_name="TEST PINTEREST COLLECTION"
        )
        if success:
            moved += 1
        else:
            failed += 1

    logger.info(f"Move complete. Success: {moved}, Failed: {failed}.")

