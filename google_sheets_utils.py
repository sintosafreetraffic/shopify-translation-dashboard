# File: google_sheets_utils.py (Improved Version with add_new_product_rows)

import os
import gspread # Requires: pip install gspread
import logging
# Requires: pip install oauth2client
from oauth2client.service_account import ServiceAccountCredentials
import time
from threading import Lock
import requests # Requires: pip install requests
import json # Needed for header check in move_done
import random # Needed for jitter

# --- Type Hinting Imports ---
from typing import List, Dict, Any, Tuple, Optional, Union

# --- Setup logger ---
# Use standard logger name, format allows easy filtering
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration ---
# Load from environment variables, provide defaults where sensible
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID") # CRITICAL - Must be set in .env
SHEET1_NAME = os.getenv("STATUS_SHEET_NAME", "Sheet1") # Main processing sheet
SHEET2_NAME = os.getenv("ARCHIVE_SHEET_NAME", "Sheet2") # Archive sheet

MAX_RETRIES = 3     # Max retries for Google API calls
RETRY_DELAY = 2.0   # Initial delay in seconds for retries

# --- Column Mapping for Multi-Store Status Updates ---
# !!! IMPORTANT: Verify these column letters match your ACTUAL Sheet1 layout !!!
STORE_COLUMN_MAP = {
    # Example: If Spanish Status is Col D, GID is E, Title is F
    "store_es": {"status": "D", "gid": "E", "title": "F"},
    # Example: If Danish Status is Col G, GID is H, Title is I
    "store_dk": {"status": "G", "gid": "H", "title": "I"},
    # Add mappings for ALL your target stores here, matching Sheet1 columns
    # "store_fr": {"status": "J", "gid": "K", "title": "L"},
}

# --- Helper Functions ---
_gspread_client = None
_client_lock = Lock()

def _get_gspread_client() -> Optional[gspread.Client]:
    """Authenticates and returns an authorized gspread client (cached). Thread-safe."""
    global _gspread_client
    # Quick check without lock first
    if _gspread_client:
        return _gspread_client

    with _client_lock:
        # Double-check after acquiring lock
        if _gspread_client is None:
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds_path = GOOGLE_CREDENTIALS_FILE
            if not GOOGLE_SHEET_ID:
                 logger.critical("❌ CRITICAL: GOOGLE_SHEET_ID environment variable not set.")
                 return None # Cannot proceed without Sheet ID
            if not os.path.exists(creds_path):
                logger.critical(f"❌ Google Credentials file not found at: {creds_path}. Check GOOGLE_CREDENTIALS_FILE env var.")
                return None
            try:
                logger.debug(f"Attempting to authorize Google Sheets client using: {creds_path}")
                creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
                client = gspread.authorize(creds)
                logger.info(f"🔐 Google Sheets client authorized successfully using: {creds_path}")
                _gspread_client = client
            except Exception as e:
                logger.exception(f"❌ Failed to authorize Google Sheets client: {e}")
                _gspread_client = None # Ensure it stays None on failure
    return _gspread_client

def _get_worksheet(worksheet_name: str) -> Optional[gspread.Worksheet]:
    """Gets a specific worksheet object using the cached client."""
    client = _get_gspread_client()
    if not client:
        logger.error("❌ Cannot get worksheet, client not authorized.")
        return None
    # GOOGLE_SHEET_ID check happens in client auth now

    try:
        spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)
        sheet = spreadsheet.worksheet(worksheet_name)
        logger.debug(f"Accessed worksheet: '{worksheet_name}' in Sheet ID: {GOOGLE_SHEET_ID}")
        return sheet
    except gspread.WorksheetNotFound:
        logger.error(f"❌ Worksheet '{worksheet_name}' not found in Google Sheet ID {GOOGLE_SHEET_ID}.")
    except gspread.exceptions.APIError as e:
        # Log specific API errors (like permission denied, quota exceeded)
        response_text = getattr(e.response, 'text', str(e)) # Safely get response text
        status_code = getattr(e.response, 'status_code', 'N/A')
        logger.error(f"❌ API Error opening worksheet '{worksheet_name}' (SheetID: {GOOGLE_SHEET_ID}): Status {status_code}, Details: {response_text[:500]}...") # Limit error text length
    except Exception as e:
        logger.exception(f"❌ Failed to open worksheet '{worksheet_name}' (SheetID: {GOOGLE_SHEET_ID}): {e}")
    return None

def _retry_gspread_operation(operation: callable, *args, **kwargs) -> Any:
    """Wrapper to retry gspread operations with exponential backoff and jitter."""
    retries = 0
    last_exception = None
    while retries < MAX_RETRIES:
        try:
            # Attempt the operation (e.g., sheet.get_all_values(), sheet.append_rows())
            return operation(*args, **kwargs)
        except requests.exceptions.ConnectionError as conn_err:
            # Network-level errors
            last_exception = conn_err; retries += 1; error_type = "ConnectionError"
        except gspread.exceptions.APIError as api_err:
            # Errors specifically from the Google Sheets API
            last_exception = api_err; error_type = "APIError"
            # Check if error is retryable (Rate Limit 429, Server Errors 5xx)
            status_code = getattr(api_err.response, 'status_code', 0)
            if status_code == 429 or status_code >= 500:
                retries += 1 # Retry these errors
            else:
                # Do not retry client errors like 400, 401, 403, 404
                response_text = getattr(api_err.response, 'text', str(api_err))
                logger.error(f"❌ Non-retryable Google Sheets API Error during {operation.__name__}: Status {status_code}, Details: {response_text[:500]}...")
                raise # Re-raise the exception to stop the process
        except Exception as e:
             # Catch any other unexpected exceptions during the gspread call
             last_exception = e; error_type = "Unexpected Error"
             logger.error(f"❌ {error_type} during {operation.__name__}: {e}", exc_info=True)
             raise # Re-raise unexpected errors immediately

        # If a retry is needed and possible:
        if retries >= MAX_RETRIES:
            logger.error(f"🚫 Max retries ({MAX_RETRIES}) exceeded for {operation.__name__} after {error_type}: {last_exception}")
            raise last_exception # Re-raise the last captured exception

        # Calculate wait time with exponential backoff and jitter
        wait = RETRY_DELAY * (2 ** (retries - 1)) * (1 + random.random())
        wait = min(wait, 30.0) # Cap wait time
        status_code_info = f" (Status: {status_code})" if error_type == "APIError" else ""
        logger.warning(f"🔁 {error_type}{status_code_info} during {operation.__name__}. Retrying in {wait:.2f}s (Attempt {retries}/{MAX_RETRIES})...")
        time.sleep(wait)

    # Fallback raise if loop structure somehow allows exit without raising
    raise last_exception if last_exception else Exception(f"Max retries exceeded for {operation.__name__}")

# --- Public Utility Functions ---

def ensure_sheet_headers(sheet_name: str = SHEET1_NAME) -> Tuple[Optional[List[str]], bool]:
    """
    Checks Sheet1 headers and updates them if necessary based on STORE_COLUMN_MAP.
    Returns (expected_headers, success_flag).
    """
    logger.info(f"Checking/Ensuring headers for sheet '{sheet_name}'...")
    sheet = _get_worksheet(sheet_name)
    if not sheet: return None, False # Return None for headers if sheet fails

    # Define base headers + dynamically add store-specific headers
    # Ensure consistent order by sorting map keys
    expected_headers = ["Product ID", "Product Title", "Sales Count"] # Base columns A, B, C
    sorted_store_keys = sorted(STORE_COLUMN_MAP.keys())
    for store_key in sorted_store_keys:
        # Derive suffix (e.g., ES, DA) from store key like 'store_es'
        store_suffix = store_key.split('_')[-1].upper()
        expected_headers.extend([f"Status {store_suffix}", f"Cloned GID {store_suffix}", f"Cloned Title {store_suffix}"])

    logger.debug(f"Expected Headers: {expected_headers}")

    try:
        current_header = []
        # Use retry for the initial fetch operation
        header_values = _retry_gspread_operation(sheet.get_values, 'A1:Z1') # Fetch a wide range
        if header_values:
             current_header = header_values[0]
             # Trim empty trailing cells from what was read
             while current_header and not current_header[-1]: current_header.pop()

        logger.debug(f"Current Headers read: {current_header}")

        if current_header == expected_headers:
            logger.info(f"✅ Headers in '{sheet_name}' are correct.")
            return expected_headers, True # Return headers and success

        # Headers are missing or incorrect, attempt to update
        logger.warning(f"Headers mismatch or missing. Attempting update in '{sheet_name}'...")
        # Determine range to update based on expected headers length
        header_range = f"A1:{gspread.utils.rowcol_to_a1(1, len(expected_headers))}"
        logger.debug(f"Updating header range: {header_range}")

        # Clear extra header columns if current header is longer than expected
        if len(current_header) > len(expected_headers):
             try:
                 clear_range_start_col_letter = gspread.utils.rowcol_to_a1(1, len(expected_headers) + 1)[0]
                 clear_range = f"{clear_range_start_col_letter}1:Z1" # Clear rest of row 1 to Z
                 logger.debug(f"Clearing extra header cells in range: {clear_range}")
                 _retry_gspread_operation(sheet.batch_clear, [clear_range])
             except Exception as clear_err:
                  logger.warning(f"⚠️ Failed to clear extra header cells: {clear_err}. Continuing with update...")

        # Update first row with expected headers
        _retry_gspread_operation(sheet.update, header_range, [expected_headers], value_input_option="USER_ENTERED")
        logger.info(f"✅ Headers updated in '{sheet_name}'. Please verify formatting if needed.")
        return expected_headers, True # Return headers and success

    except Exception as e:
        logger.exception(f"❌ Unexpected error checking/updating headers for '{sheet_name}': {e}")
        return None, False # Return None for headers on error

# (Keep get_source_data if needed by import.py - code omitted for brevity unless requested)
# def get_source_data(...) -> List[Tuple[int, str, List[Any]]]: ...


def get_sheet_data_by_header(sheet_name: str = SHEET1_NAME) -> Tuple[Optional[List[str]], Optional[List[Dict[str, Any]]]]:
    """
    Gets all data from a sheet, returning header row and data rows as list of dicts.
    Returns (None, None) on error. Uses retry wrapper.
    """
    logger.info(f"Fetching all values from '{sheet_name}' to process...")
    sheet = _get_worksheet(sheet_name)
    if not sheet: return None, None

    try:
        # Retry the fetching of all values
        all_values = _retry_gspread_operation(sheet.get_all_values)
        if not all_values or len(all_values) < 1:
             logger.warning(f"Sheet '{sheet_name}' is empty or header not found.")
             return None, [] # Return None for header, empty list for data is valid

        header = all_values[0]
        data_rows = all_values[1:]

        # Convert rows to list of dictionaries, padding rows shorter than header
        list_of_dicts = []
        num_headers = len(header)
        for row in data_rows:
             # Efficiently create dict, handling potential short rows
             row_data = dict(zip(header, row))
             # Add missing keys if row was shorter (less common with get_all_values but safe)
             if len(row) < num_headers:
                 for i in range(len(row), num_headers):
                     row_data[header[i]] = "" # Default to empty string
             list_of_dicts.append(row_data)


        logger.info(f"Fetched header ({len(header)} columns) and {len(list_of_dicts)} data rows from '{sheet_name}'.")
        return header, list_of_dicts

    except Exception as e:
        # Error likely already logged by _retry_gspread_operation if it's API/connection
        logger.exception(f"❌ Failed to load/process data from '{sheet_name}' using get_all_values: {e}")
        return None, None

# --- NEW FUNCTION TO ADD ROWS ---
def add_new_product_rows(rows_to_add: List[List[Any]], sheet_name: str = SHEET1_NAME) -> bool:
    """
    Appends multiple rows of data to the specified sheet.

    Args:
        rows_to_add (List[List[Any]]): A list of lists, where each inner list
                                       represents a row and contains the cell values
                                       in the correct column order.
        sheet_name (str): The name of the target worksheet.

    Returns:
        bool: True if rows were appended successfully, False otherwise.
    """
    if not rows_to_add:
        logger.info(f"No new rows provided to add to '{sheet_name}'.")
        return True # Nothing to do is considered success

    logger.info(f"Attempting to append {len(rows_to_add)} new rows to sheet '{sheet_name}'...")
    sheet = _get_worksheet(sheet_name)
    if not sheet:
        logger.error(f"Cannot append rows, failed to get worksheet '{sheet_name}'.")
        return False

    try:
        # Use the append_rows method with retry logic
        _retry_gspread_operation(
            sheet.append_rows,
            values=rows_to_add,
            value_input_option="USER_ENTERED", # Interprets values (e.g., numbers)
            insert_data_option="INSERT_ROWS" # Appends after the last row with content
        )
        logger.info(f"✅ Successfully appended {len(rows_to_add)} rows to '{sheet_name}'.")
        return True
    except Exception as e:
        # Error likely logged by retry wrapper, add context here
        logger.exception(f"❌ Failed to append rows to '{sheet_name}': {e}")
        return False
# --- END NEW FUNCTION ---


def find_row_index_by_id(sheet: gspread.Worksheet, product_id: Union[str, int], id_column_index: int = 1) -> Optional[int]:
     """Finds the row index (1-based) for a given ID in a specific column using retry."""
     if not sheet or not product_id: return None
     try:
         # Find expects a string query
         cell = _retry_gspread_operation(sheet.find, str(product_id), in_column=id_column_index)
         if cell:
              logger.debug(f"Found product_id '{product_id}' in row {cell.row}")
              return cell.row
         else:
              logger.debug(f"Product_id '{product_id}' not found in column {id_column_index}.")
              return None
     except Exception as e:
         # Error likely logged by retry wrapper
         logger.error(f"Error finding row for ID {product_id} in col {id_column_index}: {e}")
         return None


def update_export_status_for_store(original_product_id: Union[str, int], target_store_value: str,
                                   new_status: str, cloned_gid: Optional[str], cloned_title: Optional[str],
                                   sheet_name: str = SHEET1_NAME) -> bool:
    """
    Updates Status, GID, and Title in the columns specific to the target_store_value.
    Uses batch update for efficiency after finding the row. Handles retries.
    """
    # Ensure product ID is a string for logging and lookup consistency
    original_product_id_str = str(original_product_id)

    if not original_product_id_str or not target_store_value:
        logger.warning("⚠️ update_export_status_for_store: Missing product_id or target_store_value.")
        return False

    # --- Determine target columns ---
    column_set = STORE_COLUMN_MAP.get(target_store_value)
    if not column_set:
        logger.error(f"❌ No column mapping found for target store '{target_store_value}' in STORE_COLUMN_MAP.")
        return False

    # Safely get column letters, default to None if key missing in map
    status_col = column_set.get('status')
    gid_col = column_set.get('gid')
    title_col = column_set.get('title')

    if not status_col or not gid_col or not title_col:
         logger.error(f"❌ Incomplete column mapping for target store '{target_store_value}' in STORE_COLUMN_MAP. Found: {column_set}")
         return False

    log_title_snip = str(cloned_title)[:50] + '...' if cloned_title else '(empty)'
    logger.info(f"Sheet Update Prep for Orig ID {original_product_id_str} / Store '{target_store_value}': "+
                f"Status='{new_status}'({status_col}), GID='{cloned_gid or ''}'({gid_col}), Title='{log_title_snip}'({title_col})")

    try:
        sheet = _get_worksheet(sheet_name)
        if not sheet: return False

        # Find row based on original Product ID (Column A = 1)
        logger.debug(f"Finding row for Product ID '{original_product_id_str}'...")
        row_index = find_row_index_by_id(sheet, original_product_id_str, id_column_index=1)

        if row_index:
            # Prepare data for batch update
            update_data = [
                {"range": f"{status_col}{row_index}", "values": [[str(new_status or '')]]},
                {"range": f"{gid_col}{row_index}",    "values": [[str(cloned_gid or '')]]},
                {"range": f"{title_col}{row_index}",  "values": [[str(cloned_title or '')]]}
            ]
            logger.debug(f"Found row {row_index}. Attempting batch update...")
            # Use retry wrapper for the batch update operation
            _retry_gspread_operation(sheet.batch_update, update_data, value_input_option="USER_ENTERED")
            logger.info(f"✅ Updated Sheet Row {row_index} for Store '{target_store_value}'.")
            return True
        else:
            # This warning means the product ID wasn't found in Column A
            # This case should be handled by the calling script (export_weekly.py)
            # by first adding missing rows if needed.
            logger.warning(f"⚠️ Could not find row for original product_id={original_product_id_str} in '{sheet_name}' Col A during update attempt.")
            return False # Indicate row wasn't found for update
    except Exception as e:
        # Error likely logged by retry wrapper
        logger.exception(f"❌ Error in update_export_status_for_store for ID {original_product_id_str} / Store '{target_store_value}': {e}")
        return False


def move_done_to_sheet2():
    """
    Moves completed rows (based on STORE_COLUMN_MAP statuses like DONE_*, TRANSLATED, APPROVED)
    from Sheet1 to Sheet2 and deletes them from Sheet1 using batch operations.
    """
    logger.info(f"Checking for completed rows to move from '{SHEET1_NAME}' to '{SHEET2_NAME}'...")
    sheet1 = _get_worksheet(SHEET1_NAME)
    sheet2 = _get_worksheet(SHEET2_NAME)
    if not sheet1 or not sheet2:
        logger.error(f"Could not access '{SHEET1_NAME}' or '{SHEET2_NAME}'. Aborting move.")
        return

    try:
        # Fetch header and data using the reliable helper
        header, all_data = get_sheet_data_by_header(SHEET1_NAME)
        if header is None or all_data is None:
            logger.error(f"Failed to fetch data from '{SHEET1_NAME}'. Aborting move.")
            return
        if not all_data:
            logger.info(f"📭 No data rows found in '{SHEET1_NAME}' to process for moving.")
            return

        # Dynamically determine which status columns to check based on the header AND the map
        actual_status_columns = []
        for store_key, cols in STORE_COLUMN_MAP.items():
             status_col_header = f"Status {store_key.split('_')[-1].upper()}"
             if 'status' in cols and status_col_header in header: # Check if map defined AND exists in sheet
                 actual_status_columns.append(status_col_header)
        # Optionally add base 'Status' column if it exists
        if "Status" in header and "Status" not in actual_status_columns:
             actual_status_columns.append("Status")

        if not actual_status_columns:
            logger.error(f"❌ Cannot find any expected Status columns based on STORE_COLUMN_MAP in header of '{SHEET1_NAME}'. Headers: {header}")
            return
        logger.debug(f"Status columns being checked for completion: {actual_status_columns}")

        # Define statuses that trigger a move
        statuses_to_move = {"APPROVED", "TRANSLATED"}
        # Dynamically add DONE_STORE_XYZ statuses based on map keys
        for store_key in STORE_COLUMN_MAP.keys():
            statuses_to_move.add(f"DONE_{store_key.upper()}") # e.g., DONE_STORE_ES
        logger.info(f"Statuses triggering move to Sheet2: {statuses_to_move}")

        rows_to_move_data = []
        rows_to_delete_requests = [] # Build requests for batchUpdate deleteDimension
        sheet1_gid = sheet1.id # Get the numeric GID of Sheet1

        # Iterate backwards through the indices to handle deletions correctly
        for idx in range(len(all_data) - 1, -1, -1):
            row_dict = all_data[idx]
            current_sheet_row_index = idx + 2 # Sheet index is 1-based, +1 for header

            # Check all relevant status columns for a "move" status
            should_move = False
            status_found = ""
            for status_col_name in actual_status_columns:
                status_val = str(row_dict.get(status_col_name, "")).strip().upper()
                if status_val in statuses_to_move:
                    should_move = True
                    status_found = status_val
                    break # Found a status in this row, no need to check others

            if should_move:
                logger.debug(f"Marking sheet row {current_sheet_row_index} for moving (Status: '{status_found}').")
                # Convert dict back to list in header order for appending
                row_values = [row_dict.get(h, "") for h in header]
                rows_to_move_data.append(row_values)
                # Add a delete request (API uses 0-based index)
                rows_to_delete_requests.append({
                    "deleteDimension": {
                        "range": {
                            "sheetId": sheet1_gid,
                            "dimension": "ROWS",
                            "startIndex": current_sheet_row_index - 1, # 0-based start index
                            "endIndex": current_sheet_row_index        # Exclusive end index
                        }
                    }
                })

        # --- Perform Sheet Updates (if any rows marked) ---
        if rows_to_move_data:
            # Append data to Sheet2 (reverse collected data back to original order for append)
            logger.info(f"Appending {len(rows_to_move_data)} rows to '{SHEET2_NAME}'...")
            _retry_gspread_operation(sheet2.append_rows, rows_to_move_data[::-1], value_input_option="USER_ENTERED", insert_data_option="INSERT_ROWS")

            # Batch delete rows from Sheet1 (API requires requests sorted descending by index)
            logger.info(f"Batch deleting {len(rows_to_delete_requests)} rows from '{SHEET1_NAME}'...")
            sorted_delete_requests = sorted(rows_to_delete_requests, key=lambda x: x['deleteDimension']['range']['startIndex'], reverse=True)
            delete_body = {'requests': sorted_delete_requests}
            _retry_gspread_operation(sheet1.batch_update, delete_body)

            logger.info(f"✅ Successfully moved and deleted {len(rows_to_move_data)} completed rows.")
        else:
            logger.info("📭 No completed rows found in Sheet1 to move.")

    except Exception as e:
        # Error logged by retry wrapper or here
        logger.exception(f"❌ Failed during move_done_to_sheet2 process: {e}")


# --- Add other Google Sheet utility functions as needed ---