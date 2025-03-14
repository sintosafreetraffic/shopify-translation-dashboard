import os
import sys

sys.path.append(os.path.abspath(os.path.dirname(__file__)))  # Ensure current directory is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))  # Add parent directory

print("PYTHONPATH:", sys.path)  # Debugging output

import sqlite3
import requests
import json
import logging
import re  # For simple HTML pattern matching
from translation import chatgpt_translate, google_translate, deepl_translate
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from variants_utils import get_product_option_values, update_product_option_values



# If your modules are located one directory up
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

load_dotenv()

# Custom modules
from shopify_api import fetch_product_by_id, fetch_products_by_collection, update_product_translation
from translation import chatgpt_translate, google_translate, deepl_translate, chatgpt_translate_title  # Extend as needed
from google_sheets import process_google_sheet

# ------------------------------ #
# Load Environment Variables
# ------------------------------ #

DEEPL_API_KEY = os.getenv("DEEPL_API_KEY")
GOOGLE_TRANSLATE_API_KEY = os.getenv("GOOGLE_TRANSLATE_API_KEY")  # If needed for advanced Google Translate API
CHATGPT_API_KEY = os.getenv("CHATGPT_API_KEY")
SHOPIFY_API_URL = os.getenv("SHOPIFY_API_URL")  # Shopify store URL
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_STORE_URL=os.getenv("SHOPIFY_STORE_URL")

if not SHOPIFY_STORE_URL or not SHOPIFY_API_KEY:
    raise ValueError("Missing Shopify credentials! Please set SHOPIFY_STORE_URL and SHOPIFY_API_KEY.")
    
# ------------------------------ #
# Logging Configuration
# ------------------------------ #
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------------------ #
# Initialize Flask App
# ------------------------------ #
app = Flask(__name__, template_folder="templates")
CORS(app)  

# ------------------------------ #
# Database Setup
# ------------------------------ #
DATABASE = "translations.db"

def init_db():
    """Initialize the SQLite database for storing translation information."""
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS translations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT UNIQUE,
                product_title TEXT,
                translated_title TEXT,
                product_description TEXT,
                translated_description TEXT,
                image_url TEXT,
                batch TEXT,
                status TEXT
            )
        """)
        conn.commit()
        logger.info("Database initialized.")

init_db()

# ------------------------------ #
# Shopify API Helper
# ------------------------------ #
def shopify_request(method, url, **kwargs):
    """
    Helper to perform a Shopify API request.
    Automatically includes the Shopify API key header and logs errors.
    """
    headers = kwargs.pop("headers", {})
    headers["X-Shopify-Access-Token"] = SHOPIFY_API_KEY
    try:
        response = requests.request(method, url, headers=headers, **kwargs)
        if response.status_code not in (200, 201):
            logger.error(f"Shopify API error: {response.status_code} {response.text}")
        return response
    except Exception as e:
        logger.exception(f"Error during Shopify request: {e}")
        raise

#############################
# post_process_description
#############################

def post_process_description(original_html, new_html, method, product_data=None, target_lang='en'):
    """
    Final layout:
      1) Title
      2) Short Introduction
      3) First image (480px)
      4) "Product Advantages" (translated)
      5) Bullet points (fully centered & bolded before ':' or '-')
      6) Second image (480px)
      7) CTA (h4)
    """

    if not new_html.strip() or method.lower() != "chatgpt":
        return new_html

    # Parse AI output
    def parse_ai_description(ai_text):
        parsed_data = {'title': '', 'introduction': '', 'features': [], 'cta': ''}

        match_title = re.search(r"(?i)product title\s*:\s*(.*)", ai_text)
        if match_title:
            parsed_data['title'] = match_title.group(1).strip()

        match_intro = re.search(r"(?i)short introduction\s*:\s*(.*)", ai_text)
        if match_intro:
            parsed_data['introduction'] = match_intro.group(1).strip()

        features_section = re.search(r"(?is)product advantages\s*:(.*?)(?:call to action:|$)", ai_text)
        if features_section:
            features_raw = features_section.group(1).strip()
            bullets = re.findall(r"-\s*(.+)", features_raw)
            parsed_data['features'] = [b.strip() for b in bullets if b.strip() and not b.lower().startswith("additional feature")]

        match_cta = re.search(r"(?i)call to action\s*:\s*(.*)", ai_text)
        if match_cta:
            parsed_data['cta'] = match_cta.group(1).strip()

        return parsed_data

    parsed = parse_ai_description(new_html)

    # Localization for "Product Advantages" and "CTA"
    localized_labels = {
        'en': {'advantages': 'Product Advantages', 'cta': 'Buy Now!'},
        'de': {'advantages': 'Produktvorteile', 'cta': 'Jetzt kaufen!'},
        'es': {'advantages': 'Ventajas del producto', 'cta': '¡Compra ahora!'},
        'fr': {'advantages': 'Avantages du produit', 'cta': 'Achetez maintenant !'},
        'it': {'advantages': 'Vantaggi del prodotto', 'cta': 'Acquista ora!'},
        'nl': {'advantages': 'Productvoordelen', 'cta': 'Koop nu!'},
        'pt': {'advantages': 'Vantagens do produto', 'cta': 'Compre agora!'},
        'ru': {'advantages': 'Преимущества товара', 'cta': 'Купить сейчас!'},
        'ja': {'advantages': '製品の特長', 'cta': '今すぐ購入！'},
        'zh': {'advantages': '产品优势', 'cta': '立即购买！'},
    }
    labels = localized_labels.get(target_lang, localized_labels['en'])

    # Remove "Feature 1, 2, 3..." and bold text before ':' or '-'
    bullet_li_list = []
    for bp in parsed['features']:
        bp = re.sub(r'(?i)^Feature \d+:\s*', '', bp)  # Remove "Feature X:"
        parts = re.split(r'[:\-]', bp, 1)  # Split on ':' or '-'
        if len(parts) == 2:
            bold_part, rest_part = parts
            bullet_li_list.append(f"<li><strong>{bold_part.strip()}</strong>: {rest_part.strip()}</li>")
        else:
            bullet_li_list.append(f"<li><strong>{bp.strip()}</strong></li>")  # No colon or dash, just bold entire line

    bullet_str = "".join(bullet_li_list)

    # Images from product data
    image1_url = product_data['images'][0]['src'] if product_data and product_data.get('images') else ""
    image2_url = product_data['images'][1]['src'] if product_data and len(product_data.get('images', [])) > 1 else ""

    # Final HTML Template
    final_html = f"""
    <div style="text-align:center; margin:0 auto; max-width:800px;">
      <h3 style="font-weight:bold;">{parsed['title']}</h3>
      <p>{parsed['introduction']}</p>

      <div style="margin:1em 0;">
        <img src="{image1_url}" style="width:480px; max-width:100%;"/>
      </div>

      <h3 style="font-weight:bold;">{labels['advantages']}</h3>
      <div style="display: flex; justify-content: center;">
        <ul style="list-style-position: inside; text-align: center;">
          {bullet_str}
        </ul>
      </div>

      <div style="margin:2em 0;">
        <img src="{image2_url}" style="width:480px; max-width:100%;"/>
      </div>

      <h4 style="font-weight:bold; margin:1.5em 0; font-size:1.2em;">{parsed['cta']}</h4>
    </div>
    """.strip()

    logging.info("post_process_description: Final HTML built, fully structured, centered bullets, localized headers.")
    return final_html

# ------------------------------ #
# slugify
# ------------------------------ #
def slugify(text): 
    """
    Convert text to a URL-friendly slug.
    """
    return (
        text.lower()
            .replace(" ", "-")
            .replace("ä", "ae")
            .replace("ö", "oe")
            .replace("ü", "ue")
            .replace("ß", "ss")
            .strip()
    )

# ------------------------------ #
# apply_translation_method
# ------------------------------ #
def apply_translation_method(original_text, method, custom_prompt, source_lang, target_lang, product_title=""):
    """
    Decide which translation approach to use:
      - google
      - deepl
      - chatgpt

    This function logs the chosen method and returns the final translated text.
    """
    logger.info("apply_translation_method: method=%s, prompt=%s", method, custom_prompt)

    chosen_lower = method.lower()
    if chosen_lower == "chatgpt":
        return chatgpt_translate(
            text=original_text,
            custom_prompt=custom_prompt,
            target_language=target_lang,
            product_title=product_title
        )
    elif chosen_lower == "google":
        return google_translate(
            original_text,
            source_language=source_lang,
            target_language=target_lang
        )
    elif chosen_lower == "deepl":
        return deepl_translate(
            original_text,
            source_language=source_lang,
            target_language=target_lang
        )
    else:
        logger.warning("Unrecognized method '%s'. Returning original text.", method)
        return original_text

# ------------------------------ #
# Flask Routes
# ------------------------------ #

@app.route("/")
def index():
    """Render the main translation dashboard UI (index.html)."""
    return render_template("index.html")

# --- Get Collections ---
@app.route("/get_collections", methods=["GET"])
def get_collections():
    """
    Fetch both smart and custom collections from Shopify for the dropdown.
    """
    url_custom = f"https://{SHOPIFY_STORE_URL}/admin/api/2023-04/custom_collections.json"
    url_smart = f"https://{SHOPIFY_STORE_URL}/admin/api/2023-04/smart_collections.json"

    custom_resp = shopify_request("GET", url_custom)
    smart_resp = shopify_request("GET", url_smart)

    custom_collections = custom_resp.json().get("custom_collections", []) if custom_resp.status_code == 200 else []
    smart_collections = smart_resp.json().get("smart_collections", []) if smart_resp.status_code == 200 else []

    all_collections = custom_collections + smart_collections
    result = [{"id": c["id"], "title": c["title"]} for c in all_collections]
    return jsonify({"collections": result})


# --- Fetch Products by Collection ---
@app.route("/fetch_products_by_collection", methods=["POST"])
def fetch_products_by_collection():
    """
    Fetch product details (without variants) from Shopify based on the selected collection.
    Returns collection name, product count, product list, and Shopify GIDs.
    """
    try:
        data = request.json
        collection_id = data.get("collection_id")
        if not collection_id:
            return jsonify({"error": "No collection selected"}), 400

        # Fetch products from Shopify API
        url = (
            f"https://{SHOPIFY_STORE_URL}/admin/api/2023-04/products.json"
            f"?collection_id={collection_id}&fields=id,title,body_html,image,images"
        )
        resp = shopify_request("GET", url)
        if resp.status_code != 200:
            return jsonify({"error": "Failed to fetch products from Shopify."}), 500

        products = resp.json().get("products", [])
        if not products:
            return jsonify({"error": "No products found in this collection."}), 404

        # Convert product IDs to Shopify Global IDs (GIDs)
        product_data = []
        for product in products:
            product_gid = f"gid://shopify/Product/{product['id']}"
            product["gid"] = product_gid  # Add GID to product data
            product_data.append(product)

        return jsonify({
            "success": True,
            "collection_name": data.get("collection_name", "Unknown Collection"),
            "product_count": len(products),
            "products": product_data,  # Now includes Shopify GIDs
            "product_gids": [p["gid"] for p in products]  # Separate GID list
        })

    except Exception as e:
        logger.exception(e)
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500


# --- Fetch Variants ---
@app.route("/fetch_variants", methods=["POST"])
def fetch_variants():
    """
    Fetch variants for a given product ID from Shopify.
    """
    try:
        data = request.json
        product_id = data.get("product_id")
        if not product_id:
            return jsonify({"error": "No product ID provided"}), 400

        url = f"https://{SHOPIFY_STORE_URL}/admin/api/2023-04/products/{product_id}/variants.json"
        resp = shopify_request("GET", url)
        if resp.status_code != 200:
            return jsonify({"error": "Failed to fetch variants from Shopify."}), 500

        variants = resp.json().get("variants", [])
        return jsonify({"success": True, "product_id": product_id, "variants": variants})
    except Exception as e:
        logger.exception(e)
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

# --- Upload & Process Google Sheet ---
@app.route("/upload_google_sheet", methods=["POST"])
def upload_google_sheet():
    """
    Upload and process a Google Sheet (or CSV/XLSX) for translation.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    image_column = request.form.get("image_column", "A")
    starting_row = int(request.form.get("starting_row", 2))
    if starting_row < 2:
        return jsonify({"error": "Starting row must be at least 2."}), 400

    processed_count = process_google_sheet(file, image_column, starting_row)
    return jsonify({
        "success": True,
        "message": f"Processed {processed_count} products from the Google Sheet."
    })

# --- Test Product Endpoint ---
@app.route("/test_product", methods=["GET"])
def test_product():
    """
    Fetch a single test product (with variants) from Shopify using TEST_PRODUCT_ID.
    """
    try:
        test_product_id = os.getenv("TEST_PRODUCT_ID", "1234567890")
        url = (
            f"https://{SHOPIFY_STORE_URL}/admin/api/2023-04/products/{test_product_id}.json"
            f"?fields=id,title,body_html,handle,tags,metafields,variants,images"
        )
        resp = shopify_request("GET", url)
        if resp.status_code != 200:
            return jsonify({"error": "Failed to fetch the test product"}), 500

        product = resp.json().get("product", {})
        if not product:
            return jsonify({"error": "Test product not found"}), 404

        return jsonify({"success": True, "product": product})
    except Exception as e:
        logger.exception(e)
        return jsonify({"error": str(e)}), 500
    
def clean_title_output(title):
    """
    Removes unnecessary quotation marks and extra spaces from ChatGPT-generated titles.
    """
    return title.strip().strip('"').strip("'")

# --- Translate Single Product ---
@app.route("/translate_test_product", methods=["POST"])
def translate_test_product():
    """
    Translate product fields using Google, DeepL, or ChatGPT, clearly preserving
    HTML formatting and structured content if ChatGPT is selected.
    """
    try:
        data = request.json
        product_id = data.get("product_id")
        fields = data.get("fields", [])
        methods = data.get("field_methods", {})

        prompt_title = data.get("prompt_title", "")
        prompt_desc = data.get("prompt_desc", "")
        prompt_tags = data.get("prompt_tags", "")
        prompt_handle = data.get("prompt_handle", "")
        prompt_variants = data.get("prompt_variants", "")

        source_lang = data.get("source_language", "auto")
        target_lang = data.get("target_language", "de")
        logger.info(f"Received target_language: '{target_lang}' for translation.")

        if not product_id:
            return jsonify({"error": "No product ID provided"}), 400

        logger.info(f"🌍 Target language received: '{target_lang}' for product ID: '{product_id}'")
        logger.info(f"🛠️ Fields to translate: {fields}")

        url_get = (
            f"https://{SHOPIFY_STORE_URL}/admin/api/2023-04/products/{product_id}.json"
            f"?fields=id,title,body_html,tags,handle,options,images"
        )
        resp = shopify_request("GET", url_get)
        if resp.status_code != 200:
            return jsonify({"error": f"Failed to fetch product {product_id}"}), 500

        product_data = resp.json().get("product", {})
        if not product_data:
            return jsonify({"error": "Product not found"}), 404

        updated_data = {}

        # --- TITLE ---
        if "title" in fields:
            chosen_method = methods.get("title", "google")

            # Use specific translation function for title
            if chosen_method == "chatgpt":
                title = chatgpt_translate_title(
                    product_data.get("title", ""),
                    custom_prompt=prompt_title,
                    target_language=target_lang
                )
            else:
                title = apply_translation_method(
                    original_text=product_data.get("title", ""),
                    method=chosen_method,
                    custom_prompt=prompt_title,
                    source_lang=source_lang,
                    target_lang=target_lang
                )

            # 🔥 Function to clean and fix abrupt cuts
            def clean_title_output(title):
                """
                Cleans and ensures the title is complete, structured, and not cut off.
                """
                title = title.strip().strip('"').strip("'").rstrip(",").rstrip(".")  # Remove unnecessary symbols

                # 🚀 If the title ends with an incomplete phrase, attempt to fix
                incomplete_endings = ("et", "à", "de", "avec", "pour", "en", "sur", "dans")
                if title.split()[-1].lower() in incomplete_endings:
                    title += "..."  # Add an ellipsis to avoid awkward cut-offs

                return title

            title = clean_title_output(title)

            # ✅ Ensure the title follows token & character limits
            title_tokens = title.split()
            if len(title_tokens) > 25:
                title = " ".join(title_tokens[:25])  # Trim to 25 tokens

            # ✅ Ensure "[Brand Name] | [Product Name]" format is respected
            if "|" in title:
                parts = title.split("|")
                brand_name = parts[0].strip()
                product_name_words = parts[1].strip().split()

                # 🚀 Ensure product name is max 5 words
                if len(product_name_words) > 5:
                    trimmed_product_name = " ".join(product_name_words[:5])
                    title = f"{brand_name} | {trimmed_product_name}"

            # ✅ Ensure title does NOT exceed 255 characters & prevent abrupt cuts
            if len(title) > 255:
                title = title[:255].rsplit(" ", 1)[0]  # Cut at last word boundary

            updated_data["title"] = title  # Store cleaned title

        # --- DESCRIPTION (body_html) ---
        if "body_html" in fields:
            chosen_method = methods.get("body_html", "google")
            original_html = product_data.get("body_html", "") or ""

            new_desc = apply_translation_method(
                original_text=original_html,
                method=chosen_method,
                custom_prompt=prompt_desc,
                source_lang=source_lang,
                target_lang=target_lang,
                product_title=product_data.get("title", "")  # clearly pass product title!
            )

            new_desc = post_process_description(
                original_html=original_html,
                new_html=new_desc,
                method=chosen_method,
                product_data=product_data,
                target_lang=target_lang  # clearly pass target_lang!
            )
            updated_data["body_html"] = new_desc

        # --- TAGS ---
        if "tags" in fields:
            logging.info("🚀 Translating product tags...")
            chosen_method = methods.get("tags", "google")
            original_tags = product_data.get("tags", "")
            new_tags = apply_translation_method(
                original_text=original_tags,
                method=chosen_method,
                custom_prompt=prompt_tags,
                source_lang=source_lang,
                target_lang=target_lang
            )
            updated_data["tags"] = new_tags

        # --- HANDLE (SLUG) ---
        if "handle" in fields:
            logging.info("🚀 Translating product handle...")
            chosen_method = methods.get("handle", "google")
            original_handle = product_data.get("handle", "")
            new_handle = apply_translation_method(
                original_text=original_handle,
                method=chosen_method,
                custom_prompt=prompt_handle,
                source_lang=source_lang,
                target_lang=target_lang
            )
            updated_data["handle"] = slugify(new_handle)

       # --- VARIANT OPTIONS (✅ Fix: Capture Translated Variants) ---
        if "variant_options" in fields:
            logging.info("🚀 Translating variant options for product...")

            # Fetch product options
            product_gid = f"gid://shopify/Product/{product_id}"  # ←✅ This fixes your error
            options = get_product_option_values(product_gid)

            translated_variant_options = []

            if options:
                for option in options:
                    translation_method = data.get("translation_method")

                    # ✅ Ensure a default translation method (if missing)
                    if not translation_method or not isinstance(translation_method, str):
                        logging.warning("⚠️ No translation method provided! Falling back to user default.")
                        translation_method = "google"  # Default to ChatGPT (Change if needed)

                    translation_method = translation_method.strip().lower()

                    # ✅ Allowed methods
                    VALID_METHODS = {"deepl", "chatgpt", "google"}

                    if translation_method not in VALID_METHODS:
                        logging.error(f"❌ Invalid translation method! Received: '{translation_method}'")
                        return jsonify({"error": "Invalid translation method. Please select Deepl, ChatGPT, or Google."}), 400


                    update_product_option_values(
                    product_gid,
                    option,
                    target_lang,
                    source_language=source_lang,  # ✅ Ensure it's passed as a keyword argument
                    translation_method=translation_method  # ✅ Also pass translation method correctly
                )



                    translated_variant_options.append({
                        "id": option["id"],
                        "name": option["name"],
                        "translated_values": [val["name"] for val in option["optionValues"]]
                    })

            # Store in updated_data to include in the response
            updated_data["translated_options"] = translated_variant_options if translated_variant_options else []

        logging.info("✅ Translation process complete!")

        return jsonify({
            "success": True,
            "product_id": product_id,
            "translated_title": updated_data.get("title", ""),
            "translated_description": updated_data.get("body_html", ""),
            "translated_tags": updated_data.get("tags", ""),
            "translated_handle": updated_data.get("handle", ""),
            "translated_options": updated_data.get("translated_options", []),  # ✅ Ensure it's returned
        })


    except Exception as e:
        logger.exception(e)
        return jsonify({"error": str(e)}), 500

# --- Translate Entire Collection (ChatGPT example) ---
@app.route("/translate_collection_fields", methods=["POST"])
def translate_collection_fields():
    """
    Translate selected fields for all products in a collection using ChatGPT.
    (No google/deepl logic here—could be expanded if needed.)
    """
    try:
        data = request.json
        collection_id = data.get("collection_id")
        fields_to_translate = data.get("fields", [])
        user_prompt = data.get("prompt", "Translate these fields")

        if not collection_id:
            return jsonify({"error": "No collection_id provided"}), 400

        url = (
            f"https://{SHOPIFY_STORE_URL}/admin/api/2023-04/products.json"
            f"?collection_id={collection_id}&fields=id,title,body_html,tags,product_type,variants"
        )
        resp = shopify_request("GET", url)
        if resp.status_code != 200:
            return jsonify({"error": "Failed to load products from Shopify"}), 500

        products = resp.json().get("products", [])
        for product in products:
            updates = {}
            if "title" in fields_to_translate:
                updates["title"] = chatgpt_translate(product.get("title", ""), user_prompt)
            if "body_html" in fields_to_translate:
                orig_html = product.get("body_html", "")
                new_desc = chatgpt_translate(orig_html, user_prompt)
                new_desc = post_process_description(orig_html, new_desc, "chatgpt")
                updates["body_html"] = new_desc
            if "tags" in fields_to_translate:
                updates["tags"] = chatgpt_translate(product.get("tags", ""), user_prompt)
            if "product_type" in fields_to_translate:
                updates["product_type"] = chatgpt_translate(product.get("product_type", ""), user_prompt)
            # handle variant options if needed

            if updates:
                payload = {"product": {"id": product["id"], **updates}}
                update_resp = shopify_request("PUT", f"https://{SHOPIFY_STORE_URL}/admin/api/2023-04/products/{product['id']}.json",
                                              json=payload)
                if update_resp.status_code not in (200, 201):
                    logger.error(f"Error updating product {product['id']}: {update_resp.text}")

        return jsonify({"success": True, "message": "Translation complete for selected fields."})
    except Exception as e:
        logger.exception(e)
        return jsonify({"error": str(e)}), 500

# --- Translate Selected Fields on Single Product (ChatGPT only) ---
@app.route("/translate_selected_fields", methods=["POST"])
def translate_selected_fields():
    """
    Translate selected fields for a single product using ChatGPT (example).
    You can modify if you want google/deepl, etc.
    """
    try:
        data = request.json
        product_id = data.get("product_id")
        fields_to_translate = data.get("fields", [])
        user_prompt = data.get("prompt", "Please translate the following fields")

        if not product_id:
            return jsonify({"error": "No product ID provided"}), 400

        url_get = f"https://{SHOPIFY_STORE_URL}/admin/api/2023-04/products/{product_id}.json"
        resp = shopify_request("GET", url_get)
        if resp.status_code != 200:
            return jsonify({"error": "Failed to fetch product from Shopify"}), 500

        product_data = resp.json().get("product", {})
        if not product_data:
            return jsonify({"error": "Product not found"}), 404

        updates = {}
        if "title" in fields_to_translate:
            updates["title"] = chatgpt_translate(product_data.get("title", ""), user_prompt)
        if "body_html" in fields_to_translate:
            orig_html = product_data.get("body_html", "")
            new_desc = chatgpt_translate(orig_html, user_prompt)
            # re-inject images if ChatGPT stripped them
            new_desc = post_process_description(orig_html, new_desc, "chatgpt")
            updates["body_html"] = new_desc
        if "tags" in fields_to_translate:
            updates["tags"] = chatgpt_translate(product_data.get("tags", ""), user_prompt)
        if "product_type" in fields_to_translate:
            updates["product_type"] = chatgpt_translate(product_data.get("product_type", ""), user_prompt)
        if "handle" in fields_to_translate:
            new_handle = chatgpt_translate(product_data.get("handle", ""), user_prompt)
            updates["handle"] = slugify(new_handle)

        if updates:
            url_put = f"https://{SHOPIFY_STORE_URL}/admin/api/2023-04/products/{product_id}.json"
            payload = {"product": {"id": product_id, **updates}}
            update_resp = shopify_request("PUT", url_put, json=payload)
            if update_resp.status_code not in (200, 201):
                return jsonify({"error": "Failed to update product with translations"}), 500

        return jsonify({"success": True, "message": "Selected fields translated successfully!"})
    except Exception as e:
        logger.exception(e)
        return jsonify({"error": str(e)}), 500

# --- Start AI Translation Process (Bulk) ---
@app.route("/start_translation", methods=["POST"])
def start_translation():
    """
    Start the bulk translation process for multiple variants and product IDs.
    Updates the local database with status='Pending Approval'.
    Supports ChatGPT translation.
    """
    data = request.json
    product_ids = data.get("product_ids", [])
    variants = data.get("variants", [])
    target_language = data.get("target_language", "fr")
    prompt = data.get("prompt", "")

    if not product_ids and not variants:
        return jsonify({"error": "No products or variants selected"}), 400

    try:
        success_message = []

        if product_ids:
            success, message = process_all_products(product_ids, target_language)
            if success:
                success_message.append(message)
            else:
                return jsonify({"error": message}), 500

        if variants:
            with sqlite3.connect(DATABASE) as conn:
                cursor = conn.cursor()
                for variant_id in variants:
                    translated_text = chatgpt_translate(prompt)
                    cursor.execute("""
                        UPDATE translations 
                        SET translated_description=?, status='Pending Approval' 
                        WHERE product_id=?
                    """, (translated_text, variant_id))
                conn.commit()
            success_message.append(f"Translation started for {len(variants)} variants!")

        return jsonify({"success": True, "message": " ".join(success_message)})
    except Exception as e:
        logger.exception(e)
        return jsonify({"error": str(e)}), 500

# --- Approve Translations ---
@app.route("/approve_translations", methods=["POST"])
def approve_translations():
    """
    Approve multiple translations and update them in Shopify.
    """
    data = request.json
    product_ids = data.get("product_ids", [])
    if not product_ids:
        return jsonify({"error": "No products selected for approval"}), 400

    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        for pid in product_ids:
            cursor.execute("""
                SELECT translated_title, translated_description 
                FROM translations 
                WHERE product_id=?
            """, (pid,))
            product = cursor.fetchone()
            if product:
                translated_title, translated_description = product
                update_product_translation(pid, translated_title, translated_description)
                cursor.execute("UPDATE translations SET status='Approved' WHERE product_id=?", (pid,))
                log_translation(pid, translated_title, translated_description, "Approved")
        conn.commit()

    return jsonify({"success": True, "message": f"Approved {len(product_ids)} translations!"})

# --- Reject Translation ---
@app.route("/reject_translation", methods=["POST"])
def reject_translation():
    """
    Reject a translation and allow the user to modify the prompt before reprocessing.
    """
    data = request.json
    product_id = data.get("product_id")
    new_prompt = data.get("new_prompt", "")

    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT product_title, product_description 
            FROM translations 
            WHERE product_id=?
        """, (product_id,))
        product = cursor.fetchone()
        if not product:
            return jsonify({"success": False, "message": "Product not found."})

        product_title, product_description = product
        new_ai_prompt = f"""
        Translate the following product description into the target language with the user's modifications.
        Product Title: {product_title}
        Description: {product_description}
        User's Custom Instruction: {new_prompt}
        """
        new_translated_description = chatgpt_translate(new_ai_prompt, new_prompt)
        cursor.execute("""
            UPDATE translations 
            SET translated_description=?, status='Pending Review'
            WHERE product_id=?
        """, (new_translated_description, product_id))
        conn.commit()

    return jsonify({"success": True, "message": "Translation rejected and reprocessed with new prompt."})

# --- Optimize Translations ---
@app.route("/optimize_translations", methods=["POST"])
def optimize_translations():
    """
    Analyze past translation performance and suggest improvements using ChatGPT.
    """
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT product_id, product_title, translated_title, product_description, translated_description, status 
            FROM translations 
            WHERE status='Approved'
        """)
        records = cursor.fetchall()

    if not records:
        return jsonify({"error": "No approved translations found to analyze"}), 404

    optimization_prompt = "Analyze the past translation performance and suggest improvements:\n\n"
    for record in records[:5]:
        (pid, orig_title, trans_title, orig_desc, trans_desc, status) = record
        optimization_prompt += f"""
        Product ID: {pid}
        Original Title: {orig_title}
        Translated Title: {trans_title}
        Original Description: {orig_desc}
        Translated Description: {trans_desc}
        Status: {status}
        """
    optimization_prompt += """
    Based on this data, refine and suggest an optimized translation prompt 
    that improves future translations for maximum conversion and clarity.
    """
    improved_prompt = chatgpt_translate(optimization_prompt, "Provide detailed suggestions for improvements.")
    return jsonify({"success": True, "optimized_prompt": improved_prompt})

# --- Utility: Log Translation ---
def log_translation(product_id, title, description, status):
    """Optional: Log translation events (prints to console)."""
    logger.info(f"Translation log - Product ID: {product_id}, Status: {status}")

@app.route("/upload_google_sheet_text", methods=["POST"])
def upload_google_sheet_text():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    image_column = request.form.get("image_column", "A")
    starting_row = int(request.form.get("starting_row", 2))
    convert_str = request.form.get("convert_to_text", "false").lower()
    convert_bool = (convert_str == "true")

    result = process_google_sheet(
        file=file,
        image_column=image_column,
        starting_row=starting_row,
        pre_process=True,
        convert_to_text=convert_bool
    )
    return jsonify(result)



# ------------------------------ #
# Main Entry Point
# ------------------------------ #
if __name__ == "__main__":
    logger.info("Starting Flask app in %s", os.getcwd())
    app.run(debug=True, port=5003)
