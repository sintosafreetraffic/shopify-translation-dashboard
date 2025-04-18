# File: export_weekly.py

import os
import sys
import time
import json
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
import traceback

# --- Assumed Centralized Utility Modules (MUST BE CREATED/POPULATED) ---
try:
    import shopify_utils # Needs functions like: get_sold_product_details, fetch_product_by_id, clone_product
    import google_sheets_utils # Needs class/functions like: GoogleSheetManager, update_sheet_status
    import translation_utils # Needs function like: translate_cloned_product
    # import text_processing_utils # Needed by translation_utils likely
    # import variant_utils # Needed by translation_utils likely
except ImportError as e:
    print(f"❌ CRITICAL ERROR: Failed to import one or more required utility modules: {e}")
    print("   Please ensure these modules exist in the 'shopify_translation_dashboard' project")
    print("   and contain the necessary functions extracted from export_routes.py/app.py.")
    sys.exit(1)

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration Loading Function ---
def load_configuration():
    """Loads and validates required environment variables."""
    load_dotenv()
    config = {
        "SOURCE_STORE_URL": os.getenv("SHOPIFY_STORE_URL"), # URL of the store to check sales FROM
        "SOURCE_STORE_API_KEY": os.getenv("SHOPIFY_API_KEY"), # API Key for the source store
        "SHOPIFY_STORES_CONFIG": os.getenv("SHOPIFY_STORES_CONFIG"), # JSON string of target stores
        "GOOGLE_SHEET_ID": os.getenv("GOOGLE_SHEET_ID"),
        "GOOGLE_CREDENTIALS_FILE": os.getenv("GOOGLE_CREDENTIALS_FILE"),
        "STATUS_SHEET_NAME": os.getenv("STATUS_SHEET_NAME", "Sheet1"), # Sheet for tracking export status
        # Add other needed vars like STATUS_COLUMN if checking status before processing
        # Translation keys needed by translation_utils.translate_cloned_product
        "DEEPSEEK_API_KEY": os.getenv("DEEPSEEK_API_KEY"),
        "GOOGLE_TRANSLATE_API_KEY": os.getenv("GOOGLE_TRANSLATE_API_KEY"),
        # Add others like CHATGPT_API_KEY if needed
    }

    # Validate critical variables
    critical_vars = ["SOURCE_STORE_URL", "SOURCE_STORE_API_KEY", "SHOPIFY_STORES_CONFIG",
                     "GOOGLE_SHEET_ID", "GOOGLE_CREDENTIALS_FILE"]
    missing = [k for k, v in config.items() if k in critical_vars and not v]
    if missing:
        logger.critical(f"❌ CRITICAL ERROR: Missing environment variables: {', '.join(missing)}")
        return None

    # Parse the target stores config JSON
    try:
        config["TARGET_STORES"] = json.loads(config["SHOPIFY_STORES_CONFIG"])
        if not isinstance(config["TARGET_STORES"], list):
            raise ValueError("SHOPIFY_STORES_CONFIG is not a valid JSON list.")
        logger.info(f"Loaded config for {len(config['TARGET_STORES'])} target stores.")
    except Exception as e:
        logger.critical(f"❌ CRITICAL ERROR: Failed to parse SHOPIFY_STORES_CONFIG JSON: {e}")
        return None

    return config

# --- Main Export Logic ---
def main():
    logger.info("--- Starting Weekly Export Script ---")
    start_time = time.time()

    config = load_configuration()
    if not config:
        return # Exit if config loading failed

    # --- Initialize Google Sheets Manager ---
    try:
        # Assumes google_sheets_utils has a manager class or relevant functions
        sheet_manager = google_sheets_utils.GoogleSheetManager(
            config["GOOGLE_CREDENTIALS_FILE"], config["GOOGLE_SHEET_ID"]
        )
        logger.info("✅ Google Sheet Manager Initialized.")
    except Exception as e:
        logger.critical(f"❌ CRITICAL: Failed to initialize GoogleSheetManager: {e}", exc_info=True)
        return

    # --- 1. Define Time Range & Get Sold Products ---
    try:
        # Example: Get sales data for the last 7 days
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=7)
        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')
        min_sales = 1

        logger.info(f"Fetching products sold between {start_date_str} and {end_date_str} (Min sales: {min_sales}) from source store: {config['SOURCE_STORE_URL']}")

        # Assumes shopify_utils.get_sold_product_details exists and is adapted from export_routes.py
        sold_products = shopify_utils.get_sold_product_details(
            config["SOURCE_STORE_URL"],
            config["SOURCE_STORE_API_KEY"],
            start_date_str,
            end_date_str,
            min_sales
        )

        if not sold_products:
            logger.info("✅ No products met the sales criteria in the specified period. Exiting.")
            return

        logger.info(f"Found {len(sold_products)} products meeting sales criteria.")
        # Extract just the product IDs for processing
        product_ids_to_export = [str(p['product_id']) for p in sold_products if p.get('product_id')]
        if not product_ids_to_export:
             logger.info("✅ No valid product IDs found in sales data. Exiting.")
             return

    except Exception as e:
        logger.critical(f"❌ CRITICAL ERROR: Failed to get sold products: {e}", exc_info=True)
        return

    # --- 2. Process Each Target Store ---
    processed_count = 0
    success_clones = 0
    failed_clones = 0
    success_translations = 0
    failed_translations = 0

    target_stores = config["TARGET_STORES"] # Already parsed list of dicts

    for target_store_config in target_stores:
        target_store_value = target_store_config.get("value", "UNKNOWN_STORE")
        target_store_url = target_store_config.get("shopify_store_url")
        target_store_key = target_store_config.get("shopify_api_key")
        # Assumes language is defined per store in the config
        target_language = target_store_config.get("language", "en") # Default to english if not set

        if not target_store_url or not target_store_key:
            logger.error(f"Skipping target store '{target_store_value}': Missing URL or API key in SHOPIFY_STORES_CONFIG.")
            continue

        logger.info(f"--- Processing Target Store: {target_store_value} ---")

        for original_product_id in product_ids_to_export:
            processed_count += 1
            cloned_product_gid = None
            clone_success = False
            translate_success = None # None = not attempted, False = failed, True = succeeded

            # Unique identifier for logging/status update, combining product and target store
            log_prefix = f"[Product {original_product_id} -> Store {target_store_value}]"

            try:
                # Optional: Check Sheet status first to avoid re-processing?
                # status = google_sheets_utils.get_status(sheet_manager, config["STATUS_SHEET_NAME"], original_product_id, target_store_value)
                # if status == "DONE": continue

                logger.info(f"{log_prefix} Starting export & translate process...")
                # Update status to processing
                # google_sheets_utils.update_status(sheet_manager, config["STATUS_SHEET_NAME"], original_product_id, target_store_value, "PROCESSING")

                # --- 3. Fetch Full Source Product Data ---
                logger.info(f"{log_prefix} Fetching source product data...")
                source_product_data = shopify_utils.fetch_product_by_id(
                    original_product_id,
                    config["SOURCE_STORE_URL"],
                    config["SOURCE_STORE_API_KEY"]
                )
                if not source_product_data:
                    logger.error(f"{log_prefix} ❌ Failed to fetch source product data.")
                    # google_sheets_utils.update_status(sheet_manager, config["STATUS_SHEET_NAME"], original_product_id, target_store_value, "ERROR_FETCHING_SOURCE")
                    failed_clones += 1
                    continue # Skip to next product

                # --- 4. Clone Product to Target Store ---
                logger.info(f"{log_prefix} Cloning product...")
                # Assumes shopify_utils.clone_product exists, takes source data and target config,
                # and returns dict with 'cloned_product_gid', 'status', etc. or None on failure
                clone_result = shopify_utils.clone_product(
                    source_product_data,
                    target_store_config # Pass the whole dict for the target store
                )

                if clone_result and clone_result.get("cloned_product_gid"):
                    cloned_product_gid = clone_result["cloned_product_gid"]
                    clone_success = True
                    success_clones += 1
                    logger.info(f"{log_prefix} ✅ Clone successful. New GID: {cloned_product_gid}")
                    # google_sheets_utils.update_status(sheet_manager, config["STATUS_SHEET_NAME"], original_product_id, target_store_value, "CLONED")

                    # --- 5. Translate Cloned Product (if clone succeeded) ---
                    logger.info(f"{log_prefix} Translating cloned product {cloned_product_gid}...")
                    # Define fixed translation methods for the automated run
                    fixed_translation_methods = {
                        "title": "deepseek",
                        "description": "deepseek",
                        "variants": "google"
                    }
                    # Assumes translation_utils.translate_cloned_product exists.
                    # It needs the GID, target store config (URL/Key), target language, and methods.
                    # It should internally handle fetching by GID, translation, post-processing, and updating via GraphQL/REST.
                    translate_success = translation_utils.translate_cloned_product(
                        product_gid=cloned_product_gid,
                        target_store_url=target_store_url,
                        target_store_api_key=target_store_key,
                        target_language=target_language,
                        translation_methods=fixed_translation_methods,
                        source_language="auto" # Or get from config if needed
                        # Pass API keys if translate_cloned_product needs them directly
                        # deepseek_key=config["DEEPSEEK_API_KEY"],
                        # google_key=config["GOOGLE_TRANSLATE_API_KEY"]
                    )

                    if translate_success:
                        success_translations += 1
                        logger.info(f"{log_prefix} ✅ Translation successful.")
                        # google_sheets_utils.update_status(sheet_manager, config["STATUS_SHEET_NAME"], original_product_id, target_store_value, f"DONE_{target_store_value.upper()}")
                    else:
                        failed_translations += 1
                        logger.error(f"{log_prefix} ❌ Translation failed for GID {cloned_product_gid}.")
                        # google_sheets_utils.update_status(sheet_manager, config["STATUS_SHEET_NAME"], original_product_id, target_store_value, f"ERROR_TRANSLATING_{target_store_value.upper()}")

                else: # Clone failed
                    clone_success = False
                    failed_clones += 1
                    error_detail = clone_result.get("error", "Unknown error") if clone_result else "Clone function returned None"
                    logger.error(f"{log_prefix} ❌ Clone failed: {error_detail}")
                    # google_sheets_utils.update_status(sheet_manager, config["STATUS_SHEET_NAME"], original_product_id, target_store_value, f"ERROR_CLONING_{target_store_value.upper()}")

            except Exception as e:
                logger.error(f"{log_prefix} ‼️ UNEXPECTED ERROR during processing: {e}", exc_info=True)
                failed_clones += 1 # Count as clone failure if exception happens before/during clone
                # google_sheets_utils.update_status(sheet_manager, config["STATUS_SHEET_NAME"], original_product_id, target_store_value, f"ERROR_EXCEPTION_{target_store_value.upper()}")

            # Delay between products to be nice to APIs
            time.sleep(2.0) # Adjust as needed

        logger.info(f"--- Finished Processing Target Store: {target_store_value} ---")

    # --- Final Summary ---
    end_time = time.time(); duration = end_time - start_time
    logger.info("--- Weekly Export & Translate Script Complete ---")
    logger.info(f"      Duration: {duration:.2f} seconds ({duration/60:.2f} minutes)")
    logger.info(f"      Products Meeting Sales Criteria: {len(product_ids_to_export)}")
    logger.info(f"      Target Stores Processed: {len(target_stores)}")
    logger.info(f"      Total Product Export/Translate Attempts: {processed_count}")
    logger.info(f"      ✅ Successful Clones: {success_clones}")
    logger.info(f"      ✅ Successful Translations: {success_translations}")
    logger.info(f"      ❌ Failed Clones/Fetches: {failed_clones}")
    logger.info(f"      ❌ Failed Translations: {failed_translations}")
    logger.info("-------------------------------------------------")


# --- Script Execution ---
if __name__ == "__main__":
    main()