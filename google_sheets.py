import os
import re
import logging
import sqlite3
import pandas as pd
import gspread

from oauth2client.service_account import ServiceAccountCredentials

# For converting HTML to structured text
from bs4 import BeautifulSoup

# Local modules (adjust import paths if needed)
from shopify_api import fetch_product_by_id  # Must handle variant->product resolution
from translation import google_translate, chatgpt_translate

###############################################################################
# CONFIG & CONSTANTS
###############################################################################
DATABASE = "translations.db"

# Only allow columns A, B, or C
VALID_COLUMNS = {"A": 0, "B": 1, "C": 2}

# Google Sheets Logging
CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "Translation Log")

# Configure Logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

###############################################################################
# 1) PRE-PROCESS DESCRIPTION
###############################################################################
def pre_process_description(original_html: str) -> str:
    """
    Remove inline styles, empty <p>, repeated <br>, data-* attributes, etc.
    So ChatGPT or final display is simpler.
    """
    logging.debug("[pre_process_description] Original HTML snippet:\n%s", original_html[:300])

    # 1) Remove inline style="..."
    cleaned = re.sub(r'style\s*=\s*"[^"]*"', '', original_html, flags=re.IGNORECASE)
    logging.debug("[pre_process_description] After removing inline styles:\n%s", cleaned[:300])

    # 2) Remove empty <p> (like <p>&nbsp;</p>)
    cleaned = re.sub(r'<p[^>]*>(\s|&nbsp;)*</p>', '', cleaned, flags=re.IGNORECASE)
    logging.debug("[pre_process_description] After removing empty <p>:\n%s", cleaned[:300])

    # 3) Reduce repeated <br>
    cleaned = re.sub(r'(<br\s*/?>\s*){2,}', '<br>', cleaned)
    logging.debug("[pre_process_description] After reducing repeated <br>:\n%s", cleaned[:300])

    # 4) Remove data-* attributes (data-start, data-end, data-mce-*, etc.)
    cleaned = re.sub(r'\sdata-[^=]+="[^"]*"', '', cleaned)
    logging.debug("[pre_process_description] After removing data-*:\n%s", cleaned[:300])

    final_html = cleaned.strip()
    logging.debug("[pre_process_description] Final cleaned HTML:\n%s", final_html[:300])
    return final_html

###############################################################################
# 2) CONVERT HTML → STRUCTURED PLAIN TEXT
###############################################################################
def html_to_structured_text(html: str) -> str:
    """
    Parse HTML into a plain text representation:
      - Headings => '### Title'
      - Bullets => '- item'
      - paragraphs => plain lines
    Adjust the style as you like.
    """
    soup = BeautifulSoup(html, "html.parser")
    lines = []

    def walk(element):
        # Headings => # or ##
        if element.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            lvl = int(element.name[-1])  # e.g. '3' from 'h3'
            heading_text = element.get_text(strip=True)
            prefix = "#" * lvl
            lines.append(f"{prefix} {heading_text}")
            return

        elif element.name == "p":
            p_text = element.get_text(strip=True)
            if p_text:
                lines.append(p_text)
            return

        elif element.name == "ul":
            # Bullets => '- item'
            for li in element.find_all("li", recursive=False):
                li_text = li.get_text(strip=True)
                if li_text:
                    lines.append(f"- {li_text}")
            return

        elif element.name == "ol":
            # Numbered => '1. item'
            num = 1
            for li in element.find_all("li", recursive=False):
                li_text = li.get_text(strip=True)
                if li_text:
                    lines.append(f"{num}. {li_text}")
                    num += 1
            return

        else:
            # For div, span, etc., we walk children
            for child in element.children:
                if child.name is not None:
                    walk(child)

    walk(soup)
    return "\n".join(lines)

###############################################################################
# 3) FETCH PRODUCT HELPER (resolves variant->product if needed)
###############################################################################
def unified_fetch_product(id_or_url):
    logging.debug("[unified_fetch_product] Attempt fetch: %s", id_or_url)
    product = fetch_product_by_id(id_or_url)
    if product:
        logging.debug("[unified_fetch_product] Fetched product ID %s, title: %s",
                      product.get("id"), product.get("title"))
    else:
        logging.debug("[unified_fetch_product] No product for: %s", id_or_url)
    return product

###############################################################################
# 4) FETCH TEST PRODUCT FROM SHEET
###############################################################################
def fetch_test_product(file,
                       image_column="A",
                       starting_row=2,
                       pre_process=False,
                       convert_to_text=False):
    """
    1) Reads an Excel/CSV.
    2) Grab the product ID from the chosen col & row.
    3) Calls unified_fetch_product.
    4) If pre_process => pre_process_description.
    5) If convert_to_text => html_to_structured_text.
    Returns a dict: { success, row_index, product_id, title, description, image_url }
    """
    if image_column not in VALID_COLUMNS:
        err = f"Invalid column '{image_column}'. Use A, B, or C."
        logging.error("[fetch_test_product] %s", err)
        return {"error": err}

    logging.debug("[fetch_test_product] Opening file: %s", file)
    df = pd.read_excel(file)
    col_idx = VALID_COLUMNS[image_column]

    # Skip rows
    df = df.iloc[starting_row - 1:]
    logging.debug("[fetch_test_product] after skipping rows => shape=%s", df.shape)

    for i, row in df.iterrows():
        product_ref = str(row.iloc[col_idx]).strip()
        logging.debug("[fetch_test_product] Row %d => '%s'", i + starting_row, product_ref)

        if product_ref:
            product = unified_fetch_product(product_ref)
            if product:
                # Start with the raw or pre-processed HTML
                raw_html = product.get("body_html", "")
                if pre_process:
                    logging.debug("[fetch_test_product] Pre-processing row %d", i + starting_row)
                    raw_html = pre_process_description(raw_html)

                # Possibly convert HTML => plain text
                final_desc = raw_html
                if convert_to_text:
                    text_version = html_to_structured_text(final_desc)
                    final_desc = text_version

                return {
                    "success": True,
                    "row_index": i + starting_row,
                    "product_id": product["id"],
                    "title": product.get("title", ""),
                    "description": final_desc,
                    "image_url": product.get("image", {}).get("src", "")
                }

    msg = "No valid products found in the selected column."
    logging.warning("[fetch_test_product] %s", msg)
    return {"error": msg}

###############################################################################
# 5) PROCESS GOOGLE SHEET (Single Test Product)
###############################################################################
def process_google_sheet(file,
                         image_column="A",
                         starting_row=2,
                         pre_process=False,
                         convert_to_text=False):
    """
    1) Calls fetch_test_product with the chosen flags.
    2) If success, returns { test_product: {...}, bulk_ready: True, message }
    """
    logging.debug("[process_google_sheet] file=%s, col=%s, row=%d, pre_process=%s, convert_to_text=%s",
                  file, image_column, starting_row, pre_process, convert_to_text)

    test_prod = fetch_test_product(file,
                                   image_column=image_column,
                                   starting_row=starting_row,
                                   pre_process=pre_process,
                                   convert_to_text=convert_to_text)
    if "error" in test_prod:
        logging.debug("[process_google_sheet] Error => %s", test_prod["error"])
        return test_prod

    result = {
        "test_product": test_prod,
        "bulk_ready": True,
        "message": "Test product fetched. You can now run bulk translation."
    }
    logging.debug("[process_google_sheet] returning => %s", result)
    return result

###############################################################################
# 6) BULK TRANSLATION: PRE-PROCESS & STORE "PENDING"
###############################################################################
def process_bulk_translation(file, image_column="A", starting_row=2, target_lang="de"):
    """
    1) Read file 
    2) For each row => fetch product => pre_process => 
       google/chatgpt => store in DB as 'Pending'
    """
    if image_column not in VALID_COLUMNS:
        err = f"Invalid column '{image_column}'. Use A, B, or C."
        logging.error("[process_bulk_translation] %s", err)
        return {"error": err}

    logging.debug("[process_bulk_translation] file=%s col=%s row=%d lang=%s",
                  file, image_column, starting_row, target_lang)

    df = pd.read_excel(file)
    col_idx = VALID_COLUMNS[image_column]
    count = 0

    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()

        for i, row in df.iterrows():
            actual_row = i + 1
            if actual_row < starting_row:
                continue

            product_ref = str(row.iloc[col_idx]).strip()
            if not product_ref:
                logging.debug("[process_bulk_translation] row %d => empty => skip", actual_row)
                continue

            logging.debug("[process_bulk_translation] row %d => '%s'", actual_row, product_ref)
            product = unified_fetch_product(product_ref)
            if not product:
                logging.debug("[process_bulk_translation] no product => skip row %d", actual_row)
                continue

            product_id = product["id"]
            original_title = product.get("title", "")
            original_desc = product.get("body_html", "")

            # Pre-process
            logging.debug("[process_bulk_translation] row %d => Pre-processing desc", actual_row)
            cleaned_desc = pre_process_description(original_desc)

            # e.g. Translate title => google, desc => chatgpt
            logging.debug("[process_bulk_translation] row %d => google+chatgpt translation", actual_row)
            translated_title = google_translate(original_title, target_language=target_lang)
            translated_description = chatgpt_translate(cleaned_desc, target_language=target_lang)

            # Insert as "Pending"
            logging.debug("[process_bulk_translation] row %d => Insert to DB as Pending", actual_row)
            cursor.execute("""
                INSERT OR IGNORE INTO translations
                (product_id, product_title, translated_title, product_description, translated_description, image_url, batch, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                product_id,
                original_title,
                translated_title,
                original_desc,  # store raw desc
                translated_description,
                product.get("image", {}).get("src", ""),
                "Google Sheet Bulk",
                "Pending"
            ))
            count += 1

        conn.commit()

    logging.info("[process_bulk_translation] Processed %d products successfully.", count)
    return {"success": True, "message": f"{count} products processed successfully."}

###############################################################################
# 7) LOG TRANSLATION (OPTIONAL)
###############################################################################
def log_translation(product_id, translated_title, translated_description, status):
    """
    Log a translation event in a separate Google Sheet, if desired.
    """
    logging.debug("[log_translation] product=%s status=%s", product_id, status)
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME).sheet1

        sheet.append_row([product_id, translated_title, translated_description, status])
        logging.info("[log_translation] Logged product %s => %s in Google Sheet %s",
                     product_id, status, SHEET_NAME)
    except Exception as e:
        logging.error("[log_translation] error => %s", e)
