# File: export_weekly.py
# Description: Main script for weekly Shopify job. Includes core Shopify/processing logic definitions.

import os
import sys
import time
import json
import logging
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import random
import requests # For helpers defined here
import re       # For helpers defined here
from threading import Lock
from typing import Any, Dict, Union, Optional, List, Tuple # For type hints

# --- Import TRUE Utility Modules ---
# These modules contain logic NOT defined directly below
try:
    import google_sheets_utils # Handles direct sheet interactions
    # translation_utils will contain apply_translation_method etc.
    # but the main orchestrators are defined locally below
    import translation_utils
    import text_processing_utils # Handles slugify, text cleaning etc.
    # shopify_utils might still be imported if it contains other helpers,
    # but core API functions used by local definitions are defined here.
    # Let's assume it's not needed for direct calls from main() or local funcs.
    # import shopify_utils
except ImportError as e:
    missing_module = str(e).split("'")[-2] if "No module named" in str(e) else "a required utility module"
    print(f"❌ CRITICAL ERROR: Failed to import required helper module: '{missing_module}'. {e}")
    print("   Ensure google_sheets_utils.py, translation_utils.py (with base functions),")
    print("   text_processing_utils.py, and variant_utils_cron.py exist.")
    sys.exit(1)

# --- Import variant utils AND DEFINE FLAG ---
# This needs to be done *before* _translate_product_variants is defined/used
try:
    import variant_utils_cron # Import the variant module
    VARIANT_UTILS_AVAILABLE = True # Define flag as True if import succeeds
    logging.info("Successfully imported variant_utils_cron.")
except ImportError:
    # Use print before logger might be fully configured
    print("ERROR: Failed to import 'variant_utils_cron'. Variant functions unavailable.")
    logging.error("Failed to import 'variant_utils_cron'. Variant functions unavailable.")
    VARIANT_UTILS_AVAILABLE = False # Define flag as False if import fails

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s:%(lineno)d] - %(message)s',
    handlers=[ logging.StreamHandler(sys.stdout) ]
)
logger = logging.getLogger("ExportWeeklyScript")

# --- Global Constants / Variables ---
DEFAULT_API_VERSION = "2024-04"
currently_processing_lock = Lock()
currently_processing_ids = set()
SOURCE_STORE_URL = os.getenv("SHOPIFY_STORE_URL") # Load needed globals after imports
SOURCE_API_KEY = os.getenv("SHOPIFY_API_KEY")


# --- HELPER FUNCTION DEFINITIONS (Defined Locally in export_weekly.py) ---

def ensure_https(url):
    if not url or not isinstance(url, str): return None
    url = url.strip()
    if not url.startswith("http://") and not url.startswith("https://"): return f"https://{url}"
    return url

def shopify_api_request(method, url, api_key, **kwargs):
    """Basic REST helper defined locally."""
    json_payload = kwargs.pop("json", None); timeout = kwargs.pop("timeout", 30)
    headers = kwargs.pop("headers", {}); headers["X-Shopify-Access-Token"] = api_key
    headers.setdefault("Content-Type", "application/json"); headers.setdefault("User-Agent", "Python-Cron-Job/1.1")
    if 'api_key' in kwargs: del kwargs['api_key']
    try:
        logger.debug(f"API Req: {method} {url}")
        response = requests.request(method, url, headers=headers, json=json_payload, timeout=timeout, **kwargs)
        if not 200 <= response.status_code < 300: logger.error(f"API Error ({method} {url}): {response.status_code} {response.text[:200]}...")
        return response
    except requests.exceptions.Timeout: logger.error(f"Timeout ({timeout}s) for {method} {url}"); return None
    except requests.exceptions.RequestException as e: logger.exception(f"Network error for {method} {url}"); return None
    except Exception as e: logger.exception(f"Unexpected error for {url}"); return None

def shopify_graphql_request(query, variables, shopify_store_url, shopify_api_key, api_version=DEFAULT_API_VERSION):
    """Basic GraphQL helper defined locally."""
    endpoint = f"{ensure_https(shopify_store_url)}/admin/api/{api_version}/graphql.json"
    headers = {"X-Shopify-Access-Token": shopify_api_key, "Content-Type": "application/json"}
    payload = {"query": query, "variables": variables}
    try:
        logger.debug(f"GQL Req to {endpoint}")
        response = requests.post(endpoint, json=payload, headers=headers, timeout=60)
        if response.status_code != 200: logger.error(f"GQL error: {response.status_code} - {response.text[:200]}")
        # Always try to return JSON, let caller handle 'errors' key
        return response.json()
    except requests.exceptions.RequestException as e: logger.exception(f"GQL network error"); return None
    except json.JSONDecodeError as e: logger.error(f"GQL JSON decode error: {e}. Resp: {response.text[:200]}"); return None
    except Exception as e: logger.exception(f"GQL unexpected error"); return None

def fetch_product_by_id(product_id_str: str) -> dict | None:
    """Fetches source product using globally defined URL/Key."""
    source_url = os.getenv("SHOPIFY_STORE_URL"); source_key = os.getenv("SHOPIFY_API_KEY")
    if not source_url or not source_key: logger.error("fetch_product_by_id: Source URL/Key missing."); return None
    url = f"{ensure_https(source_url)}/admin/api/{DEFAULT_API_VERSION}/products/{product_id_str}.json"
    logger.debug(f"Fetching source product {product_id_str}")
    response = shopify_api_request("GET", url, source_key) # Calls local helper
    if response and response.status_code == 200:
        try: return response.json().get("product")
        except json.JSONDecodeError: logger.error(f"JSON decode error fetch src {product_id_str}"); return None
    else: logger.warning(f"Failed fetch src {product_id_str}. Status: {response.status_code if response else 'N/A'}"); return None

def fetch_product_by_gid(product_gid, shopify_store_url, shopify_api_key):
    """Fetches product by GID using locally defined GQL helper."""
    logger.debug(f"Fetching GID {product_gid} from {shopify_store_url}")
    query = """
    query getProduct($id: ID!) {
      product(id: $id) { id title handle bodyHtml vendor productType tags
        options{id name position values}
        images(first: 20){edges{node{id src altText}}}
        variants(first: 50){edges{node{id legacyResourceId title sku barcode price compareAtPrice inventoryPolicy inventoryQuantity weight weightUnit requiresShipping taxable image{id src altText} selectedOptions{name value}}}}
      } } """
    variables = {"id": product_gid}
    response_json = shopify_graphql_request(query, variables, shopify_store_url, shopify_api_key) # Calls local helper

    if response_json and 'data' in response_json and 'product' in response_json['data']:
        product_data = response_json['data']['product']
        # Basic error check within response
        if response_json.get('errors'): logger.error(f"GraphQL errors fetching GID {product_gid}: {response_json['errors']}") # Log errors but still return data if present
        # Simplify images/variants
        if product_data and product_data.get("images", {}).get("edges"): product_data["images_flat"] = [edge["node"] for edge in product_data["images"]["edges"]]
        else: product_data["images_flat"] = []
        if product_data and product_data.get("variants", {}).get("edges"): product_data["variants_flat"] = [edge["node"] for edge in product_data["variants"]["edges"]]
        else: product_data["variants_flat"] = []
        return product_data
    else:
        logger.error(f"Failed GraphQL fetch for GID {product_gid}. Response: {response_json}")
        return None

def fetch_product_by_handle(handle: str, target_store_url: str, target_api_key: str) -> dict | None:
     """Fetches product by handle from TARGET store."""
     url = f"{ensure_https(target_store_url)}/admin/api/{DEFAULT_API_VERSION}/products.json?handle={handle}"
     logger.debug(f"Checking handle '{handle}' on {target_store_url}")
     response = shopify_api_request("GET", url, target_api_key) # Calls local helper
     if response and response.status_code == 200:
         try: products = response.json().get("products", []); return products[0] if products else None
         except json.JSONDecodeError: logger.error(f"JSON decode error check handle {handle}"); return None
     else: logger.debug(f"Handle check fail/not found. Status: {response.status_code if response else 'N/A'}"); return None

def add_product_to_collection_rest(product_rest_id: int | str, collection_rest_id: int | str, target_store_url: str, target_api_key: str) -> bool:
    """Adds product to collection via REST."""
    logger.info(f"Attempting add product {product_rest_id} to collection {collection_rest_id}")
    collect_url = f"{ensure_https(target_store_url)}/admin/api/{DEFAULT_API_VERSION}/collects.json"
    try: collect_payload = {"collect": {"product_id": int(product_rest_id),"collection_id": int(collection_rest_id)}}
    except ValueError: logger.error(f"Invalid non-numeric ID for collect: {product_rest_id}/{collection_rest_id}"); return False
    response = shopify_api_request("POST", collect_url, api_key=target_api_key, json=collect_payload) # Calls local helper
    if response and response.status_code in [200, 201]: logger.info("Added to collection."); return True
    elif response and response.status_code == 422 and "product_id Has already been taken" in response.text: logger.warning(f"Already in collection."); return True
    else: logger.error(f"Failed add collection. Status: {response.status_code if response else 'N/A'}"); return False

def get_sold_product_details(start_date: str, end_date: str, min_sales: int) -> list | None:
    """Fetches product sales data using global source creds."""
    source_url = os.getenv("SHOPIFY_STORE_URL"); source_key = os.getenv("SHOPIFY_API_KEY")
    if not source_url or not source_key: logger.error("get_sold_product_details: Source URL/Key missing."); return None
    logger.info(f"Fetching sales {start_date} to {end_date} (Min: {min_sales}) from {source_url}")
    endpoint_path = f"/admin/api/{DEFAULT_API_VERSION}/orders.json?status=any&created_at_min={start_date}T00:00:00Z&created_at_max={end_date}T23:59:59Z&fields=line_items&limit=250"
    base_url = ensure_https(source_url); next_page_url = f"{base_url}{endpoint_path}"; all_orders = []; headers = {"X-Shopify-Access-Token": source_key};
    while next_page_url:
        logger.debug(f"Fetching orders page: {next_page_url}");
        try: response = requests.get(next_page_url, headers=headers, timeout=90); response.raise_for_status();
        except requests.exceptions.RequestException as e: logger.error(f"Network error fetching orders: {e}"); return None
        try: data = response.json(); orders_page = data.get("orders", [])
        except json.JSONDecodeError: logger.error("Failed JSON decode orders."); return None
        all_orders.extend(orders_page); link_header = response.headers.get('Link'); next_page_url = None;
        if link_header:
            links = requests.utils.parse_header_links(link_header);
            for link in links:
                if link.get('rel') == 'next': next_page_url = link.get('url'); logger.info("   Found next page link."); break
        if next_page_url: time.sleep(0.6); 
        else: logger.info("   No more pages.");
    logger.info(f"Fetched {len(all_orders)} orders."); counter = {};
    for order in all_orders:
        for li in order.get("line_items", []):
            pid = li.get("product_id"); title = li.get("title");
            if pid and title: key = (str(pid), title.strip()); counter[key] = counter.get(key, 0) + li.get("quantity", 1);
            else: logger.warning("Skip line item: missing ID/Title");
    sold_list = [{"product_id": pid, "title": title, "sales_count": count} for (pid, title), count in counter.items() if count >= min_sales];
    logger.info(f"Found {len(sold_list)} combinations meeting sales criteria ({min_sales})."); return sold_list

# --- NEW: update_product_fields defined LOCALLY ---
def update_product_fields(product_gid: str, api_key: str, store_url: str, title: str = None, body_html: str = None, handle: str = None, status: str = None) -> dict:
    """Updates specified Shopify product fields via GraphQL."""
    if not product_gid or not store_url or not api_key: logger.error("update_product_fields: Missing args."); return {"_success": False, "_error": True, "_message": "Missing required arguments."}
    input_payload = {"id": product_gid}
    if title is not None: input_payload["title"] = title
    if body_html is not None: input_payload["bodyHtml"] = body_html
    if handle is not None: input_payload["handle"] = handle
    if status is not None: input_payload["status"] = status.upper()
    if len(input_payload) <= 1: logger.warning("update_product_fields: No fields specified."); return {"_success": True, "_message": "No fields to update."}
    mutation = """ mutation productUpdate($input: ProductInput!) { productUpdate(input: $input) { product { id title handle status bodyHtml } userErrors { field message } } } """
    variables = {"input": input_payload}
    logger.info(f"Updating GID: {product_gid}. Fields: {list(input_payload.keys() - {'id'})}")
    # Calls the LOCAL shopify_graphql_request helper
    response_json = shopify_graphql_request(mutation, variables, store_url, api_key)
    # Basic response check based on local helper return
    if response_json and 'data' in response_json and 'productUpdate' in response_json['data'] and not response_json['data']['productUpdate'].get('userErrors'):
        logger.info(f"✅ GQL update successful for {product_gid}"); return {"_success": True, "data": response_json['data']}
    else:
        errors = response_json.get('errors') or response_json.get('data',{}).get('productUpdate',{}).get('userErrors') if response_json else "Request failed"
        logger.error(f"❌ GQL update failed for {product_gid}. Errors: {errors}"); return {"_success": False, "_error": True, "_message": "GQL update failed", "_details": errors}


# --- Core function to perform the clone ---
def _attempt_single_product_clone(original_pid_str: str, target_store_config: dict) -> dict | None:
    """Attempts single clone using helpers defined in this file."""
    log_prefix = f"[{original_pid_str} -> {target_store_config.get('value')}]"
    target_store_url = target_store_config.get("shopify_store_url")
    target_api_key = target_store_config.get("shopify_api_key")
    target_store_value = target_store_config.get("value", "UNKNOWN")
    pinterest_id = target_store_config.get("pinterest_collection_rest_id")
    status_sheet_name = os.getenv("STATUS_SHEET_NAME", "Sheet1")

    try:
        logger.info(f"{log_prefix} Attempting Clone")
        # Fetch source (calls local helper)
        source_data = fetch_product_by_id(original_pid_str)
        if not source_data: google_sheets_utils.update_export_status_for_store(original_pid_str, target_store_value, "ERROR_FETCHING_SOURCE", None, None, status_sheet_name); return None
        source_title = source_data.get("title", "").strip()
        if not source_title: google_sheets_utils.update_export_status_for_store(original_pid_str, target_store_value, "ERROR_EMPTY_SOURCE_TITLE", None, None, status_sheet_name); return None

        # Check Handle (calls local helper, uses imported util)
        base_handle = text_processing_utils.slugify(source_title)
        if not base_handle: logger.error(f"{log_prefix} Failed base handle gen."); google_sheets_utils.update_export_status_for_store(original_pid_str, target_store_value, "ERROR_HANDLE_GENERATION", None, None, status_sheet_name); return None
        cloned_handle = base_handle; counter = 1; max_attempts = 10;
        while True:
            existing = fetch_product_by_handle(cloned_handle, target_store_url, target_api_key)
            if not existing: logger.info(f"{log_prefix} Handle '{cloned_handle}' unique."); break
            logger.warning(f"{log_prefix} Handle '{cloned_handle}' exists.");
            if counter >= max_attempts: logger.error(f"{log_prefix} Max handle attempts."); google_sheets_utils.update_export_status_for_store(original_pid_str, target_store_value, "ERROR_HANDLE_GENERATION", None, None, status_sheet_name); return None
            cloned_handle = f"{base_handle}-{counter}"; counter += 1; time.sleep(0.2);

        # Construct Payload (logic from previous)
        logger.info(f"{log_prefix} Preparing payload (handle: {cloned_handle})...")
        # ... [ Assume full payload construction logic is here as before ] ...
        title = source_title; description = source_data.get("body_html", ""); vendor = source_data.get("vendor"); product_type = source_data.get("product_type"); tags_list = source_data.get("tags", []);
        if isinstance(tags_list, str): tags_list = [t.strip() for t in tags_list.split(',') if t.strip()];
        if not isinstance(tags_list, list): tags_list = [];
        if "ClonedForTranslation" not in tags_list: tags_list.append("ClonedForTranslation");
        tags_string = ", ".join(tags_list); images_input = [{"src": img.get("src")} for img in source_data.get("images", []) if isinstance(img, dict) and img.get("src")]; rest_options = []; option_names = []; source_options = source_data.get('options', []);
        if isinstance(source_options, list) and source_options:
             for i, opt in enumerate(source_options):
                 if isinstance(opt, dict) and opt.get('name'): rest_options.append({"name": opt['name'], "position": opt.get('position', i + 1)}); option_names.append(opt['name']);
        rest_variants_initial = []; source_variants = source_data.get('variants', []);
        if isinstance(source_variants, list) and source_variants:
             for i, sv in enumerate(source_variants):
                 if not isinstance(sv, dict): continue;
                 variant_payload = { "price": str(sv.get('price', '0.00')), "sku": f"CLONE-{original_pid_str}-{sv.get('sku', sv.get('id', ''))}", "compare_at_price": str(sv.get('compare_at_price')) if sv.get('compare_at_price') is not None else None, "barcode": sv.get('barcode'), "inventory_policy": "deny" if sv.get('inventory_management') == 'shopify' else "continue", "requires_shipping": sv.get('requires_shipping', True), "taxable": sv.get('taxable', True), "weight": sv.get('weight'), "weight_unit": sv.get('weight_unit', 'kg') if sv.get('weight') is not None else None, **({f"option{idx+1}": sv.get(f"option{idx+1}") for idx in range(len(option_names)) if sv.get(f"option{idx+1}") is not None}) };
                 rest_variants_initial.append({k: v for k, v in variant_payload.items() if v is not None});
        product_payload_data = { "title": title, "body_html": description, "handle": cloned_handle, "status": "active", "published": True, **({"vendor": vendor} if vendor else {}), **({"product_type": product_type} if product_type else {}), "tags": tags_string, **({"images": images_input} if images_input else {}), **({"options": rest_options} if rest_options else {}), **({"variants": rest_variants_initial} if rest_variants_initial else {}), };
        product_payload = {"product": {k: v for k, v in product_payload_data.items() if v is not None}};

        # Create Product (calls local helper)
        logger.info(f"{log_prefix} Creating product via API...")
        create_url = f"{ensure_https(target_store_url)}/admin/api/{DEFAULT_API_VERSION}/products.json"
        response = shopify_api_request("POST", create_url, api_key=target_api_key, json=product_payload, timeout=90)

        # Process Response
        if response and response.status_code in [200, 201]:
            try: new_product = response.json().get("product")
            except json.JSONDecodeError: logger.error(f"{log_prefix} Clone success, JSON decode fail."); google_sheets_utils.update_export_status_for_store(original_pid_str, target_store_value, "ERROR_CLONE_RESPONSE_JSON", None, None, status_sheet_name); return None
            if new_product:
                cloned_gid = new_product.get("admin_graphql_api_id"); cloned_title = new_product.get("title", ""); cloned_rest_id = new_product.get("id"); logger.info(f"{log_prefix} ✅ Clone successful. GID: {cloned_gid}");
                clone_result = { "_success": True, "admin_graphql_api_id": cloned_gid, "title": cloned_title };
                if cloned_rest_id and pinterest_id: add_product_to_collection_rest(cloned_rest_id, pinterest_id, target_store_url, target_api_key) # Calls local helper
                logger.info(f"{log_prefix} Updating sheet status to CLONED...")
                google_sheets_utils.update_export_status_for_store(original_pid_str, target_store_value, f"CLONED_{target_store_value.upper()}", cloned_gid, cloned_title, status_sheet_name)
                return clone_result # Success
            else: logger.error(f"{log_prefix} Clone success but no 'product'."); google_sheets_utils.update_export_status_for_store(original_pid_str, target_store_value, "ERROR_CLONE_RESPONSE", None, None, status_sheet_name); return None
        else: status = response.status_code if response else 'N/A'; logger.error(f"{log_prefix} Clone failed. Status: {status}."); google_sheets_utils.update_export_status_for_store(original_pid_str, target_store_value, "ERROR_CLONING", None, None, status_sheet_name); return None

    except Exception as e:
        logger.exception(f"{log_prefix} 🔥 Unhandled Exception in clone attempt: {e}")
        try: google_sheets_utils.update_export_status_for_store(original_pid_str, target_store_value, "ERROR_EXCEPTION", None, None, status_sheet_name)
        except Exception as log_err: logger.error(f"{log_prefix} Failed log EXCEPTION status: {log_err}")
        return None # Failure

# ADD THIS FUNCTION DEFINITION TO export_weekly.py
# (Place it BEFORE the 'translate_cloned_product' function definition)
# Ensure VARIANT_UTILS_AVAILABLE flag is defined globally near top imports

def _translate_product_variants(
    product_gid: str,
    target_store_config: Dict[str, Any],
    variant_method_config: Union[str, Dict[str, Any]],
    target_language: str,
    source_language: str
    ) -> bool:
    """
    Handles fetching, translating, and updating ONLY the variant options for a product.
    Uses functions from variant_utils_cron. Intended to be called by translate_cloned_product.
    [Internal Function defined in export_weekly.py]
    """
    # Access the flag defined globally in this script
    # global VARIANT_UTILS_AVAILABLE # Usually not needed if defined at module level before function
    log_prefix = f"[{product_gid} -> Lang: {target_language} -> Variants]"
    variant_success = True

    target_store_url = target_store_config.get("shopify_store_url")
    target_api_key = target_store_config.get("shopify_api_key")
    if not target_store_url or not target_api_key: logger.error(f"{log_prefix} Missing target URL/Key."); return False

    variant_method_name = variant_method_config.get("method").lower() if isinstance(variant_method_config, dict) else str(variant_method_config).lower()

    if variant_method_name == 'none': logger.info(f"{log_prefix} Skipping variant translation."); return True

    logger.info(f"{log_prefix} Starting Variant translation using '{variant_method_name}'...")

    # Check the global flag defined near the top of export_weekly.py
    if not VARIANT_UTILS_AVAILABLE:
        logger.error(f"{log_prefix} Cannot translate variants - variant_utils_cron module import failed.")
        return False

    try:
        logger.info(f"{log_prefix} Fetching options via variant_utils_cron...")
        # Assumes variant_utils_cron is imported at the top of export_weekly.py
        options_to_translate = variant_utils_cron.get_product_option_values(
              product_gid, shopify_store_url=target_store_url, shopify_api_key=target_api_key
        )

        if options_to_translate is None: logger.error(f"{log_prefix} FAILED fetch options."); variant_success = False
        elif options_to_translate:
             logger.info(f"{log_prefix} Found {len(options_to_translate)} options. Looping...")
             all_options_succeeded = True
             for option_data in options_to_translate:
                 if not isinstance(option_data, dict) or not option_data.get("id") or not option_data.get("name"): logger.warning(f"{log_prefix} Skipping invalid option data."); continue
                 opt_name = option_data.get('name', '???');
                 logger.info(f"{log_prefix} Processing Option '{opt_name}'...")
                 # Assumes variant_utils_cron has update_product_option_values
                 single_success = variant_utils_cron.update_product_option_values(
                       product_gid=product_gid, option=option_data, target_language=target_language,
                       source_language=source_language, translation_method=variant_method_config,
                       shopify_store_url=target_store_url, shopify_api_key=target_api_key
                 )
                 logger.info(f"{log_prefix} Result for option '{opt_name}': {'OK' if single_success else 'FAIL'}")
                 if not single_success: all_options_succeeded = False; logger.error(f"{log_prefix} Update failed for '{opt_name}', stopping."); break
             variant_success = all_options_succeeded
        else: logger.info(f"{log_prefix} No options defined."); variant_success = True

    except AttributeError as ae: logger.error(f"{log_prefix} ❌ Variant func error: {ae}. Check variant_utils_cron.py."); variant_success = False
    except Exception as e: logger.exception(f"{log_prefix} ❌ Unexpected variant exception:"); variant_success = False

    logger.info(f"{log_prefix} Finished variant translation. Success: {variant_success}")
    return variant_success

# --- Main Translation Orchestration function (Defined LOCALLY) ---
def translate_cloned_product(product_gid: str, target_store_url: str, target_api_key: str, target_language: str, translation_methods: dict, source_language: str = "auto") -> bool:
    """
    Orchestrates the full translation of a cloned product (Title, Description, Variants).
    Defined within export_weekly.py. Calls _translate_product_variants (also local).
    Uses external translation_utils for apply_translation_method.
    Uses local update_product_fields.
    """
    log_prefix = f"[{product_gid} -> Lang: {target_language}]"
    logger.info(f"{log_prefix} --- Starting Full Translation Orchestration ---")
    td_success = False; variant_success = True # Reset status

    # Step 1: Fetch Product Data (using local helper)
    logger.info(f"{log_prefix} Fetching product data...")
    try: product_data = fetch_product_by_gid(product_gid, target_store_url, target_api_key);
    except Exception as e: logger.exception(f"{log_prefix} Fetch error."); return False
    if not product_data: logger.error(f"{log_prefix} Failed fetch."); return False;
    logger.info(f"{log_prefix} Fetched data.")

    # Step 2: Handle T/D/H (using local helpers and imported utils)
    logger.info(f"{log_prefix} Processing T/D/H...")
    try:
        original_title = product_data.get("title", ""); original_body = product_data.get("bodyHtml", ""); original_handle = product_data.get("handle", "")
        updates_payload = {"id": product_gid}; final_processed_title = original_title; title_translation_failed = False; body_processing_failed = False
        title_method_config = translation_methods.get('title', 'none'); desc_method_config = translation_methods.get('description', 'none')
        title_method_name = title_method_config.get("method").lower() if isinstance(title_method_config, dict) else str(title_method_config).lower()
        desc_method_name = desc_method_config.get("method").lower() if isinstance(desc_method_config, dict) else str(desc_method_config).lower()

        # 2a. Translate Title (uses imported translation_utils.apply_translation_method)
        if title_method_name != 'none':
            logger.info(f"{log_prefix}   Translating Title ({title_method_name})...")
            try:
                name_for_context = text_processing_utils.extract_name_from_title(original_title)
                # Call IMPORTED function from translation_utils module
                raw_title = translation_utils.apply_translation_method(original_text=original_title, method=title_method_config, custom_prompt="", source_lang=source_language, target_lang=target_language, field_type="title", product_title=original_title) # NO required_name
                if raw_title:
                    temp_title = text_processing_utils.post_process_title(raw_title)
                    cleaned_title = text_processing_utils.clean_title_output(temp_title, required_name=name_for_context)
                    final_title_constrained = text_processing_utils.apply_title_constraints(cleaned_title)
                    processed_title_candidate = final_title_constrained.strip()
                    if processed_title_candidate and processed_title_candidate != original_title: final_processed_title = processed_title_candidate; updates_payload["title"] = final_processed_title
                    elif not processed_title_candidate: logger.warning(f"{log_prefix}   Title empty."); title_translation_failed = True
                    else: logger.info(f"{log_prefix}   Title unchanged.")
                else: logger.warning(f"{log_prefix}   Raw title empty."); title_translation_failed = True
            except Exception as e: logger.exception(f"{log_prefix}   Error translating title."); title_translation_failed = True
        else: logger.info(f"{log_prefix} Skipping title translation.")

        # 2b. Generate Handle (uses imported text_processing_utils.slugify)
        if not title_translation_failed:
            logger.info(f"{log_prefix}   Generating Handle...")
            try:
                if final_processed_title:
                     new_handle = text_processing_utils.slugify(final_processed_title)
                     if new_handle and new_handle != original_handle: updates_payload["handle"] = new_handle; logger.info(f"{log_prefix}   Handle generated: {new_handle}")
                     else: logger.info(f"{log_prefix}   Handle unchanged.")
                else: logger.warning(f"{log_prefix}   Cannot generate handle, title empty.")
            except Exception as e: logger.exception(f"{log_prefix}   Error generating handle.")
        else: logger.warning(f"{log_prefix}   Skipping handle generation.")

        # 2c. Translate Description (uses imported translation_utils.apply_translation_method & text_processing_utils)
        if desc_method_name != 'none':
             logger.info(f"{log_prefix}   Translating Description ({desc_method_name})...")
             try:
                 if original_body and original_body.strip():
                     raw_body = translation_utils.apply_translation_method(original_text=original_body, method=desc_method_config, custom_prompt="", source_lang=source_language, target_lang=target_language, product_title=final_processed_title, field_type="description", description=original_body)
                     name_for_desc = text_processing_utils.extract_name_from_title(final_processed_title)
                     final_body = text_processing_utils.post_process_description(original_html=original_body, new_html=raw_body, method=desc_method_name, product_data=product_data, target_lang=target_language, final_product_title=final_processed_title, product_name=name_for_desc)
                     final_body = final_body.strip() if final_body else ""
                     if final_body and final_body != original_body: updates_payload["bodyHtml"] = final_body; logger.info(f"{log_prefix}   Desc translated/processed.")
                     elif not final_body: logger.warning(f"{log_prefix}   Desc empty.")
                     else: logger.info(f"{log_prefix}   Desc unchanged.")
                 else: logger.info(f"{log_prefix}   Original body empty.")
             except Exception as e: logger.exception(f"{log_prefix}   Error translating/processing description."); body_processing_failed = True
        else: logger.info(f"{log_prefix} Skipping description translation.")

        # 2d. Perform Shopify Update for T/D/H (calls LOCAL update_product_fields)
        gql_tdh_update_success = True
        if len(updates_payload) > 1:
            logger.info(f"{log_prefix}   Updating T/D/H via Shopify API...")
            try:
                update_response = update_product_fields(product_gid=product_gid, api_key=target_api_key, store_url=target_store_url, title=updates_payload.get("title"), body_html=updates_payload.get("bodyHtml"), handle=updates_payload.get("handle"))
                if not update_response or not update_response.get("_success"): logger.error(f"{log_prefix}   ❌ Failed T/D/H update. Resp: {update_response}"); gql_tdh_update_success = False
                else: logger.info(f"{log_prefix}   ✅ T/D/H update successful.")
            except Exception as e: logger.exception(f"{log_prefix}   Exception calling update_product_fields."); gql_tdh_update_success = False
        else: logger.info(f"{log_prefix}   No T/D/H changes to update.")

        td_success = gql_tdh_update_success and not title_translation_failed and not body_processing_failed

    except Exception as outer_td_err: logger.exception(f"{log_prefix} ❌ Error during T/D/H phase: {outer_td_err}"); td_success = False

    # Step 3: Handle Variant Translation (calls LOCAL _translate_product_variants)
    variants_method_config = translation_methods.get('variants', 'none')
    target_store_config = {"shopify_store_url": target_store_url, "shopify_api_key": target_api_key}
    variant_success = _translate_product_variants(
         product_gid=product_gid, target_store_config=target_store_config,
         variant_method_config=variants_method_config, target_language=target_language,
         source_language=source_language
     )

    overall_success = td_success and variant_success
    logger.info(f"{log_prefix} --- Finished Translation Orchestration. Overall Success: {overall_success} ---")
    return overall_success


# --- Main Execution Logic ---
def main():
    logger.info("--- Starting Weekly Export & Translate Cron Job ---")
    start_time = time.time()
    logger.info("Loading environment variables...")
    load_dotenv()

    # --- 1. Validate Env Vars ---
    SOURCE_STORE_URL = os.getenv("SHOPIFY_STORE_URL")
    SOURCE_API_KEY = os.getenv("SHOPIFY_API_KEY")
    TARGET_STORES_CONFIG_JSON = os.getenv("SHOPIFY_STORES_CONFIG")
    GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
    GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE")
    STATUS_SHEET_NAME = os.getenv("STATUS_SHEET_NAME", "Sheet1")
    # ... (Keep validation checks) ...
    critical_vars = { "Source Store URL": SOURCE_STORE_URL, "Source API Key": SOURCE_API_KEY, "Target Stores JSON": TARGET_STORES_CONFIG_JSON, "Google Sheet ID": GOOGLE_SHEET_ID, "Google Credentials File": GOOGLE_CREDENTIALS_FILE }; missing = [k for k, v in critical_vars.items() if not v];
    if missing: logger.critical(f"❌ Missing env vars: {', '.join(missing)}. Exit."); return
    if not os.path.exists(GOOGLE_CREDENTIALS_FILE): logger.critical(f"❌ Creds file not found: {GOOGLE_CREDENTIALS_FILE}. Exit."); return
    try: target_stores_list = json.loads(TARGET_STORES_CONFIG_JSON); assert isinstance(target_stores_list, list); logger.info(f"Loaded {len(target_stores_list)} target stores.")
    except Exception as e: logger.critical(f"❌ Failed parse stores config: {e}. Exit."); return

    # --- 2. Sheet Setup ---
    sheet1_header = None; sheet1_data_map = {};
    try:
        logger.info(f"Ensuring headers/fetching data: '{STATUS_SHEET_NAME}'")
        expected_header, headers_ok = google_sheets_utils.ensure_sheet_headers(STATUS_SHEET_NAME)
        if headers_ok and expected_header:
            sheet1_header = expected_header; logger.info("Fetching sheet data..."); fetched_header, sheet1_all_data = google_sheets_utils.get_sheet_data_by_header(STATUS_SHEET_NAME);
            if fetched_header != sheet1_header: logger.warning("Header mismatch fetch vs ensure."); sheet1_header = fetched_header if fetched_header else sheet1_header
            if sheet1_all_data is not None and sheet1_header:
                pid_col = "Product ID";
                if pid_col in sheet1_header: valid_rows = 0; [ (sheet1_data_map.update({pid: r}), valid_rows := valid_rows + 1) for r in sheet1_all_data if (pid := str(r.get(pid_col, "")).strip()) ]; logger.info(f"Created map: {valid_rows} IDs.")
                else: logger.error(f"'{pid_col}' header missing.")
            elif sheet1_all_data is None: logger.error("Could not fetch sheet data.")
        else: logger.error("Could not get header structure.")
    except Exception as e: logger.error(f"Sheet setup error: {e}", exc_info=True)

    # --- 3. Get Sold Products ---
    product_ids_to_export = []; sold_products_map = {};
    try:
        end_date = datetime.now(timezone.utc); days_lookback = int(os.getenv("SALES_DAYS_LOOKBACK", 7)); start_date = end_date - timedelta(days=days_lookback); start_date_str = start_date.strftime('%Y-%m-%d'); end_date_str = end_date.strftime('%Y-%m-%d'); min_sales = int(os.getenv("MIN_SALES", 1)); logger.info(f"Fetching sales {start_date_str} to {end_date_str} (Min: {min_sales})")
        sold_products_list = get_sold_product_details(start_date_str, end_date_str, min_sales) # Calls LOCAL function
        if sold_products_list is None: logger.error("Sales fetch failed. Exit."); return
        if not sold_products_list: logger.info("No products met sales criteria. Exit."); return
        logger.info(f"Found {len(sold_products_list)} combinations."); temp_ids = set(); [ (temp_ids.add(pid_str), sold_products_map.setdefault(pid_str, {"title": p.get("title", "N/A"), "sales_count": p.get("sales_count", 0)})) for p in sold_products_list if (pid_val := p.get('product_id')) and (pid_str := str(pid_val)) ]; product_ids_to_export = sorted(list(temp_ids));
        if not product_ids_to_export: logger.info("No valid IDs from sales. Exit."); return
        logger.info(f"Processing {len(product_ids_to_export)} unique IDs.")
    except Exception as e: logger.critical(f"Sales fetch error: {e}", exc_info=True); return

    # --- 3b. Add New Products to Sheet ---
    # ... (Keep Add New Products logic using google_sheets_utils as before) ...
    if sheet1_header:
        existing_ids_in_sheet = set(sheet1_data_map.keys()); new_product_ids_to_add = [pid for pid in product_ids_to_export if pid not in existing_ids_in_sheet];
        if new_product_ids_to_add:
            logger.info(f"Adding {len(new_product_ids_to_add)} new products to sheet..."); rows_to_add = []; num_cols = len(sheet1_header);
            for pid in new_product_ids_to_add: info = sold_products_map.get(pid, {}); row = [ pid, info.get("title", "N/A"), info.get("sales_count", 0) ]; row.extend([''] * (num_cols - len(row))); rows_to_add.append(row);
            if google_sheets_utils.add_new_product_rows(rows_to_add, STATUS_SHEET_NAME):
                logger.info("Added rows. Refetching map...");
                try: # Re-fetch map
                    hdr, data = google_sheets_utils.get_sheet_data_by_header(STATUS_SHEET_NAME);
                    if data is not None and hdr: sheet1_header = hdr; sheet1_data_map = {}; valid_rows = 0; pid_col = "Product ID";
                    if pid_col in hdr: [ (sheet1_data_map.update({pid: r}), valid_rows := valid_rows + 1) for r in data if (pid := str(r.get(pid_col, "")).strip()) ]; logger.info(f"Refreshed map ({valid_rows} IDs).")
                    else: logger.error("ID column missing during refresh.");
                except Exception as refetch_err: logger.error(f"Error refetching sheet: {refetch_err}", exc_info=True)
            else: logger.error("Failed add new rows.")
        else: logger.info("All sold products already in sheet.")
    else: logger.warning("Skipping add new - sheet header unknown.")

    success_translations = 0 # Initialize HERE
    failed_translations = 0  # Initialize HERE
    # -----------------------------------------
    # --- 4. Process Each Target Store and Product ---
    proc_count = 0; ok_clones = 0; fail_clones = 0; ok_trans = 0; fail_trans = 0;
    target_stores = target_stores_list if isinstance(target_stores_list, list) else []

    for store_config in target_stores:
        store_val = store_config.get("value"); store_url = store_config.get("shopify_store_url"); store_key = store_config.get("shopify_api_key"); store_lang = store_config.get("language") or "en";
        if not store_val or not store_url or not store_key: logger.error(f"Skipping store due to missing config: {store_config}."); continue
        logger.info(f"--- Processing Store: {store_val} (Lang: {store_lang}) ---")

        for original_pid in product_ids_to_export:
            proc_count += 1; log_prefix = f"[{original_pid} -> {store_val}]";
            cloned_gid = None; cloned_title = None; clone_ok = False; trans_ok = None; current_sheet_status = "STARTED";

            # Status Check from sheet1_data_map (as before)
            # ... [ Keep status check logic here using sheet1_data_map ] ...
            skip = False;
            if original_pid in sheet1_data_map and sheet1_header:
                row = sheet1_data_map[original_pid]; suffix = store_val.split('_')[-1].upper(); status_col = f"Status {suffix}"; gid_col = f"Cloned GID {suffix}"; title_col = f"Cloned Title {suffix}";
                if status_col in row:
                    status = str(row.get(status_col, "")).strip().upper(); done_statuses = {f"DONE_{store_val.upper()}", "APPROVED", "TRANSLATED"}; retry_errors = {"ERROR_TRANSLATING", "ERROR_VARIANT_TRANSLATION", "ERROR_MISSING_GID"};
                    if status in done_statuses: logger.info(f"{log_prefix} Skip: Done status '{status}'."); skip = True;
                    elif status.startswith("ERROR_") and status not in retry_errors: logger.info(f"{log_prefix} Skip: Non-retryable error '{status}'."); skip = True;
                    elif status.startswith("ERROR_") and status in retry_errors:
                        logger.warning(f"{log_prefix} Note: Retryable error '{status}'."); cloned_gid = row.get(gid_col, "").strip();
                        if cloned_gid: logger.info(f"{log_prefix} Found GID: {cloned_gid}"); clone_ok = True; cloned_title = row.get(title_col, "").strip();
                        else: logger.error(f"{log_prefix} Cannot retry '{status}': GID missing."); skip = True;
                else: logger.warning(f"{log_prefix} Status column '{status_col}' missing.")
            else: logger.warning(f"{log_prefix} Product ID not in sheet map.")
            if skip: continue

            # --- Main Processing Block ---
            try:
                # Update Status to PROCESSING (if not reprocessing)
                if not clone_ok:
                    current_sheet_status = f"PROCESSING_{store_val.upper()}"
                    try: google_sheets_utils.update_export_status_for_store(original_pid, store_val, current_sheet_status, "", "", STATUS_SHEET_NAME)
                    except Exception as sheet_err: logger.error(f"{log_prefix} Failed initial status update: {sheet_err}")

                # --- Clone Product (if needed) ---
                if not clone_ok:
                    # Calls the _attempt_single_product_clone defined LOCALLY
                    clone_result = _attempt_single_product_clone(original_pid, store_config)
                    if clone_result and clone_result.get("_success"):
                        cloned_gid = clone_result.get("admin_graphql_api_id"); cloned_title = clone_result.get("title"); clone_ok = True; ok_clones += 1;
                        # Status already updated inside _attempt_single_product_clone
                        current_sheet_status = f"CLONED_{store_val.upper()}" # Track status locally
                        logger.info(f"{log_prefix} Clone step successful.")
                    else:
                        clone_ok = False; fail_clones += 1; logger.info(f"{log_prefix} Clone step failed or skipped."); continue # Skip translation

                # --- Translate Product (if clone ok) ---
                if not cloned_gid: logger.error(f"{log_prefix} Cannot translate, GID missing."); continue

                logger.info(f"{log_prefix} Translating GID: {cloned_gid}...")
                methods = {"title": "deepseek", "description": "deepseek", "variants": "google"} # Example methods
                try:
                    # Calls translate_cloned_product defined LOCALLY
                    trans_ok = translate_cloned_product(
                        product_gid=cloned_gid, target_store_url=store_url, target_api_key=store_key,
                        target_language=store_lang, translation_methods=methods, source_language="auto"
                    )
                except Exception as trans_err: # Catch errors from the orchestration function
                    logger.exception(f"{log_prefix} ❌ Error calling translate_cloned_product: {trans_err}"); trans_ok = False

                # Update status based on translation result
                # Update status based on translation result
                if trans_ok is True: # Use 'is True' for explicit boolean check
                    success_translations += 1
                    logger.info(f"{log_prefix} ✅ Translation orchestration successful.")
                    # SET STATUS TO DONE ON SUCCESS
                    current_sheet_status = f"DONE_{store_val.upper()}"
                else: # This block runs only if trans_ok is False or None
                    failed_translations += 1
                    # Set status to ERROR only on failure
                    # Keep existing ERROR status if it was already set before translation attempt
                    if not current_sheet_status.startswith("ERROR_"):
                         current_sheet_status = f"ERROR_TRANSLATING_{store_val.upper()}"
                    logger.error(f"{log_prefix} ❌ Translation orchestration failed (Final Status set to: {current_sheet_status}).")

                # Final sheet update uses the status determined correctly above
                # Uses google_sheets_utils
                logger.info(f"{log_prefix} Updating sheet with final status '{current_sheet_status}'...")
                google_sheets_utils.update_export_status_for_store(
                    original_pid, store_val, current_sheet_status, cloned_gid, cloned_title, STATUS_SHEET_NAME
                )
            except Exception as processing_err: # Catch errors in main try block for product
                logger.error(f"{log_prefix} ‼️ UNEXPECTED ERROR: {processing_err}", exc_info=True)
                if not clone_ok: fail_clones += 1;
                else: fail_trans += 1;
                current_sheet_status = f"ERROR_EXCEPTION_{store_val.upper()}"
                try: google_sheets_utils.update_export_status_for_store(original_pid, store_val, current_sheet_status, cloned_gid, cloned_title, STATUS_SHEET_NAME)
                except Exception as log_err: logger.error(f"{log_prefix} Failed log EXCEPTION status: {log_err}")

            # --- Delay ---
            time.sleep(random.uniform(1.0, 2.5))

        logger.info(f"--- Finished Store: {store_val} ---")

    # --- Final Summary ---
    end_time = time.time(); duration = end_time - start_time; logger.info("="*40); logger.info("--- Weekly Script Complete ---"); logger.info(f" Duration: {duration:.2f}s"); logger.info(f" Attempts: {proc_count}"); logger.info(f" Clones OK: {ok_clones} | Fail: {fail_clones}"); logger.info(f" Translations OK: {ok_trans} | Fail: {fail_trans}"); logger.info("="*40);


# --- Script Execution Guard ---
if __name__ == "__main__":
    try: main()
    except Exception as main_err: logger.critical(f"💥 MAIN EXECUTION FAILED: {main_err}", exc_info=True); sys.exit(1);