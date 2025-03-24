import os
import re
import time
import logging
import requests
import json

# -------------------------------------------------------------------------
# Configure Logging (adjust level as needed)
# -------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# Shopify API Credentials
# -------------------------------------------------------------------------
SHOPIFY_STORE_URL = os.getenv("SHOPIFY_STORE_URL")
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")

# -------------------------------------------------------------------------
# Base API URL (adjust API version if needed)
# -------------------------------------------------------------------------
SHOPIFY_API_BASE = f"https://{SHOPIFY_STORE_URL}/admin/api/2023-04"

# -------------------------------------------------------------------------
# Helper: extract_id
# -------------------------------------------------------------------------
def extract_id(url_or_id):
    """
    Extracts a numeric Shopify product or variant ID from a URL,
    or returns the input if it's already purely numeric.
    """
    # If it’s an integer or purely digits, we can return it directly
    if isinstance(url_or_id, int) or (isinstance(url_or_id, str) and url_or_id.isdigit()):
        return str(url_or_id)

    # Attempt to find 'variant=123456' or 'products/123456' in the URL
    match = (
        re.search(r"variant=(\d+)", url_or_id)
        or re.search(r"products/(\d+)", url_or_id)
    )
    if match:
        return match.group(1)

    # If no match, log a warning
    logging.warning(f"⚠️ Invalid Shopify URL format or non-numeric ID: '{url_or_id}'")
    return None

# -------------------------------------------------------------------------
# fetch_product_by_id
# -------------------------------------------------------------------------
def fetch_product_by_id(product_id_or_url, retries=3):
    """
    Fetches a product from Shopify by:
      1) Attempting to parse 'product_id_or_url' as a numeric product ID
         or extracting from a product/variant URL.
      2) If that fails, tries to treat it as a variant ID to locate the parent product.
      3) Retries on transient errors (like rate limits) up to 'retries' times.

    Returns a dictionary with the product data, or None on failure.
    """
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_API_KEY,
        "Content-Type": "application/json"
    }

    # Extract the numeric ID if it's in a URL or is purely digits
    numeric_id = extract_id(product_id_or_url)
    if not numeric_id:
        logging.error("❌ Unable to extract a valid product/variant ID.")
        return None

    # 1) Attempt to fetch as a Product ID
    product_url = f"{SHOPIFY_API_BASE}/products/{numeric_id}.json"

    for attempt in range(1, retries + 1):
        try:
            response = requests.get(product_url, headers=headers, timeout=10)
        except requests.exceptions.RequestException as e:
            logging.error(f"⚠️ Network error on attempt {attempt}/{retries}: {e}")
            time.sleep(2)
            continue

        if response.status_code == 200:
            try:
                data = response.json()
                if "product" in data:
                    logging.info(f"✅ Successfully fetched product ID: {numeric_id}")
                    return data["product"]
            except requests.exceptions.JSONDecodeError:
                logging.error(f"⚠️ Shopify returned invalid JSON (Attempt {attempt}/{retries})")
                time.sleep(2)
                continue

        elif response.status_code == 403:
            logging.critical("🚨 Permission error: check your Shopify API key scopes!")
            return None
        elif response.status_code == 429:
            logging.warning("🚨 Rate limited by Shopify. Waiting 5s before retry.")
            time.sleep(5)
            continue
        else:
            logging.warning(f"⚠️ Failed to fetch product {numeric_id}: {response.status_code} {response.text}")
            break

    # 2) If fetching as a product ID failed, treat numeric_id as a variant ID
    logging.warning(f"⚠️ Product ID not found. Checking if {numeric_id} is a Variant ID...")

    variant_url = f"{SHOPIFY_API_BASE}/variants/{numeric_id}.json"
    try:
        response = requests.get(variant_url, headers=headers, timeout=10)
    except requests.exceptions.RequestException as e:
        logging.error(f"⚠️ Network error while fetching variant {numeric_id}: {e}")
        return None

    if response.status_code == 200:
        try:
            variant_data = response.json().get("variant", {})
            parent_product_id = variant_data.get("product_id")
            if parent_product_id:
                logging.info(f"✅ Found Product ID {parent_product_id} from Variant ID {numeric_id}")

                # Fetch the actual product
                product_url = f"{SHOPIFY_API_BASE}/products/{parent_product_id}.json"
                try:
                    product_resp = requests.get(product_url, headers=headers, timeout=10)
                except requests.exceptions.RequestException as e:
                    logging.error(f"⚠️ Network error fetching product {parent_product_id}: {e}")
                    return None

                if product_resp.status_code == 200:
                    try:
                        data = product_resp.json()
                        if "product" in data:
                            logging.info(f"✅ Successfully fetched product from Variant ID: {numeric_id}")
                            return data["product"]
                    except requests.exceptions.JSONDecodeError:
                        logging.error("⚠️ Shopify returned invalid JSON while fetching product.")
                        return None
                else:
                    logging.error(f"❌ Failed to fetch product {parent_product_id}: {product_resp.text}")
                    return None
        except requests.exceptions.JSONDecodeError:
            logging.error("⚠️ Shopify returned empty/invalid JSON for variant.")
            return None

    logging.error(f"❌ Could not locate product data for '{numeric_id}'.")
    return None

# -------------------------------------------------------------------------
# fetch_products_by_collection
# -------------------------------------------------------------------------
def fetch_products_by_collection(collection_id, limit=50):
    """
    Fetches products from a specific Shopify collection (by numeric ID).
    Returns a list of product dicts or empty if none found.
    """
    url = f"{SHOPIFY_API_BASE}/collections/{collection_id}/products.json?limit={limit}"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_API_KEY,
        "Content-Type": "application/json"
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10)
    except requests.exceptions.RequestException as e:
        logging.error(f"⚠️ Network error while fetching collection {collection_id}: {e}")
        return []

    if resp.status_code == 200:
        products = resp.json().get("products", [])
        logging.info(f"✅ Fetched {len(products)} products from collection {collection_id}")
        return products
    else:
        logging.error(f"❌ Failed to fetch products from collection {collection_id}: {resp.status_code} {resp.text}")
        return []

# -------------------------------------------------------------------------
# update_product_translation
# -------------------------------------------------------------------------
def update_product_translation(product_id, translated_title, translated_description):
    """
    Updates a Shopify product with a new title and description.
    Returns the updated product dict on success, or None on failure.
    """
    url = f"https://{SHOPIFY_STORE_URL}/admin/api/2023-04/products/{product_id}.json"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "product": {
            "id": product_id,
            "title": translated_title,
            "body_html": translated_description
        }
    }

    try:
        response = requests.put(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()  # This will raise an error if response is 4xx or 5xx
        json_response = response.json()

        if "errors" in json_response:
            logger.error(f"❌ Shopify API error: {json_response['errors']}")
            return None  # Return None if there are errors

        logger.info(f"✅ Successfully updated product {product_id}: {json_response}")
        return json_response.get("product", {})
    
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Shopify update failed: {e}")
        return None


# -------------------------------------------------------------------------
# (Optional) fetch_product_by_url
# -------------------------------------------------------------------------
def fetch_product_by_url(product_url):
    """
    Fetches a product using its handle-based URL.
    e.g. "https://your-store.com/products/my-product-handle"
    """
    if "/products/" not in product_url:
        logging.warning("⚠️ Invalid product URL format.")
        return None

    # Extract handle from the URL
    handle = product_url.split("/products/")[-1].split("?")[0].strip("/")
    url = f"{SHOPIFY_API_BASE}/products.json?handle={handle}"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_API_KEY,
        "Content-Type": "application/json"
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10)
    except requests.exceptions.RequestException as e:
        logging.error(f"⚠️ Network error while fetching product by handle: {e}")
        return None

    if resp.status_code == 200:
        products = resp.json().get("products", [])
        if products:
            logging.info(f"✅ Successfully fetched product by URL: {product_url}")
            return products[0]
        else:
            logging.error(f"❌ No product found for handle '{handle}' in Shopify.")
            return None
    else:
        logging.error(f"❌ Failed to fetch product by URL {product_url}: {resp.status_code} {resp.text}")
        return None

# -------------------------------------------------------------------------
# (Optional) extract_product_id_from_variant
# -------------------------------------------------------------------------
def extract_product_id_from_variant(variant_id):
    """
    Given a variant ID, returns the parent product ID (or None if fails).
    """
    url = f"{SHOPIFY_API_BASE}/variants/{variant_id}.json"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_API_KEY,
        "Content-Type": "application/json"
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10)
    except requests.exceptions.RequestException as e:
        logging.error(f"⚠️ Network error while fetching variant {variant_id}: {e}")
        return None

    if resp.status_code == 200:
        product_id = resp.json().get("variant", {}).get("product_id")
        if product_id:
            logging.info(f"✅ Variant {variant_id} belongs to Product ID {product_id}")
            return product_id
        else:
            logging.warning(f"⚠️ Variant {variant_id} does not contain a valid product_id.")
            return None
    else:
        logging.error(f"❌ Failed to fetch variant {variant_id}: {resp.status_code} {resp.text}")
        return None
 