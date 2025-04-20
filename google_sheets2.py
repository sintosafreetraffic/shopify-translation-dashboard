# File: google_sheet_helpers.py
# Version for MOVING specific data (Original URL, New URL) to IMPORTED sheet

import os
import traceback
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import time # Added for test block
from dotenv import load_dotenv # Added for test block


class GoogleSheetManager:
    """
    Manages interactions with a specific Google Sheet using the Google Sheets API v4.
    Handles initialization, reading data, appending rows, and deleting rows.
    """
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets'] # Read/Write access

    def __init__(self, credentials_path, spreadsheet_id):
        # ... (Initialization remains the same) ...
        if not os.path.exists(credentials_path):
            raise FileNotFoundError(f"Google credentials file not found at: {credentials_path}")
        self.spreadsheet_id = spreadsheet_id
        self.service = self._initialize_service(credentials_path)
        self._sheet_ids_cache = {} # Cache for numeric sheet IDs

    def _initialize_service(self, credentials_path):
        # ... (Remains the same) ...
        try:
            creds = service_account.Credentials.from_service_account_file(
                credentials_path, scopes=self.SCOPES)
            service = build('sheets', 'v4', credentials=creds, cache_discovery=False)
            print("Google Sheets service initialized successfully.")
            return service
        except Exception as e:
            print(f"Error initializing Google Sheets service: {e}")
            traceback.print_exc()
            raise

    def get_sheet_id_by_name(self, sheet_name, use_cache=True):
        # ... (Remains the same) ...
        if use_cache and sheet_name in self._sheet_ids_cache: return self._sheet_ids_cache[sheet_name]
        if not self.service: print("Error: Google Sheets service not initialized."); return None
        try:
            # print(f"Fetching numeric sheet ID for '{sheet_name}'...") # Keep logging minimal
            sheet_metadata = self.service.spreadsheets().get(spreadsheetId=self.spreadsheet_id, fields='sheets(properties(sheetId,title))').execute()
            sheets = sheet_metadata.get('sheets', []);
            for sheet in sheets:
                properties = sheet.get('properties', {}); title = properties.get('title'); sheet_id = properties.get('sheetId')
                if title == sheet_name:
                    if use_cache: self._sheet_ids_cache[sheet_name] = sheet_id
                    # print(f"Found numeric sheet ID for '{sheet_name}': {sheet_id}");
                    return sheet_id
            print(f"Error: Sheet named '{sheet_name}' not found."); return None
        except Exception as e: print(f"Error getting sheet ID for '{sheet_name}': {e}"); traceback.print_exc(); return None

    def get_source_data(self, sheet_name, data_range, url_column_index=0):
        """
        Fetches all row data, URL, and row numbers from the specified sheet range.
        NOTE: Even if range is B2:B, full_row_data will be a list like ['url'].
        """
        # ... (Remains largely the same, ensure start_row calculation is robust) ...
        if not self.service: print("Error: Google Sheets service not initialized."); return []
        source_data = []; full_range = f"{sheet_name}!{data_range}"
        try:
            print(f"Reading data from sheet range: {full_range}")
            result = self.service.spreadsheets().values().get( spreadsheetId=self.spreadsheet_id, range=full_range, valueRenderOption='UNFORMATTED_VALUE', dateTimeRenderOption='SERIAL_NUMBER' ).execute()
            values = result.get('values', [])
            # Calculate starting row index from the range string (e.g., B2 -> 2)
            range_part = data_range.split('!')[0] if '!' in data_range else data_range
            start_row_match = "".join(filter(str.isdigit, range_part))
            start_row_index = int(start_row_match) if start_row_match else 2 # Default to 2 if format is weird

            print(f"Found {len(values)} rows in range to check.")
            valid_rows_found = 0
            for i, row in enumerate(values):
                # Check if row has enough columns FOR THE URL INDEX and url is not empty
                if not row or len(row) <= url_column_index or not str(row[url_column_index]).strip():
                    continue # Skip rows without a URL in the target column

                url = str(row[url_column_index]).strip()
                current_row_num = start_row_index + i
                source_data.append((current_row_num, url, row)) # row here might just be ['url'] if range is B2:B
                valid_rows_found += 1

            print(f"Found {valid_rows_found} valid rows with URLs to process.")
            return source_data
        except Exception as e: print(f"Error reading from Google Sheet range '{full_range}': {e}"); traceback.print_exc(); return []

    def append_row(self, row_data, sheet_name):
        """
        Appends a row of data to the specified sheet, after the last row with content.
        (Method added back)
        """
        if not self.service: print("Error: Google Sheets service not initialized."); return False
        try:
            range_to_append = sheet_name # Append to the sheet, API finds the end
            value_input_option = 'USER_ENTERED'
            insert_data_option = 'INSERT_ROWS'
            body = { 'values': [row_data] } # Assumes row_data is already a list
            request = self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id, range=range_to_append,
                valueInputOption=value_input_option, insertDataOption=insert_data_option, body=body)
            response = request.execute()
            print(f"   Successfully appended row to '{sheet_name}'.")
            return True
        except Exception as e: print(f"   Error appending row to sheet '{sheet_name}': {e}"); traceback.print_exc(); return False

    def delete_row(self, row_num, sheet_numeric_id):
        """
        Deletes a specific row from a sheet using its numeric ID and row number.
        (Method added back)
        """
        if not self.service: print("Error: Google Sheets service not initialized."); return False
        if sheet_numeric_id is None: print("Error: Cannot delete row without numeric sheet ID."); return False
        try:
            start_index = row_num - 1; end_index = row_num # 0-based index for API
            body = { "requests": [ { "deleteDimension": { "range": { "sheetId": sheet_numeric_id, "dimension": "ROWS", "startIndex": start_index, "endIndex": end_index } } } ] }
            request = self.service.spreadsheets().batchUpdate(spreadsheetId=self.spreadsheet_id, body=body)
            response = request.execute()
            print(f"   Successfully deleted row {row_num} from source sheet (Numeric ID: {sheet_numeric_id}).")
            return True
        except Exception as e: print(f"   Error deleting row {row_num} from sheet (Numeric ID: {sheet_numeric_id}): {e}"); traceback.print_exc(); return False

    # --- update_cell method is REMOVED ---

# --- Example Usage ---
if __name__ == '__main__':
     # (Keep or update the test block as needed for append/delete)
     print("Testing Google Sheet Helpers Module (Append/Delete)...")
     # ... (Add back relevant test logic if desired, using caution) ...