import os
import gspread
import logging
from oauth2client.service_account import ServiceAccountCredentials
import time
from threading import Lock
import pandas as pd # Keep for process_google_sheet

# Setup logger
logger = logging.getLogger("google_sheets")
# Ensure logger has a handler if running standalone for testing
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("google_sheets")

# --- Configuration ---
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
GOOGLE_SHEET_ID = "11PVJZkYeZfEtcuXZ7U4xiV1r_axgAIaSe88VgFF189E" # Consider making this an env var
SHEET1_NAME = "Sheet1"
SHEET2_NAME = "Sheet2"
MAX_RETRIES = 3 # Max retries for API calls
RETRY_DELAY = 2 # Base delay seconds for exponential backoff

# --- Helper Functions ---

# Cache the client to avoid re-authenticating constantly
_gspread_client = None
_client_lock = Lock()

def _get_gspread_client():
    """Authenticates and returns an authorized gspread client (cached)."""
    global _gspread_client
    with _client_lock:
        if _gspread_client is None:
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            try:
                # Try loading from env var path first
                creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
                _gspread_client = gspread.authorize(creds)
                logger.info(f"🔐 Google Sheets client authorized using: {GOOGLE_CREDENTIALS_FILE}")
            except FileNotFoundError:
                logger.error(f"❌ Google Credentials file not found at: {GOOGLE_CREDENTIALS_FILE}. Check GOOGLE_CREDENTIALS_FILE env var.")
                # Optional: Add fallback logic here if needed, like checking default paths
            except Exception as e:
                logger.exception(f"❌ Failed to authorize Google Sheets client: {e}")
                _gspread_client = None # Ensure it's None on failure
        return _gspread_client

def _get_worksheet(worksheet_name):
    """Gets a specific worksheet object using the cached client."""
    client = _get_gspread_client()
    if not client:
        return None
    try:
        sheet = client.open_by_key(GOOGLE_SHEET_ID).worksheet(worksheet_name)
        logger.debug(f"Accessed worksheet: '{worksheet_name}'")
        return sheet
    except gspread.WorksheetNotFound:
         logger.error(f"❌ Worksheet '{worksheet_name}' not found in Google Sheet ID {GOOGLE_SHEET_ID}.")
    except gspread.exceptions.APIError as e:
         logger.error(f"❌ API Error opening worksheet '{worksheet_name}': {e}")
    except Exception as e:
        logger.exception(f"❌ Failed to open worksheet '{worksheet_name}': {e}")
    return None

def _retry_gspread_operation(operation, *args, **kwargs):
    """ Wrapper to retry gspread operations on API errors AND ConnectionErrors. """
    retries = 0
    while retries < MAX_RETRIES: # Ensure MAX_RETRIES is defined
        try:
            return operation(*args, **kwargs)
        except requests.exceptions.ConnectionError as conn_err:
             # Catch connection errors specifically
             retries += 1
             if retries >= MAX_RETRIES:
                 logger.error(f"🚫 Max retries exceeded for {operation.__name__} after ConnectionError: {conn_err}")
                 raise # Re-raise after max retries
             wait = RETRY_DELAY * (2 ** (retries - 1))
             logger.warning(f"🔁 ConnectionError during {operation.__name__}. Retrying in {wait}s (Attempt {retries}/{MAX_RETRIES})")
             time.sleep(wait) # Ensure time is imported
        except gspread.exceptions.APIError as api_err:
            # Keep existing APIError handling (429, 5xx)
            if api_err.response.status_code == 429 or api_err.response.status_code >= 500:
                retries += 1
                if retries >= MAX_RETRIES:
                     logger.error(f"🚫 Max retries exceeded for {operation.__name__} after APIError: {api_err}")
                     raise
                wait = RETRY_DELAY * (2 ** (retries - 1))
                logger.warning(f"🔁 APIError ({api_err.response.status_code}) during {operation.__name__}. Retrying in {wait}s (Attempt {retries}/{MAX_RETRIES})")
                time.sleep(wait)
            else:
                logger.error(f"❌ Non-retryable Google Sheets API Error during {operation.__name__}: {api_err}")
                raise
        except Exception as e:
             # Catch other unexpected errors
             logger.error(f"❌ Unexpected error during {operation.__name__}: {e}")
             raise # Re-raise immediately

    # Should not be reached if MAX_RETRIES > 0
    logger.error(f"🚫 Unexpected exit from retry loop for {operation.__name__}.")
    raise Exception(f"Max retries exceeded for {operation.__name__} without specific error.")

def process_google_sheet(file, image_column="A", starting_row=2):
    """Reads an uploaded Excel/CSV and performs placeholder processing."""
    logger.info(f"Processing uploaded file: {file.filename}")
    try:
        # Read the uploaded file into a DataFrame
        if file.filename.endswith((".xlsx", ".xls")):
             df = pd.read_excel(file)
        elif file.filename.endswith(".csv"):
             df = pd.read_csv(file)
        else:
             logger.error("Unsupported file type for processing.")
             return 0

        # Example: Count the number of non-empty rows starting from `starting_row`
        df = df.iloc[starting_row - 1:]  # Adjust for 0-index
        product_count = df.shape[0]
        logger.info(f"Found {product_count} products in uploaded file starting from row {starting_row}.")

        # --- Process the sheet logic here (placeholder) ---
        # For example, extract titles, descriptions, translate, etc.
        # Add your specific processing steps here based on the DataFrame 'df'
        # --- End Placeholder ---

        return product_count
    except Exception as e:
        logger.exception(f"❌ Failed to process uploaded sheet: {e}")
        return 0

def get_pending_products_from_sheet():
    """
    Gets products that have the status 'PENDING' from Sheet1.
    Returns a list of dicts containing all columns for PENDING rows, or None on error.
    """
    logger.info(f"Fetching PENDING products from '{SHEET1_NAME}'...")
    sheet = _get_worksheet(SHEET1_NAME)
    if not sheet:
        return None # Indicate failure to get sheet

    try:
        # Using get_all_records is simple if sheet isn't huge
        all_records = _retry_gspread_operation(sheet.get_all_records)
        pending_products = [
            row for row in all_records
            if str(row.get("Status", "")).strip().upper() == "PENDING"
            # Add any other necessary conditions, e.g., ensuring 'Product ID' exists
            and row.get("Product ID")
        ]
        logger.info(f"📋 Found {len(pending_products)} PENDING products in '{SHEET1_NAME}'.")
        return pending_products
    except Exception as e:
        logger.exception(f"❌ Failed to load PENDING products from '{SHEET1_NAME}'.")
        return None # Indicate failure

def update_product_status_in_sheet(product_id, new_status, sheet=None):
    """
    Updates the 'Status' (Column D=4) for a given Product ID (Column A=1) in Sheet1.
    Uses sheet.find() for efficiency. Includes retry logic via helper.
    Returns True on success, False on failure.
    """
    if not product_id:
        logger.warning("⚠️ Attempted to update status with empty product_id.")
        return False

    logger.info(f"Attempting to update status for Product ID {product_id} to '{new_status}' in '{SHEET1_NAME}'.")
    try:
        if sheet is None:
            sheet = _get_worksheet(SHEET1_NAME)
            if not sheet: return False

        # Find the cell containing the product_id in the first column
        cell = _retry_gspread_operation(sheet.find, str(product_id), in_column=1)

        if cell:
            row_index = cell.row
            status_col_index = 4 # Assuming Status is Column D
            logger.debug(f"Found Product ID {product_id} at row {row_index}. Updating status column {status_col_index}.")
            # Use retry wrapper for the update operation
            _retry_gspread_operation(sheet.update_cell, row_index, status_col_index, str(new_status))
            logger.info(f"✅ Set Product ID {product_id} status -> '{new_status}' in '{SHEET1_NAME}'.")
            return True
        else:
            logger.warning(f"⚠️ Could not find Product ID {product_id} in '{SHEET1_NAME}' to update status.")
            return False

    except Exception as e:
        # Catch potential exceptions from _retry_operation or find
        logger.exception(f"❌ Error in update_product_status_in_sheet for Product ID {product_id}: {e}")
        return False

def get_products_pending_translation_from_sheet1(sheet=None):
    """
    Gets products that have the status 'PENDING' and a 'Cloned Product GID' from Sheet1.
    Returns list of dicts [{'Product ID': ..., 'Cloned Product GID': ...}], or None on error.
    """
    logger.info(f"Fetching products PENDING translation from '{SHEET1_NAME}'...")
    try:
        if sheet is None:
            sheet = _get_worksheet(SHEET1_NAME)
            if not sheet: return None

        # Using get_all_records is simple if the sheet isn't huge
        all_records = _retry_gspread_operation(sheet.get_all_records)

        pending_translation_products = []
        for row in all_records:
            status = str(row.get("Status", "")).strip().upper()
            gid = row.get("Cloned Product GID", "").strip()
            pid = row.get("Product ID") # Need original ID for status updates

            # Check if status is PENDING and GID exists
            if status == "PENDING" and gid and pid:
                pending_translation_products.append({
                    "Product ID": pid, # Keep original ID for reference/updates
                    "Cloned Product GID": gid # GID needed for API calls
                })

        logger.info(f"📋 Found {len(pending_translation_products)} products PENDING translation with GID in '{SHEET1_NAME}'.")
        return pending_translation_products

    except Exception as e:
        logger.exception(f"❌ Failed to load products PENDING translation from '{SHEET1_NAME}'.")
        return None

def mark_product_translation_done_in_sheet(original_product_id, sheet=None):
    """
    Marks a product's translation status as 'TRANSLATED' in Sheet1
    using the original 'Product ID' (Column A) to find the row. Includes retry logic.
    """
    new_status = "TRANSLATED" # Status indicating successful translation step
    if not original_product_id:
        logger.warning("⚠️ Attempted to mark translation done with empty original_product_id.")
        return False

    logger.info(f"Attempting to mark Original ID {original_product_id} as '{new_status}' in '{SHEET1_NAME}'.")
    try:
        if sheet is None:
            sheet = _get_worksheet(SHEET1_NAME)
            if not sheet: return False

        # Find the cell containing the original product_id in the first column (A=1)
        cell = _retry_gspread_operation(sheet.find, str(original_product_id), in_column=1)

        if cell:
            row_index = cell.row
            status_col_index = 4 # Assuming Status is Column D
            logger.debug(f"Found Original ID {original_product_id} at row {row_index}. Updating status column {status_col_index} to '{new_status}'.")
            # Use retry wrapper for the update operation
            _retry_gspread_operation(sheet.update_cell, row_index, status_col_index, new_status)
            logger.info(f"✅ Updated status to '{new_status}' for Original ID {original_product_id}")
            return True
        else:
            # This log is important - indicates data mismatch between processing and sheet state
            logger.warning(f"⚠️ Could not find product Original ID {original_product_id} in '{SHEET1_NAME}' to mark translation done.")
            return False

    except Exception as e:
        logger.exception(f"❌ Error marking translation done for product Original ID {original_product_id}: {e}")
        return False

def export_sales_to_sheet(product_sales):
    """
    Adds new products from sales data to Sheet1 if not already present or DONE.
    Updates sales counts for existing entries. Ensures headers. Includes retry logic.
    Returns the sheet URL on success, empty string on failure.
    """
    if not product_sales:
        logger.info("No product sales data provided to export_sales_to_sheet.")
        # Return sheet URL even if no data added, as sheet should exist
        return f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}/edit#gid=0" # Link to Sheet1

    logger.info(f"Exporting {len(product_sales)} products with sales data to Google Sheet...")
    client = _get_gspread_client()
    # Client is obtained internally by _get_worksheet
    sheet1 = _get_worksheet(SHEET1_NAME) # <-- Corrected Call
    sheet2 = _get_worksheet(SHEET2_NAME) # <-- Corrected Call
    if not sheet1 or not sheet2:
        logger.error("Could not access Sheet1 or Sheet2. Aborting move.")
        return

    try:
        # --- Ensure Headers ---
        # Define expected headers including the new column
        headers = ["Product ID", "Product Title", "Sales Count", "Status", "Cloned Product GID", "Cloned Product Title"]
        try:
            sheet1_header = _retry_gspread_operation(sheet1.row_values, 1)
        except gspread.exceptions.APIError as e: # Catch error if sheet is totally empty
             if "exceeds grid limits" in str(e): sheet1_header = []
             else: raise
        if sheet1_header != headers:
            logger.warning(f"Updating Sheet1 header.")
            # More robust header setting: clear only if needed, then update row 1
            if sheet1_header: _retry_gspread_operation(sheet1.delete_rows, 1)
            _retry_gspread_operation(sheet1.update, 'A1', [headers]) # Use update for header row

        try:
            sheet2_header = _retry_gspread_operation(sheet2.row_values, 1)
        except gspread.exceptions.APIError as e: # Catch error if sheet is totally empty
             if "exceeds grid limits" in str(e): sheet2_header = []
             else: raise
        if sheet2_header != headers:
            logger.warning(f"Updating Sheet2 header.")
            if sheet2_header: _retry_gspread_operation(sheet2.delete_rows, 1)
            _retry_gspread_operation(sheet2.update, 'A1', [headers])
        # --- End Header Check ---

        # --- Get Existing Data Efficiently ---
        logger.info("Fetching existing data from sheets...")
        # Fetch only Product ID and Status columns if possible? gspread might not support this easily.
        # Sticking to get_all_records for simplicity for now.
        existing_sheet1_data = _retry_gspread_operation(sheet1.get_all_records)
        existing_sheet2_data = _retry_gspread_operation(sheet2.get_all_records)
        logger.info(f"Fetched {len(existing_sheet1_data)} records from {SHEET1_NAME}, {len(existing_sheet2_data)} from {SHEET2_NAME}.")

        # Create lookups (using string IDs)
        sheet1_info = {str(row.get("Product ID","")): {"row_index": idx + 2, "status": str(row.get("Status","")).strip().upper()}
                       for idx, row in enumerate(existing_sheet1_data) if row.get("Product ID")}
        sheet2_ids = {str(row.get("Product ID","")) for row in existing_sheet2_data if row.get("Product ID")}
        logger.debug(f"Created lookups: {len(sheet1_info)} Sheet1 IDs, {len(sheet2_ids)} Sheet2 IDs.")

        # --- Process Input Sales Data ---
        new_rows_to_append = []
        sales_updates_batch = []

        for item in product_sales:
            pid_str = str(item.get("product_id","")).strip()
            if not pid_str: continue

            title = item.get("title", "")
            count = item.get("sales_count")

            if pid_str in sheet2_ids:
                logger.debug(f"Skipping {pid_str}: Already present in '{SHEET2_NAME}'.")
                continue

            if pid_str in sheet1_info:
                info = sheet1_info[pid_str]
                if info["status"] in ["DONE", "APPROVED"]:
                     logger.info(f"Skipping {pid_str}: Found in '{SHEET1_NAME}' with status '{info['status']}', will be moved later.")
                     continue
                else:
                     # Update sales count (Column C = 3)
                     try:
                          # Fetch current value before deciding to update
                          current_cell_value = _retry_gspread_operation(sheet1.cell, info["row_index"], 3).value
                          current_sales_count = int(current_cell_value) if current_cell_value else 0
                     except (ValueError, TypeError): current_sales_count = 0
                     except Exception as cell_err: logger.error(f"Error reading sales count for {pid_str}: {cell_err}"); current_sales_count = -1

                     if count is not None and count != current_sales_count:
                          sales_updates_batch.append({ "range": f"C{info['row_index']}", "values": [[count]] })
                          logger.debug(f"Queueing sales count update for {pid_str}: {current_sales_count} -> {count}")
            else:
                # New product for Sheet1
                # Ensure correct number of columns match header: ID, Title, Sales, Status, GID, Cloned Title
                new_rows_to_append.append([pid_str, title, count, "PENDING", "", ""])
                logger.debug(f"Queueing new row for {pid_str}.")

        # --- Perform Sheet Updates ---
        if new_rows_to_append:
            logger.info(f"Appending {len(new_rows_to_append)} new rows to '{SHEET1_NAME}'...")
            _retry_gspread_operation(sheet1.append_rows, new_rows_to_append, value_input_option="USER_ENTERED", insert_data_option="INSERT_ROWS")
            logger.info(f"✅ Successfully appended {len(new_rows_to_append)} rows.")

        if sales_updates_batch:
            logger.info(f"Batch updating sales counts for {len(sales_updates_batch)} rows in '{SHEET1_NAME}'...")
            _retry_gspread_operation(sheet1.batch_update, sales_updates_batch, value_input_option="USER_ENTERED")
            logger.info(f"✅ Successfully batch updated {len(sales_updates_batch)} sales counts.")

        sheet_url = f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}/edit#gid=0" # Link to first sheet
        logger.info(f"Sales export process finished. Sheet URL: {sheet_url}")
        return sheet_url

    except Exception as e:
        logger.exception("❌ Failed during export_sales_to_sheet")
        return "" # Return empty string on error


def move_done_to_sheet2():
    """
    Moves rows with status 'DONE' or 'APPROVED' from Sheet1 to Sheet2
    and DELETES them from Sheet1 using batch deletion. Includes retry logic.
    """
    logger.info(f"Checking for DONE/APPROVED rows to move from '{SHEET1_NAME}' to '{SHEET2_NAME}'...")
    client = _get_gspread_client()
    sheet1 = _get_worksheet(client, SHEET1_NAME)
    sheet2 = _get_worksheet(client, SHEET2_NAME)
    if not sheet1 or not sheet2:
        logger.error("Could not access Sheet1 or Sheet2. Aborting move.")
        return

    try:
        # Get all data including formulas/values as needed
        all_rows_sheet1 = _retry_gspread_operation(sheet1.get_all_values)
        if len(all_rows_sheet1) < 2: # Only header or empty
            logger.info("📭 No data rows found in Sheet1 to process.")
            return

        header = all_rows_sheet1[0]
        rows_to_process = all_rows_sheet1[1:]

        rows_to_move_data = []
        rows_to_delete_indices = [] # Store indices in descending order

        status_col_index = -1
        try:
             status_col_index = header.index("Status") # Find status column (0-based index)
        except ValueError:
             logger.error(f"❌ 'Status' column not found in header of '{SHEET1_NAME}'. Cannot move rows.")
             return

        # Iterate backwards to collect indices for deletion correctly
        for idx in range(len(rows_to_process) - 1, -1, -1):
            row_data = rows_to_process[idx]
            current_row_index = idx + 2 # Sheet index is 1-based, +1 for header

            # Check status column safely
            if len(row_data) > status_col_index:
                 status = row_data[status_col_index].strip().upper()
                 if status in ["DONE", "APPROVED"]:
                     logger.debug(f"Found row {current_row_index} to move (Status: {status}).")
                     rows_to_move_data.append(row_data) # Add data
                     rows_to_delete_indices.append(current_row_index) # Add index

        # --- Perform Sheet Updates ---
        if rows_to_move_data:
            # Append data to Sheet2 (reverse collected data back to original order for appending)
            logger.info(f"Moving {len(rows_to_move_data)} rows to '{SHEET2_NAME}'...")
            _retry_gspread_operation(sheet2.append_rows, rows_to_move_data[::-1], value_input_option="USER_ENTERED", insert_data_option="INSERT_ROWS")

            # Delete rows from Sheet1 (delete in descending index order)
            logger.info(f"Deleting {len(rows_to_delete_indices)} rows from '{SHEET1_NAME}'...")
            # Use batch delete for efficiency if gspread supports it well, otherwise loop
            # gspread doesn't have a direct batch delete by index list, so loop is safer
            for row_index in sorted(rows_to_delete_indices, reverse=True):
                 try:
                      _retry_gspread_operation(sheet1.delete_rows, row_index)
                      logger.debug(f"Deleted row {row_index} from {SHEET1_NAME}.")
                 except Exception as del_err:
                      logger.error(f"Error deleting row {row_index} from {SHEET1_NAME}: {del_err}")
                      # Decide if you want to stop or continue on deletion error

            logger.info(f"✅ Successfully moved {len(rows_to_move_data)} rows.")
        else:
            logger.info("📭 No DONE or APPROVED rows found in Sheet1 to move.")

    except Exception as e:
        logger.exception("❌ Failed to move DONE/APPROVED rows to Sheet2.")