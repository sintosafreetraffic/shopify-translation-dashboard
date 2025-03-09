import pandas as pd
import sqlite3
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from shopify_api import fetch_product_by_id
from translation import google_translate, chatgpt_translate

DATABASE = "translations.db"
COLUMN_MAPPING = {"A": 0, "B": 1, "C": 2}  # Maps columns to index
CREDENTIALS_FILE = "credentials.json"
SHEET_NAME = "Translation Log"  # Change this to your actual Google Sheet name

def process_google_sheet(file, image_column="A", starting_row=2):
    """Extract product URLs from a Google Sheet and translate them."""
    df = pd.read_excel(file)
    
    if "Product URL" not in df.columns:
        return 0

    image_col_index = COLUMN_MAPPING.get(image_column, 0)  # Default to Column A
    count = 0

    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        
        for i, row in df.iterrows():
            if i + 1 < starting_row:  # Skip rows before the starting row
                continue

            product_url = row["Product URL"]
            image_url = str(row.iloc[image_col_index])  # Get image URL from selected column

            product = fetch_product_by_id(product_url)
            if product:
                product_id = product["id"]
                title = product["title"]
                description = product.get("body_html", "")

                translated_title = google_translate(title)
                translated_description = chatgpt_translate(description)

                cursor.execute("INSERT OR IGNORE INTO translations (product_id, product_title, translated_title, product_description, translated_description, image_url, batch, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                               (product_id, title, translated_title, description, translated_description, image_url, "Google Sheet Upload", "Pending"))
                count += 1
        conn.commit()
    return count

def log_translation(product_id, translated_title, translated_description, status):
    """Logs the translation into a Google Sheet"""
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
    client = gspread.authorize(creds)
    sheet = client.open(SHEET_NAME).sheet1

    sheet.append_row([product_id, translated_title, translated_description, status])