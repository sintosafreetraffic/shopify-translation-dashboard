import os
import re
import time
import logging
import requests
import json
from typing import Optional, Dict, Any, List, Union
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
def ensure_https(url):
    url = url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        return f"https://{url}"
    return url

SHOPIFY_API_BASE = f"{ensure_https(SHOPIFY_STORE_URL)}/admin/api/2023-04"

def slugify(text): 
    """
    Convert text to a URL-friendly slug.
    """
    return (
        text.lower()
            .strip()
            .replace(" ", "-")
            .replace("ä", "ae")
            .replace("ö", "oe")
            .replace("ü", "ue")
            .replace("ß", "ss")
            .replace("/", "-")
            .replace("|", "-")
    )

def clean_title(title: str) -> str:
    """
    Removes 'Clone' or similar suffixes from product titles.
    """
    unwanted_suffixes = ["(Clone)", "Clone"]
    for suffix in unwanted_suffixes:
        if title.endswith(suffix):
            title = title[: -len(suffix)].strip()
    return title

def create_shopify_session(store_domain: str = None, access_token: str = None):
    """
    Checks for necessary Shopify credentials and confirms readiness.
    Uses provided arguments or falls back to environment variables.
    Returns a dictionary with essential session parameters (store_url, access_token, api_base)
    or None if critical credentials are not configured.
    """
    logger.info("Attempting to create/validate Shopify session credentials...")

    # Use provided arguments or retrieve from environment variables
    current_store_domain = store_domain if store_domain else os.getenv("SHOPIFY_STORE_URL")
    current_access_token = access_token if access_token else os.getenv("SHOPIFY_API_KEY")

    if not current_store_domain:
        logger.critical("❌ CRITICAL: Shopify store domain/URL not provided and SHOPIFY_STORE_URL environment variable not set.")
        return None
    if not current_access_token:
        logger.critical("❌ CRITICAL: Shopify access token not provided and SHOPIFY_API_KEY environment variable not set.")
        return None

    # Ensure the store URL has a scheme (https://)
    full_store_url = current_store_domain.strip()
    if not full_store_url.startswith("http://") and not full_store_url.startswith("https://"):
        full_store_url = f"https://{full_store_url}"

    api_version = "2024-04" # Consistent with your previous setup
    api_base_url = f"{full_store_url}/admin/api/{api_version}"

    logger.info(f"✅ Shopify session credentials validated for store: {full_store_url}")

    return {
        "store_url": full_store_url,
        "access_token": current_access_token,
        "api_base": api_base_url,
        "api_version": api_version
    }

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


def execute_shopify_graphql_query(store_url: str, api_key: str, query: str, variables: dict, api_version: str = "2024-04") -> dict:
    """
    Helper function to execute a Shopify GraphQL query.
    """
    headers = {
        "X-Shopify-Access-Token": api_key,
        "Content-Type": "application/json",
    }
    endpoint = f"https://{store_url.replace('https://', '').replace('http://', '')}/admin/api/{api_version}/graphql.json"
    
    try:
        response = requests.post(endpoint, json={"query": query, "variables": variables}, headers=headers)
        response.raise_for_status()  # Raises an exception for HTTP errors (4xx or 5xx)
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Shopify GraphQL request failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response content: {e.response.content}")
            try:
                return e.response.json() # Try to return Shopify's error structure
            except ValueError: # If response is not JSON
                return {"errors": [{"message": f"Request failed: {str(e)}", "content": e.response.text}]}
        return {"errors": [{"message": f"Request failed: {str(e)}"}]}


def update_product_advanced(
    product_gid: str,
    payload: dict,
    api_key: str,
    store_url: str,
    api_version: str = None # Allow override, or use default/env
) -> tuple[bool, dict]:
    """
    Updates specified Shopify product fields via a dynamic GraphQL productUpdate mutation.

    Args:
        product_gid (str): The GID of the product to update (e.g., "gid://shopify/Product/12345").
        payload (dict): A dictionary containing the fields to update.
                        Expected keys can include:
                        - "title" (str)
                        - "bodyHtml" (str)
                        - "handle" (str)
                        - "status" (str: "ACTIVE", "ARCHIVED", "DRAFT")
                        - "options" (list[str]: e.g., ["Color", "Size"])
                        - "seo" (dict: {"title": str, "description": str})
                        - "variants" (list[dict]: e.g., [{"id": "variant_gid1", "options": ["Red", "Small"]}, ...])
        api_key (str): The Shopify API key (admin access token).
        store_url (str): The Shopify store URL (e.g., "your-store.myshopify.com").
        api_version (str): The Shopify API version (e.g., "2024-04"). Defaults to env or "2024-04".

    Returns:
        tuple[bool, dict]: A tuple containing:
                           - bool: True if the update was successful (no userErrors), False otherwise.
                           - dict: The Shopify API response dictionary.
    """
    if api_version is None:
        api_version = os.getenv("SHOPIFY_API_VERSION", "2024-04")

    logger.info(f"Attempting to update product GID {product_gid} with payload keys: {list(payload.keys())}")

    # 1. Construct the 'input' object for the ProductInput type in GraphQL
    product_input = {"id": product_gid}

    if "title" in payload:
        product_input["title"] = payload["title"]
    if "bodyHtml" in payload:
        product_input["bodyHtml"] = payload["bodyHtml"]
    if "handle" in payload:
        product_input["handle"] = payload["handle"]
    if "status" in payload:
        # Ensure status is one of the ProductStatus enum values
        valid_statuses = ["ACTIVE", "ARCHIVED", "DRAFT"]
        if str(payload["status"]).upper() in valid_statuses:
            product_input["status"] = str(payload["status"]).upper()
        else:
            logger.warning(f"Invalid status value '{payload['status']}' provided. Ignoring status update.")
            # Optionally return an error here or just skip the field
            # return False, {"errors": [{"message": f"Invalid status value: {payload['status']}"}]}


    # Product Options (list of strings for option names)
    # Note: Changing option names can be complex if variants already exist and rely on them.
    # Ensure the number of options and their order are handled carefully if changing.
    if "options" in payload and isinstance(payload["options"], list):
        product_input["options"] = payload["options"]

    # SEO Fields
    if "seo" in payload and isinstance(payload["seo"], dict):
        seo_input = {}
        if "title" in payload["seo"]:
            seo_input["title"] = payload["seo"]["title"]
        if "description" in payload["seo"]:
            seo_input["description"] = payload["seo"]["description"]
        if seo_input:
            product_input["seo"] = seo_input

    # Variant Updates
    # Payload for "variants" should be a list of variant input objects.
    # Each object needs at least the variant 'id' (GID) and can include 'options' list.
    # e.g., [{"id": "gid://shopify/ProductVariant/123", "options": ["Red", "Large"]}]
    if "variants" in payload and isinstance(payload["variants"], list):
        variant_inputs = []
        for var_data in payload["variants"]:
            if isinstance(var_data, dict) and "id" in var_data:
                var_input = {"id": var_data["id"]}
                if "options" in var_data and isinstance(var_data["options"], list):
                    var_input["options"] = var_data["options"]
                # Add other updatable variant fields here if needed (e.g., price, sku)
                # if "price" in var_data:
                #     var_input["price"] = str(var_data["price"]) # Price should be a string
                variant_inputs.append(var_input)
        if variant_inputs:
            product_input["variants"] = variant_inputs

    # 2. Define the GraphQL Mutation
    # This mutation is fairly static because ProductInput handles partial updates.
    # We only send the fields that are present in the product_input dictionary.
    mutation = """
    mutation productUpdate($input: ProductInput!) {
      productUpdate(input: $input) {
        product {
          id
          title
          handle
          status
          onlineStoreUrl # Example field to confirm update
          options { name } # To check if option names updated
          variants(first: 5) { # To check if variant options updated
            edges { node { id selectedOptions { name value } } }
          }
          seo { title description } # To check if SEO fields updated
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    graphql_variables = {"input": product_input}

    logger.debug(f"Executing productUpdate for GID {product_gid} with variables: {graphql_variables}")

    # 3. Execute the API Call
    response_data = execute_shopify_graphql_query(
        store_url, api_key, mutation, graphql_variables, api_version
    )

    # 4. Parse Response and Return Success/Failure
    if response_data and "errors" not in response_data and \
       response_data.get("data", {}).get("productUpdate") and \
       not response_data.get("data", {}).get("productUpdate", {}).get("userErrors"):
        logger.info(f"✅ Successfully updated product GID {product_gid}. Response: {response_data.get('data', {}).get('productUpdate', {}).get('product', {}).get('id')}")
        return True, response_data
    elif response_data and response_data.get("data", {}).get("productUpdate", {}).get("userErrors"):
        user_errors = response_data["data"]["productUpdate"]["userErrors"]
        logger.error(f"❌ Product update for GID {product_gid} failed with userErrors: {user_errors}")
        return False, response_data # Contains userErrors
    else: # Catch-all for other errors (network, Shopify internal, etc.)
        logger.error(f"❌ Product update for GID {product_gid} failed with API errors or unexpected response: {response_data.get('errors', response_data)}")
        return False, response_data


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


def fetch_product_by_id(product_id_or_url: str, session_context: dict, retries: int = 3):
    """
    Fetches a product from Shopify using session_context for authentication.
    1) Attempts to parse 'product_id_or_url' as a numeric product ID
       or extracting from a product/variant URL.
    2) If that fails (especially on 404), tries to treat it as a variant ID
       to locate the parent product.
    3) Retries on transient errors up to 'retries' times.

    Returns a dictionary with the product data, or None on failure.
    """
    if not session_context:
        logger.error("❌ Shopify session context not provided to fetch_product_by_id.")
        return None

    access_token = session_context.get('access_token')
    # api_base should be like "https://your-store.myshopify.com/admin/api/YYYY-MM"
    # It's constructed by create_shopify_session and includes the API version
    api_base = session_context.get('api_base')

    if not access_token or not api_base:
        logger.error("❌ Access token or API base URL missing from session_context in fetch_product_by_id.")
        logger.debug(f"Session context received: {session_context}")
        return None

    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json"  # Good practice, though GET often doesn't require it
    }

    numeric_id = extract_id(product_id_or_url) # Uses your existing helper
    if not numeric_id:
        # extract_id already logs an error if it can't parse
        return None

    # 1) Attempt to fetch as a Product ID
    product_url = f"{api_base}/products/{numeric_id}.json"
    logger.info(f"Attempting to fetch product by ID: {numeric_id} from {product_url}")

    product_data_found = None # To store result from product ID fetch

    for attempt in range(1, retries + 1):
        logger.debug(f"Attempt {attempt}/{retries} for product ID {numeric_id} at {product_url}")
        try:
            response = requests.get(product_url, headers=headers, timeout=20) # Increased timeout slightly

            if response.status_code == 429: # Rate limit
                retry_after = int(response.headers.get("Retry-After", 15)) # Use a shorter default if not specified
                logger.warning(f"Rate limited by Shopify (fetching product {numeric_id}). Retrying attempt {attempt}/{retries} after {retry_after}s...")
                time.sleep(retry_after)
                continue # Retry the current attempt in the for loop

            # Check for 404 specifically, as this means "not found as product", so we can try variant
            if response.status_code == 404:
                logger.warning(f"⚠️ Product ID {numeric_id} not found (404). Will try as Variant ID. Attempt {attempt}/{retries}.")
                break # Break from product fetch retries to try variant logic

            response.raise_for_status() # Raise HTTPError for other bad responses (4xx or 5xx not 404/429)
            
            data = response.json()
            if "product" in data:
                logger.info(f"✅ Successfully fetched product directly with ID: {numeric_id}")
                product_data_found = data["product"]
                break # Successfully fetched, exit retry loop
            else:
                logger.warning(f"Product key not found in response for ID {numeric_id}, though status was {response.status_code}. Attempt {attempt}/{retries}.")
                # This case might be unusual if status is 200, but good to log.
                # If it's a persistent issue, breaking might be better than retrying.
                if attempt == retries: break
                time.sleep(attempt * 2) # Simple backoff

        except requests.exceptions.HTTPError as e:
            # 403 is fatal for permissions
            if e.response.status_code == 403:
                logger.critical(f"🚨 Permission error (403) fetching product {numeric_id}: Check API key scopes! Response: {e.response.text[:200]}")
                return None # Fatal, no point retrying or trying variant
            # Other HTTP errors might be transient
            logger.error(f"⚠️ HTTP error on attempt {attempt}/{retries} fetching product {numeric_id} ({e.request.url}): {e.response.status_code} - {e.response.text[:200]}")
            if attempt == retries: break # Max retries reached for this type of error
            time.sleep(attempt * 2) # Simple backoff

        except requests.exceptions.Timeout:
            logger.error(f"⚠️ Timeout on attempt {attempt}/{retries} fetching product {numeric_id} from {product_url}")
            if attempt == retries: break
            time.sleep(attempt * 2)

        except requests.exceptions.RequestException as e: # Catch other network errors like ConnectionError
            logger.error(f"⚠️ Network error on attempt {attempt}/{retries} fetching product {numeric_id}: {e}")
            if attempt == retries: break
            time.sleep(attempt * 2)

        except ValueError: # Includes JSONDecodeError
            logger.error(f"⚠️ Failed to decode JSON (Attempt {attempt}/{retries}) for product {numeric_id}. Response: {response.text[:200] if response else 'No response object'}")
            if attempt == retries: break
            time.sleep(attempt * 2)
    
    if product_data_found:
        return product_data_found

    # 2) If fetching as a product ID failed (especially if it was a 404 or exhausted retries without success),
    #    try treating numeric_id as a Variant ID.
    logger.warning(f"⚠️ Product ID {numeric_id} not found or direct fetch failed. Checking if '{numeric_id}' is a Variant ID...")
    variant_url = f"{api_base}/variants/{numeric_id}.json"
    logger.info(f"Attempting to fetch variant by ID: {numeric_id} from {variant_url}")

    try:
        response = requests.get(variant_url, headers=headers, timeout=10)
        if response.status_code == 429: # Simplified rate limit handling for this single variant check
            retry_after = int(response.headers.get("Retry-After", 10))
            logger.warning(f"Rate limited by Shopify (fetching variant {numeric_id}). Waiting {retry_after}s...")
            time.sleep(retry_after)
            response = requests.get(variant_url, headers=headers, timeout=10)

        response.raise_for_status() # Check for errors
        variant_data = response.json().get("variant", {})
        parent_product_id = variant_data.get("product_id")

        if parent_product_id:
            logger.info(f"✅ Found Variant ID {numeric_id} belonging to Product ID {parent_product_id}. Fetching parent product...")
            # Fetch the parent product using its ID.
            # Call this function recursively, but reduce retries to prevent deep loops if there's an issue.
            # This will use the same session_context.
            return fetch_product_by_id(str(parent_product_id), session_context, retries=max(1, retries -1)) # Ensure at least 1 retry
        else:
            logger.warning(f"Variant ID {numeric_id} fetched, but no parent product_id found in its data.")

    except requests.exceptions.HTTPError as e:
         if e.response.status_code == 404:
             logger.warning(f"⚠️ Variant ID {numeric_id} also not found (404).")
         else:
             logger.warning(f"⚠️ HTTP error fetching {numeric_id} as variant ({e.request.url}): {e.response.status_code} - {e.response.text[:200]}")
    except requests.exceptions.Timeout:
        logger.error(f"⚠️ Timeout while fetching variant {numeric_id} from {variant_url}.")
    except requests.exceptions.RequestException as e:
        logger.error(f"⚠️ Network error fetching variant {numeric_id}: {e}")
    except ValueError: # Includes JSONDecodeError
        logger.error(f"⚠️ Failed to decode JSON for variant {numeric_id}. Response: {response.text[:200] if response else 'No response object'}")

    logger.error(f"❌ Ultimately could not locate product data for input: '{product_id_or_url}' (tried as product ID and variant ID: {numeric_id}).")
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

def get_sold_product_details(date_from: str, date_to: str, session_context: dict, min_sales: int = 1):
    """
    Fetches details of products sold within a given date range from Shopify,
    handling pagination and using provided session context for authentication.
    Aggregates sales by product_id and title, using line item quantities.
    """
    if not session_context:
        logger.error("❌ Shopify session context is not available. Cannot fetch sold products.")
        return []

    access_token = session_context.get('access_token')
    # api_base should be like "https://your-store.myshopify.com/admin/api/YYYY-MM"
    api_base = session_context.get('api_base')
    store_url_for_log = session_context.get('store_url', 'Unknown Store') # For logging

    if not access_token or not api_base:
        logger.error("❌ Access token or API base URL missing from session_context.")
        logger.debug(f"Session context received: {session_context}")
        return []

    logger.info(
        f"🧾 Fetching sales from {date_from} to {date_to} for store {store_url_for_log} "
        f"with ≥ {min_sales} sales (using API base: {api_base})"
    )

    # Initial endpoint for the first page
    # Consider using financial_status="paid" for more accurate sales figures
    params = {
        "status": "any", # You might want to filter by 'open' or 'closed' if also using financial_status
        "financial_status": "paid", # Recommended for actual "sold" items
        "created_at_min": f"{date_from}T00:00:00Z", # Assumes input dates are YYYY-MM-DD
        "created_at_max": f"{date_to}T23:59:59Z",
        "fields": "id,line_items", # 'id' is good for logging/debugging orders
        "limit": 250 # Max results per page for Shopify REST API
    }
    current_endpoint_url = f"{api_base}/orders.json"
    
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json"
    }

    all_orders = []
    page_num = 0

    while current_endpoint_url:
        page_num += 1
        logger.info(f"Fetching page {page_num} of orders from: {current_endpoint_url}")
        # Params are only needed for the first request if the URL doesn't have them.
        # Subsequent URLs from Link header will already include necessary params.
        current_params = params if page_num == 1 else None
        
        try:
            response = requests.get(current_endpoint_url, headers=headers, params=current_params, timeout=30)

            # Handle rate limits (429) with a simple retry
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 30)) # Default to 30s
                logger.warning(f"Rate limited by Shopify. Retrying page {page_num} after {retry_after} seconds...")
                time.sleep(retry_after)
                response = requests.get(current_endpoint_url, headers=headers, params=current_params, timeout=30) # Retry current page

            response.raise_for_status()  # Raise an exception for HTTP error codes (4xx or 5xx)

            page_orders = response.json().get("orders", [])
            if not page_orders:
                logger.info(f"No more orders found on page {page_num}.")
                break 
            
            all_orders.extend(page_orders)
            logger.info(f"Fetched {len(page_orders)} orders on page {page_num}. Total orders fetched so far: {len(all_orders)}.")

            # Pagination: Check Link header for the 'next' page URL
            link_header = response.headers.get("Link")
            current_endpoint_url = None # Reset for next iteration
            if link_header:
                links = link_header.split(',')
                for link in links:
                    parts = link.split(';')
                    if len(parts) == 2 and 'rel="next"' in parts[1].strip():
                        current_endpoint_url = parts[0].strip().strip('<>')
                        logger.debug(f"Next page URL found: {current_endpoint_url}")
                        break
            
            if not current_endpoint_url:
                 logger.info("No 'next' page link found. All pages fetched.")

        except requests.exceptions.HTTPError as e:
            logger.error(f"❌ HTTP error fetching orders (Page {page_num}, URL: {e.request.url}): {e.response.status_code} - {e.response.text[:500]}")
            return [] # Stop processing on this error
        except requests.exceptions.Timeout:
            logger.error(f"❌ Timeout while fetching orders (Page {page_num}, URL: {current_endpoint_url}).")
            return []
        except requests.exceptions.RequestException as e: # Catch other network errors
            logger.error(f"❌ Network error fetching orders (Page {page_num}, URL: {current_endpoint_url}): {e}")
            return []
        except ValueError: # Includes JSONDecodeError
            logger.error(f"❌ Failed to decode JSON response from Shopify (Page {page_num}). Response: {response.text[:500]}")
            return []

    if not all_orders:
        logger.info("No orders found matching the criteria after checking all pages.")
        return []

    logger.info(f"Successfully fetched a total of {len(all_orders)} orders after processing all pages.")
    
    # --- Sales Aggregation (Corrected to use actual quantity) ---
    product_sales_counter = {}
    for order in all_orders:
        for li in order.get("line_items", []):
            product_id = li.get("product_id")
            # The title from line_item is usually the product title.
            # If variants have distinct titles you want to preserve, consider li.get("name")
            # which is often "Product Title - Variant Title".
            item_title = li.get("title") 
            quantity_sold = li.get("quantity", 0) # Default to 0 if quantity somehow missing

            if product_id is None: # Skip line items that are not actual products
                logger.debug(f"Skipping line item without product_id (e.g., shipping, custom item): {li.get('name', 'N/A')}")
                continue
            
            # Using (product_id, item_title) as the key for aggregation.
            # This means if a product has variants with different titles in line items, they might be separate.
            # If you want to aggregate strictly by product_id, you might need to fetch the canonical product title once per product_id.
            aggregation_key = (product_id, item_title) 
            product_sales_counter[aggregation_key] = product_sales_counter.get(aggregation_key, 0) + quantity_sold

    # Prepare the final list, filtering by min_sales
    sold_products_list = [
        {
            "product_id": pid, 
            "title": title, # This is the title from the line item used for aggregation
            "sales_count": count
        }
        for (pid, title), count in product_sales_counter.items() 
        if count >= min_sales
    ]
    
    logger.info(f"Aggregated sales for {len(product_sales_counter)} unique product-title combinations. "
                f"{len(sold_products_list)} items met the minimum sales criteria of {min_sales}.")

    return sold_products_list

# In shopify_utils.py
# Ensure 'requests', 'logging', 'json' are imported if not already
# from .your_module import ensure_https # If ensure_https is in a different local module

def clone_product(source_product_data: Dict[str, Any], target_store_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Clones a product to a target Shopify store.

    Args:
        source_product_data: Dictionary containing the source product's data.
        target_store_config: Dictionary containing target store's 'shopify_store_url',
                             'shopify_api_key', and potentially 'api_version'.

    Returns:
        A dictionary with 'cloned_product_gid', 'target_handle', and 'cloned_product_id' on success,
        or a dictionary with 'error' on failure.
    """
    target_store_url = target_store_config.get("shopify_store_url")
    target_api_key = target_store_config.get("shopify_api_key")
    api_version = target_store_config.get("api_version", os.getenv("SHOPIFY_API_VERSION", "2024-04")) # More robust default

    if not target_store_url or not target_api_key:
        logger.error("❌ Target store URL or API key missing in target_store_config for cloning.")
        return {"error": "Missing target store credentials in config."}

    # Ensure target_store_url has a scheme (https://)
    # Assuming ensure_https is defined elsewhere in this file or imported
    if not target_store_url.startswith("http://") and not target_store_url.startswith("https://"):
        target_store_url = f"https://{target_store_url}" # Simplified ensure_https logic

    target_api_base = f"{target_store_url.rstrip('/')}/admin/api/{api_version}"
    endpoint = f"{target_api_base}/products.json"

    headers = {
        "X-Shopify-Access-Token": target_api_key,
        "Content-Type": "application/json"
    }
    
    # --- Prepare the payload for the new product ---
    # Get body_html from source once
    source_body_html_for_payload = source_product_data.get("body_html", "") 

    new_product_payload = {
        "product": {
            "title": source_product_data.get("title", "Cloned Product") + " (Clone)", # Add suffix
            "body_html": source_body_html_for_payload, # Use the variable
            "vendor": source_product_data.get("vendor", ""),
            "product_type": source_product_data.get("product_type", ""),
            # "handle": Let Shopify auto-generate from the new title to avoid conflicts.
            #           The handle can be updated later with a translated/cleaned version.
            "status": "active",  # Clone as draft initially
            "tags": source_product_data.get("tags", ""),
            "options": source_product_data.get("options", []), # Copies option names and their original values
            "variants": [], # Will be populated below
            "images": []    # Will be populated below
        }
    }

    # Log the body_html being sent in the payload
    logger.info(f"clone_product: Payload body_html for Shopify API (length: {len(source_body_html_for_payload) if source_body_html_for_payload else 'None/Empty'}). First 100 chars: '{source_body_html_for_payload[:100] if source_body_html_for_payload else 'N/A'}'")

    # Variant cloning
    source_variants = source_product_data.get("variants", [])
    if source_variants:
        for svar in source_variants:
            new_var = {
                "option1": svar.get("option1"),
                "option2": svar.get("option2"),
                "option3": svar.get("option3"),
                "price": svar.get("price"),
                "sku": svar.get("sku", ""),
                "requires_shipping": svar.get("requires_shipping", True),
                "taxable": svar.get("taxable", True),
                "barcode": svar.get("barcode"),
                "weight": svar.get("weight"),
                "weight_unit": svar.get("weight_unit"),
                # Consider inventory_quantity, inventory_management, inventory_policy carefully
            }
            new_var_cleaned = {k: v for k, v in new_var.items() if v is not None}
            new_product_payload["product"]["variants"].append(new_var_cleaned)
    elif not new_product_payload["product"]["options"]: # No product-level options defined
         # If no variants and no options, Shopify REST API often expects a default variant or creates one.
         # Providing a basic price ensures a variant is created.
         default_variant_price = "0.00"
         if source_product_data.get("variants") and source_product_data["variants"][0].get("price"):
             default_variant_price = source_product_data["variants"][0]["price"]
         new_product_payload["product"]["variants"] = [{"price": default_variant_price}]


    # Image cloning
    source_images = source_product_data.get("images", [])
    if source_images:
        for simg in source_images:
            if simg.get("src"):
                new_product_payload["product"]["images"].append({"src": simg.get("src")})
    
    logger.info(f"Attempting to create cloned product on target store: {target_store_url} with title '{new_product_payload['product']['title']}'")
    logger.debug(f"Clone payload (brief): {{'product': {{'title': '{new_product_payload['product']['title']}', 'variants_count': {len(new_product_payload['product']['variants'])}, 'images_count': {len(new_product_payload['product']['images'])}}}}}")

    try:
        response = requests.post(endpoint, json=new_product_payload, headers=headers, timeout=30)
        
        if response.status_code == 429: # Rate limit
            retry_after = int(response.headers.get("Retry-After", 15))
            logger.warning(f"Rate limited by Shopify (cloning product). Retrying after {retry_after}s...")
            time.sleep(retry_after)
            response = requests.post(endpoint, json=new_product_payload, headers=headers, timeout=30)

        response.raise_for_status()  # Raise an exception for HTTP error codes (4xx or 5xx)
        
        # Use a single variable for the response product data
        cloned_product_data_from_response = response.json().get("product")

        if cloned_product_data_from_response and cloned_product_data_from_response.get("id"):
            # CRITICAL LOGGING for body_html in Shopify's immediate response
            response_body_html = cloned_product_data_from_response.get("body_html")
            logger.info(f"clone_product: Shopify's IMMEDIATE RESPONSE for new product ID {cloned_product_data_from_response.get('id')} includes body_html (length: {len(response_body_html) if response_body_html else 'None/Empty in response'}). First 100 chars: '{response_body_html[:100] if response_body_html else 'N/A'}'")
            
            logger.info(f"✅ Product cloned successfully to target store. New Product ID: {cloned_product_data_from_response.get('id')}, GID: {cloned_product_data_from_response.get('admin_graphql_api_id')}")
            return {
                "cloned_product_id": cloned_product_data_from_response.get("id"),
                "cloned_product_gid": cloned_product_data_from_response.get("admin_graphql_api_id"),
                "target_handle": cloned_product_data_from_response.get("handle"), 
                "full_response": cloned_product_data_from_response 
            }
        else:
            logger.error(f"❌ Clone API call succeeded (status {response.status_code}) but response did not contain expected product data. Response: {response.text[:500]}")
            return {"error": "Clone successful but response malformed", "details": response.text[:500]}

    except requests.exceptions.HTTPError as e:
        error_details = e.response.text[:500] if hasattr(e, 'response') and e.response is not None else str(e)
        status_code_info = e.response.status_code if hasattr(e, 'response') and e.response is not None else 'N/A'
        logger.error(f"❌ HTTP error cloning product: {status_code_info} - {error_details}")
        return {"error": f"HTTP {status_code_info}", "details": error_details}
    except requests.exceptions.Timeout:
        logger.error(f"❌ Timeout while cloning product to {target_store_url}.")
        return {"error": "Timeout during clone"}
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Network error while cloning product: {e}")
        return {"error": f"Network error: {e}"}
    except ValueError: # Includes JSONDecodeError
        resp_text = response.text[:500] if 'response' in locals() and response is not None else "No response object available"
        logger.error(f"❌ Failed to decode JSON response after cloning. Response: {resp_text}")
        return {"error": "JSON decode error after clone", "details": resp_text}

    return {"error": "Unknown error during cloning"}


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
    
def slugify(text): 
    """
    Convert text to a URL-friendly slug.
    """
    return (
        text.lower()
            .strip()
            .replace(" ", "-")
            .replace("ä", "ae")
            .replace("ö", "oe")
            .replace("ü", "ue")
            .replace("ß", "ss")
            .replace("/", "-")
            .replace("|", "-")
    )

def extract_name_from_title(title: str) -> str:
    """
    Extracts the human name from a product title like 'Daisy | 3-Piece Lingerie Set'.
    Returns the part before the pipe character.
    """
    if "|" in title:
        return title.split("|")[0].strip()
    return title.strip()

def add_product_to_collection(product_id: int, collection_id: int, session: dict) -> bool:
    """
    Adds a product to a manual (custom) collection via Shopify's Collects API.
    session = {'store_url': 'store.myshopify.com', 'access_token': 'X'}
    """
    url = f"https://{session['store_url']}/admin/api/2024-04/collects.json"
    headers = {
        "X-Shopify-Access-Token": session["access_token"],
        "Content-Type": "application/json"
    }
    payload = {
        "collect": {
            "product_id": int(product_id),
            "collection_id": int(collection_id)
        }
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        if resp.status_code == 201:
            logging.info(f"✅ Successfully added product {product_id} to collection {collection_id}.")
            return True
        else:
            logging.error(f"❌ Failed to add to collection: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        logging.error(f"❌ Exception in add_product_to_collection: {e}")
        return False
        
def smart_round(price):
    """
    Rounds the price up to common psychological price points (24.99, 49.99, ...), otherwise next multiple of 25 minus 0.01.
    """
    intervals = [24.99, 49.99, 74.99, 99.99, 124.99, 149.99, 174.99, 199.99, 224.99, 249.99]
    for val in intervals:
        if price <= val:
            return val
    return (int(price // 25) * 25 + 24.99)

def update_variant(
    store_url: str,
    api_key: str,
    payload: dict,
    api_version: str = "2024-04",
    apply_smart_round: bool = True,
    double_compare_price: bool = True,
    compare_at_integer: bool = True
) -> dict:
    """
    Updates a single Shopify product variant (e.g., to change price) via REST API.
    If apply_smart_round is True, price is rounded up to common values.
    If double_compare_price and compare_at_integer are True, sets compare_at_price as a pure integer (e.g., 199 -> 400).
    """
    print("USING UPDATED update_variant FUNCTION!")
    variant = payload.get("variant", {})
    variant_id = variant.get("id")
    if not variant_id:
        logger.error("update_variant: No variant ID in payload")
        return {"error": "Missing variant ID"}

    # Price logic
    price = float(variant.get("price"))
    if apply_smart_round:
        price = smart_round(price)
        payload["variant"]["price"] = price

    # Set compare_at_price
    if double_compare_price:
        if compare_at_integer:
            compare_at_price = int(round(price * 2, 0))  # e.g. 199 -> 398, 199.99 -> 400
            # Always round up to the next full 100 if you want 199 -> 400, 149 -> 300
            # Use math.ceil if you want that effect:
            # import math
            # compare_at_price = int(math.ceil(price * 2 / 100.0)) * 100
        else:
            compare_at_price = price * 2  # Not rounded to integer

        payload["variant"]["compare_at_price"] = compare_at_price

    endpoint = f"https://{store_url.replace('https://','').replace('http://','')}/admin/api/{api_version}/variants/{variant_id}.json"
    headers = {
        "X-Shopify-Access-Token": api_key,
        "Content-Type": "application/json"
    }
    try:
        resp = requests.put(endpoint, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"update_variant failed: {e} | Response: {getattr(e, 'response', None)}")
        return {"error": str(e)}

