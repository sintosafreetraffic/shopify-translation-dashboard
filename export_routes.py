import os
import json
import logging
import requests
from flask import Blueprint, request, jsonify, render_template
from shopify_api import fetch_product_by_id
from utils import slugify
from google_sheets import move_done_to_sheet2, export_sales_to_sheet
from export_variants_utils import get_product_option_values, update_product_option_values, apply_translation_method
from google_sheets import get_pending_products_from_sheet
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from threading import Lock
from google_sheets import get_products_pending_translation_from_sheet1, mark_product_translation_done_in_sheet, update_product_status_in_sheet
from post_processing import post_process_description
import time
from bs4 import BeautifulSoup
import html

print("\u2705 export_routes.py loaded and Blueprint registered.")

export_bp = Blueprint("export", __name__)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SHOPIFY_STORE_URL = os.getenv("SHOPIFY_STORE_URL")
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
GOOGLE_SHEET_ID = "11PVJZkYeZfEtcuXZ7U4xiV1r_axgAIaSe88VgFF189E"

def ensure_https(url):
    url = url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        return f"https://{url}"
    return url


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

def update_product_gid_in_sheet(product_id, cloned_gid):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)

        sheet = client.open_by_key(GOOGLE_SHEET_ID).worksheet("Sheet1")

        all_values = sheet.get_all_values()
        for idx, row in enumerate(all_values[1:], start=2):
            if str(row[0]).strip() == str(product_id):
                sheet.update_cell(idx, 5, cloned_gid)  # Column E
                logger.info(f"✅ Set cloned GID for product_id={product_id} → {cloned_gid}")
                return True
        logger.warning(f"⚠️ Could not find product_id={product_id} to set cloned GID.")
        return False

    except Exception as e:
        logger.exception("❌ Error updating cloned GID in Google Sheets")
        return False


def get_sheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

    try:
        path = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
        logger.info(f"🔐 Using credentials from: {path}")
        creds = ServiceAccountCredentials.from_json_keyfile_name(path, scope)
        return gspread.authorize(creds)

    except Exception as e1:
        logger.warning(f"⚠️ Could not load creds using env path. Reason: {repr(e1)}")
        # Fallback
        try:
            creds = ServiceAccountCredentials.from_service_account_file(
                "/Users/saschavanwell/.config/gspread/service_account.json", scopes=scope
            )
            return gspread.authorize(creds)
        except Exception as e2:
            logger.warning(f"⚠️ Could not load fallback Google Sheets creds either. Reason: {repr(e2)}")
            return None



@export_bp.route("/export")
def export():
    return render_template("export.html")

@export_bp.route("/get_stores", methods=["GET"])
def get_stores():
    try:
        with open("stores.json", "r") as f:
            stores = json.load(f)
        return jsonify(stores)
    except Exception:
        logger.exception("\u274c Failed to load store list.")
        return jsonify({"error": "Failed to load stores"}), 500

def fetch_product_by_handle(handle, shopify_store_url, shopify_api_key):
    url = f"{ensure_https(shopify_store_url)}/admin/api/2023-04/products.json?handle={handle}"
    headers = {
        "X-Shopify-Access-Token": shopify_api_key,
        "Content-Type": "application/json"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        products = response.json().get("products", [])
        return products[0] if products else None
    return None

def get_sold_product_details(start_date, end_date, min_sales):
    logger.info(f"\U0001f9fe Fetching sales from {start_date} to {end_date} with ≥ {min_sales} sales")
    endpoint = (f"{ensure_https(SHOPIFY_STORE_URL)}/admin/api/2023-04/orders.json?status=any"
                f"&created_at_min={start_date}T00:00:00Z"
                f"&created_at_max={end_date}T23:59:59Z"
                f"&fields=line_items")
    headers = {"X-Shopify-Access-Token": SHOPIFY_API_KEY}
    response = requests.get(endpoint, headers=headers)
    if response.status_code != 200:
        logger.error(f"\u274c Failed to fetch orders: {response.status_code}")
        return []

    orders = response.json().get("orders", [])
    counter = {}
    for order in orders:
        for li in order.get("line_items", []):
            pid = li["product_id"]
            t = li["title"]
            key = (pid, t)
            counter[key] = counter.get(key, 0) + 1

    return [{"product_id": pid, "title": title, "sales_count": count} for (pid, title), count in counter.items() if count >= min_sales]

currently_processing_lock = Lock()
currently_processing_ids = set()

def clone_products_to_target_store(product_sales, target_store):
    logger = logging.getLogger(__name__)

    # Track processed IDs within this specific run
    processed_ids_current_run = set()

    # === STEP 1: Deduplicate Input ===
    seen_ids = set()
    unique_sales = []
    duplicate_input_ids = []

    for p in product_sales:
        pid = str(p.get("product_id"))
        if pid in seen_ids:
            duplicate_input_ids.append(pid)
            continue
        seen_ids.add(pid)
        unique_sales.append(p)

    logger.info(f"🧠 Initial deduplication completed: Received={len(product_sales)}, Unique={len(unique_sales)}, Duplicates skipped={len(duplicate_input_ids)}")
    if duplicate_input_ids:
        logger.debug(f"🧹 Duplicate input IDs skipped: {duplicate_input_ids}")

    # === STEP 2: Load Allowed and Blocked IDs from Google Sheets ===
    allowed_ids_sheet1, blocked_ids = set(), set()
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json"), scope
        )
        client = gspread.authorize(creds)
        sheet = client.open_by_key(GOOGLE_SHEET_ID)
        sheet1_records = sheet.worksheet("Sheet1").get_all_records()
        sheet2_records = sheet.worksheet("Sheet2").get_all_records()

        sheet1_cloned_gids = {}

        for row in sheet1_records:
            pid = str(row.get("Product ID", "")).strip()
            status = row.get("Status", "").strip().upper()
            cloned_gid = row.get("Cloned Product GID", "").strip()

            if pid:
                if status == "DONE":
                    blocked_ids.add(pid)
                else:
                    allowed_ids_sheet1.add(pid)
                    if cloned_gid:
                        sheet1_cloned_gids[pid] = cloned_gid  # Track cloned GIDs

        blocked_ids.update(str(row.get("Product ID", "")).strip() for row in sheet2_records if row.get("Product ID", "").strip())

        logger.info(f"📋 Google Sheets loaded. Allowed IDs: {len(allowed_ids_sheet1)}, Blocked IDs: {len(blocked_ids)}")

    except Exception as e:
        logger.exception(f"🔥 Failed loading Google Sheets: {e}")

    # === STEP 3: Filter based on Google Sheets ===
    pre_filter_count = len(unique_sales)
    if allowed_ids_sheet1:
        unique_sales = [
            p for p in unique_sales
            if str(p["product_id"]).strip() in allowed_ids_sheet1
            and str(p["product_id"]).strip() not in blocked_ids
            and str(p["product_id"]).strip() not in sheet1_cloned_gids  # Skip if already cloned
        ]
        logger.info(f"🧹 Filtered by Sheets from {pre_filter_count} to {len(unique_sales)} items.")
    else:
        logger.warning("⚠️ No IDs loaded from Sheets, skipping filtering.")

    # === STEP 4: Filter to Prevent Simultaneous and Duplicate Processing ===
    filtered_sales = []
    skipped_currently_processing = []
    skipped_already_processed_this_run = []

    with currently_processing_lock:
        for item in unique_sales:
            pid = item["product_id"]
            if pid in currently_processing_ids:
                skipped_currently_processing.append(pid)
                continue
            if pid in processed_ids_current_run:
                skipped_already_processed_this_run.append(pid)
                continue
            filtered_sales.append(item)
            currently_processing_ids.add(pid)
            processed_ids_current_run.add(pid)

    logger.info(f"🛡️ Duplicate processing filter:")
    logger.info(f"   ✅ Allowed: {len(filtered_sales)}")
    logger.info(f"   ⏩ Skipped (processing elsewhere): {len(skipped_currently_processing)}")
    logger.info(f"   🔄 Skipped (already processed): {len(skipped_already_processed_this_run)}")

    # === STEP 5: Clone Products to Target Store ===
    created_products = []
    for item in filtered_sales:
        original_pid = item["product_id"]
        sales_count = item["sales_count"]
        logger.debug(f"⏳ Processing product ID: {original_pid}")

        try:
            product_data = fetch_product_by_id(original_pid)
            if not product_data:
                logger.warning(f"⚠️ Could not fetch data for {original_pid}, skipping.")
                continue

            title = product_data.get("title", "").strip()
            cloned_handle = f"{slugify(title)}-{str(original_pid)[-4:]}"

            if fetch_product_by_handle(cloned_handle, target_store["shopify_store_url"], target_store["shopify_api_key"]):
                logger.warning(f"⚠️ Handle '{cloned_handle}' exists in target store '{target_store['value']}', skipping.")
                continue

            product_payload = {
                "product": {
                    "title": title,
                    "body_html": product_data.get("body_html", ""),
                    "handle": cloned_handle,
                    "status": "draft",
                    "images": [{"src": img["src"]} for img in product_data.get("images", []) if img.get("src")],
                    "options": [{"name": o.get("name", ""), "values": o.get("values", [])} for o in product_data.get("options", [])],
                    "variants": [{
                        "option1": v.get("option1"),
                        "option2": v.get("option2"),
                        "option3": v.get("option3"),
                        "price": v.get("price"),
                        "sku": v.get("sku"),
                        "requires_shipping": v.get("requires_shipping", True),
                    } for v in product_data.get("variants", [])],
                    "product_type": product_data.get("product_type", ""),
                    "tags": "NEEDS_TRANSLATION",
                }
            }

            create_url = f"{ensure_https(target_store['shopify_store_url'].rstrip('/'))}/admin/api/2023-04/products.json"
            headers = {
                "X-Shopify-Access-Token": target_store["shopify_api_key"],
                "Content-Type": "application/json"
            }

            response = requests.post(create_url, json=product_payload, headers=headers)
            if response.ok:
                new_product = response.json()["product"]
                cloned_product_id = new_product.get("admin_graphql_api_id")

                cloned_product_id = new_product.get("admin_graphql_api_id")

                created_products.append({
                    "original_id": original_pid,
                    "cloned_id": new_product["id"],
                    "title": title,
                    "handle": cloned_handle,
                    "store": target_store["value"],
                    "sales_count": sales_count
                })

                update_product_gid_in_sheet(original_pid, cloned_product_id)

                logger.info(f"✅ Cloned {original_pid} to {new_product['id']} in {target_store['value']}")
            else:
                logger.error(f"❌ Cloning failed for {original_pid}: {response.status_code} {response.text}")

        except Exception as e:
            logger.exception(f"🔥 Exception cloning product {original_pid}: {e}")

        finally:
            with currently_processing_lock:
                currently_processing_ids.remove(original_pid)

    logger.info(f"🚩 Cloning complete. Total products cloned: {len(created_products)}")

    return created_products

@export_bp.route("/generate_sales_sheet", methods=["POST"])
def generate_sales_sheet():
    try:
        data = request.get_json()
        start_date = data.get("start_date")
        end_date = data.get("end_date")
        min_sales = int(data.get("min_sales", 1))

        if not start_date or not end_date:
            return jsonify({"error": "Missing start or end date."}), 400

        sales_data = get_sold_product_details(start_date, end_date, min_sales)
        sheet_url = export_sales_to_sheet(sales_data)
        return jsonify({"sheet_url": sheet_url})
    except Exception as e:
        logger.exception("🔥 Error in generate_sales_sheet")
        return jsonify({"error": str(e)}), 500
    
def fetch_product_by_gid(product_gid, shopify_store_url, shopify_api_key):
    query = """
    query getProduct($id: ID!) {
      product(id: $id) {
        id
        title
        bodyHtml
        images(first: 5) {
          edges {
            node {
              src
            }
          }
        }
      }
    }
    """
    variables = {"id": product_gid}

    response = shopify_graphql_request(query, variables, shopify_store_url, shopify_api_key)
    product = response["data"]["product"]

    # Extract image URLs from GraphQL edge structure
    images = product.get("images", {}).get("edges", [])
    product["images"] = [{"src": edge["node"]["src"]} for edge in images]

    return product


def update_product_title_and_description(
    product_gid,
    shopify_store_url,
    shopify_api_key,
    target_language,
    translation_method,
    title_prompt="",
    desc_prompt="",
    product_data=None
):

    product_data = fetch_product_by_gid(product_gid, shopify_store_url, shopify_api_key)

    if not product_data:
        logger.warning(f"❌ Failed to fetch product by GID: {product_gid}")
        return False

    title = product_data.get("title", "")
    description = product_data.get("bodyHtml", "")

    # 🧠 Use your export_translation.py logic properly
    translated_title = apply_translation_method(
        original_text=title,
        method=translation_method,
        custom_prompt="",
        source_lang="auto",
        target_lang=target_language,
        field_type="title"
    )

    translated_description = apply_translation_method(
        original_text=description,
        method=translation_method,
        custom_prompt="",
        source_lang="auto",
        target_lang=target_language,
        product_title=title,
        field_type="description",
        description=description
    )
    # ✅ 1. Unescape HTML (fix &amp;)
    translated_description = html.unescape(translated_description)
    # ✅ 2. Inject images if missing
    soup = BeautifulSoup(translated_description, "html.parser")
    images = product_data.get("images", [])
    if images and not soup.find("img"):
        for img in images[:2]:  # Inject 1 or 2 images max
            img_tag = soup.new_tag("img", src=img["src"], style="margin: 10px auto; display: block; max-width: 100%;")
            soup.insert(0, img_tag)

    # ✅ 3. Center content (optional styling tweak)
    for tag in soup.find_all(["p", "div"]):
        tag['style'] = tag.get('style', '') + '; text-align: center;'

    translated_description = str(soup)

        # 🧠 Use your export_translation.py logic properly
    translated_title = apply_translation_method(
        original_text=title,
        method=translation_method,
        custom_prompt=title_prompt,  # if user provided a prompt
        source_lang="auto",
        target_lang=target_language,
        field_type="title"
    )

    translated_description = apply_translation_method(
        original_text=description,
        method=translation_method,
        custom_prompt=desc_prompt,  # if user provided a prompt
        source_lang="auto",
        target_lang=target_language,
        product_title=title,
        field_type="description",
        description=description
    )

    # ✅ Apply post-processing to inject images and center layout
    translated_description = post_process_description(
        original_html=description,
        new_html=translated_description,
        method=translation_method,
        product_data=product_data,  # make sure this contains 'images'
        target_lang=target_language
    )

    translated_description = html.unescape(translated_description)

    update_payload = {
        "product": {
            "id": product_gid.split("/")[-1],  # Convert gid to numeric ID
            "title": translated_title,
            "body_html": translated_description
        }
    }

    update_url = f"{ensure_https(shopify_store_url)}/admin/api/2023-04/products/{update_payload['product']['id']}.json"
    headers = {
        "X-Shopify-Access-Token": shopify_api_key,
        "Content-Type": "application/json"
    }

    response = requests.put(update_url, json=update_payload, headers=headers)

    if response.ok:
        logger.info(f"📝 Updated title and description for product {product_gid}")
        return True
    else:
        logger.error(f"❌ Failed to update product {product_gid}: {response.status_code} {response.text}")
        return False


@export_bp.route("/run_export", methods=["POST"])
def run_export():
    try:
        data = request.get_json()

        start_date = data.get("start_date")
        end_date = data.get("end_date")
        min_sales = int(data.get("min_sales", 1))
        store_value = data.get("store")
        language = data.get("language", "de")

        review_only = data.get("review_only", False)
        run_phase_1 = data.get("run_phase_1", False)
        run_phase_2 = data.get("run_phase_2", False)

        if not (start_date and end_date and store_value):
            return jsonify({"error": "Missing required fields"}), 400

        with open("stores.json", "r") as f:
            stores = json.load(f)

        target_store = next((s for s in stores if s["value"] == store_value), None)
        if not target_store:
            return jsonify({"error": "Target store not found"}), 400

        # ✅ Phase: just generate the sheet
        if review_only:
            product_sales = get_sold_product_details(start_date, end_date, min_sales)
            sheet_url = export_sales_to_sheet(product_sales)
            return jsonify({
                "message": f"✅ Sales sheet generated",
                "sheet_url": sheet_url
            })

        # ✅ Phase: clone only
        if run_phase_1:
            product_sales = get_pending_products_from_sheet()  # ⬅️ you'll need to implement this if not done yet
            cloned = clone_products_to_target_store(product_sales, target_store)
            return jsonify({
                "message": f"✅ Cloned {len(cloned)} products",
                "products": cloned
            })
        # ✅ Phase: translate only
        # ✅ Phase: translate only
        if run_phase_2:
            # Setup Google Sheets client
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
            client = gspread.authorize(creds)
            title_description_method = request.form.get("title_method", "google")      # google, chatgpt, deepl
            description_method = request.form.get("desc_method", "google")
            variant_translation_method = request.form.get("variant_method", "google")
                    # ✅ Use authorized client to load the sheet once
            sheet = client.open_by_key(GOOGLE_SHEET_ID).worksheet("Sheet1")

            # ✅ Get products marked as PENDING (passing the sheet)
            print("🧪 Before calling get_products_pending_translation_from_sheet")
            product_sales = get_products_pending_translation_from_sheet1(sheet)
            print("✅ After calling get_products_pending_translation_from_sheet")

            title_prompt = request.form.get("title_prompt", "").strip()
            desc_prompt = request.form.get("desc_prompt", "").strip()

            # Step 1: Fetch products explicitly marked as "PENDING"
            product_sales = get_pending_products_from_sheet()

            if not product_sales:
                return jsonify({"message": "No products pending translation."})

            translated_products = []

            for product in product_sales:
                product_gid = product.get('cloned_gid')
                if not product_gid:
                    logger.warning(f"⚠️ No cloned_gid found for {product['product_id']}, skipping.")
                    continue

                # Fetch cloned product data
                product_data = fetch_product_by_gid(
                    product_gid,
                    shopify_store_url=target_store["shopify_store_url"],
                    shopify_api_key=target_store["shopify_api_key"]
                )

                # Update Shopify product
                update_product_title_and_description(
                    product_gid=product_gid,
                    shopify_store_url=target_store["shopify_store_url"],
                    shopify_api_key=target_store["shopify_api_key"],
                    target_language=language,
                    translation_method=title_description_method,
                    title_prompt=title_prompt,
                    desc_prompt=desc_prompt,
                    product_data=product_data
                )

                # Fetch and translate options
                options = get_product_option_values(
                    product_gid,
                    shopify_store_url=target_store["shopify_store_url"],
                    shopify_api_key=target_store["shopify_api_key"]
                )

                if not options:
                    logger.warning(f"No options found for {product_gid}")
                    continue

                success = True
                for option in options:
                    updated = update_product_option_values(
                        product_gid,
                        option,
                        target_language=language,
                        source_language="auto",
                        translation_method=variant_translation_method,
                        shopify_store_url=target_store["shopify_store_url"],
                        shopify_api_key=target_store["shopify_api_key"]
                    )

                    if not updated:
                        success = False
                        break

                if success:
                    translated_products.append(product_gid)
                    client = gspread.authorize(creds)
                    sheet = client.open_by_key(GOOGLE_SHEET_ID).worksheet("Sheet1")
                    update_product_status_in_sheet(product["product_id"], "TRANSLATED", sheet=sheet)
                    time.sleep(1.5)


            return jsonify({
                "message": f"🌍 Successfully translated {len(translated_products)} products",
                "products_translated": translated_products
            })

    except Exception as e:
        logger.exception("🔥 Error in /run_export")
        return jsonify({"error": str(e)}), 500

move_done_to_sheet2()