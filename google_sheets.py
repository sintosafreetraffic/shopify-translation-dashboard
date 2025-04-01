import os
import gspread
import logging
from oauth2client.service_account import ServiceAccountCredentials
import time

# Setup logger
logger = logging.getLogger("google_sheets")
logger.setLevel(logging.INFO)

GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
GOOGLE_SHEET_ID = "11PVJZkYeZfEtcuXZ7U4xiV1r_axgAIaSe88VgFF189E"

import time  # optional for retry delay


def get_pending_products_from_sheet():
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials

    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)

        sheet = client.open_by_key(GOOGLE_SHEET_ID).worksheet("Sheet1")
        rows = sheet.get_all_records()

        pending_products = []
        for row in rows:
            if str(row.get("Status", "")).strip().upper() == "PENDING":
                pending_products.append({
                    "product_id": row.get("Product ID"),
                    "title": row.get("Product Title"),
                    "sales_count": row.get("Sales Count", 1),
                    "cloned_gid": row.get("Cloned Product GID")
                })

        logger.info(f"📋 Loaded {len(pending_products)} PENDING products from Sheet1")
        return pending_products

    except Exception as e:
        logger.warning("⚠️ Could not load Google Sheets to check duplicates. Proceeding without that filter.")
        return []

MAX_RETRIES = 5
RETRY_DELAY = 2  # seconds base for backoff

def update_product_status_in_sheet(product_id, new_status, sheet=None):
    retries = 0

    while retries < MAX_RETRIES:
        try:
            if sheet is None:
                scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
                creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
                client = gspread.authorize(creds)
                sheet = client.open_by_key(GOOGLE_SHEET_ID).worksheet("Sheet1")

            all_values = sheet.get_all_values()
            if not all_values:
                return False

            rows = all_values[1:]

            for idx, row_data in enumerate(rows, start=2):
                if len(row_data) < 1:
                    continue
                sheet_pid = row_data[0]
                if str(sheet_pid) == str(product_id):
                    sheet.update_cell(idx, 4, new_status)
                    logger.info(f"✅ Set product_id={product_id} status -> {new_status}")
                    return True

            logger.warning(f"⚠️ Could not find product_id={product_id} in Sheet1.")
            return False

        except Exception as e:
            if "429" in str(e):
                retries += 1
                wait = RETRY_DELAY * retries
                logger.warning(f"🔁 Rate limit hit. Retrying in {wait}s (Attempt {retries}/{MAX_RETRIES})")
                time.sleep(wait)
            else:
                logger.exception("❌ Error in update_product_status_in_sheet")
                return False

    logger.error("🚫 Max retries exceeded for update_product_status_in_sheet")
    return False

def get_products_pending_translation_from_sheet1(sheet):
    print("🧪 Called version with sheet param")  # Add this to verify!
    """
    Gets products that have the status 'PENDING' from the provided Sheet1.
    Returns a list of dicts with 'original_pid' and 'cloned_gid'.
    """
    try:
        rows = sheet.get_all_records()

        pending_translation_products = []
        for row in rows:
            if str(row.get("Status", "")).strip().upper() == "PENDING":
                pending_translation_products.append({
                    "original_pid": row.get("Product ID"),
                    "cloned_gid": row.get("Cloned Product GID")
                })

        logger.info(f"📋 Loaded {len(pending_translation_products)} products pending translation.")
        return pending_translation_products

    except Exception as e:
        logger.exception("❌ Failed to load products pending translation.")
        return []

def mark_product_translation_done_in_sheet(product_gid):
    """
    Marks a product's translation status as 'TRANSLATION_DONE' in Sheet1.
    Uses the 'Cloned Product GID' to find the correct row.
    """
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)

        sheet1 = client.open_by_key(GOOGLE_SHEET_ID).worksheet("Sheet1")

        all_values = sheet1.get_all_values()
        header = all_values[0]
        rows = all_values[1:]

        # Assume headers: ["Product ID", "Product Title", "Sales Count", "Status", "Cloned Product GID"]
        gid_col_index = header.index("Cloned Product GID") if "Cloned Product GID" in header else -1
        status_col_index = header.index("Status") if "Status" in header else -1

        if gid_col_index == -1 or status_col_index == -1:
            logger.error("⚠️ Required columns not found in Sheet1.")
            return False

        for idx, row in enumerate(rows, start=2):
            if len(row) > gid_col_index and str(row[gid_col_index]) == str(product_gid):
                sheet1.update_cell(idx, status_col_index + 1, "TRANSLATION_DONE")
                logger.info(f"✅ Updated translation status to TRANSLATION_DONE for GID {product_gid}")
                return True

        logger.warning(f"⚠️ Could not find product GID {product_gid} in Sheet1.")
        return False

    except Exception as e:
        logger.exception(f"❌ Error marking translation done for product GID {product_gid}.")
        return False

def export_sales_to_sheet(product_sales):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)

        sheet = client.open_by_key(GOOGLE_SHEET_ID)
        sheet1 = sheet.worksheet("Sheet1")
        sheet2 = sheet.worksheet("Sheet2")

        # Ensure headers
        headers = ["Product ID", "Product Title", "Sales Count", "Status", "Cloned Product GID"]
        if sheet1.row_values(1) != headers:
            sheet1.delete_rows(1)
            sheet1.insert_row(headers, 1)
        if sheet2.row_values(1) != headers:
            sheet2.delete_rows(1)
            sheet2.insert_row(headers, 1)

        existing_sheet1 = sheet1.get_all_records()
        existing_sheet2 = sheet2.get_all_records()

        sheet1_id_to_row = {str(row["Product ID"]): idx + 2 for idx, row in enumerate(existing_sheet1)}
        sheet2_ids = {str(row["Product ID"]) for row in existing_sheet2}

        new_rows = []
        batch_updates = []

        for item in product_sales:
            pid = str(item.get("product_id"))
            title = item.get("title")
            count = item.get("sales_count")

            if pid in sheet2_ids:
                continue

            if pid in sheet1_id_to_row:
                row_idx = sheet1_id_to_row[pid]
                current_row = existing_sheet1[row_idx - 2]
                if current_row.get("Status", "").strip().upper() in ["DONE", "APPROVED"]:
                    sheet2.append_row([
                        current_row.get("Product ID"),
                        current_row.get("Product Title"),
                        current_row.get("Sales Count"),
                        "DONE",
                        current_row.get("Cloned Product GID", "")
                    ])
                    sheet1.delete_rows(row_idx)
                    continue
                else:
                    batch_updates.append((row_idx, 3, count))
                continue

            # New rows should explicitly have empty cloned_gid initially
            new_rows.append([pid, title, count, "PENDING", ""])

        if new_rows:
            sheet1.append_rows(new_rows, value_input_option="USER_ENTERED")
            logger.info(f"➕ Added {len(new_rows)} new rows to Sheet1")

        if batch_updates:
            data = [{"range": f"C{row}", "values": [[value]]} for row, _, value in batch_updates]
            sheet1.batch_update([{"range": d["range"], "values": d["values"]} for d in data])
            logger.info(f"🧠 Batch updated {len(batch_updates)} sales counts")

        return f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}/edit"

    except Exception as e:
        logger.exception("❌ Failed to export to Google Sheets")
        return ""

    
def move_done_to_sheet2():
    """
    Moves all rows from Sheet1 that have status 'DONE' to Sheet2 and removes them from Sheet1.
    """
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)

        sheet = client.open_by_key(GOOGLE_SHEET_ID)
        sheet1 = sheet.worksheet("Sheet1")
        sheet2 = sheet.worksheet("Sheet2")

        all_rows = sheet1.get_all_values()
        header, rows = all_rows[0], all_rows[1:]

        keep_rows = [header]
        done_rows = []

        for row in rows:
            if len(row) >= 4 and row[3].strip().upper() == "DONE":
                done_rows.append(row)
            else:
                keep_rows.append(row)

        if done_rows:
            sheet2.append_rows(done_rows, value_input_option="USER_ENTERED")
            sheet1.clear()
            sheet1.append_rows(keep_rows, value_input_option="USER_ENTERED")
            logger.info(f"✅ Moved {len(done_rows)} DONE products to Sheet2.")
        else:
            logger.info("📭 No DONE rows to move.")

    except Exception as e:
        logger.exception("❌ Failed to move DONE rows to Sheet2.")

    except Exception as e:
        logger.exception("❌ Error in update_product_status_in_sheet")
        return False
