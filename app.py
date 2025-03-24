import os
import sys
from dotenv import load_dotenv
import traceback
from variants_utils import clean_translated_text
load_dotenv()

print("SHOPIFY_STORE_URL:", os.getenv("SHOPIFY_STORE_URL"))
print("SHOPIFY_API_KEY:", os.getenv("SHOPIFY_API_KEY"))

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
from variants_utils import get_product_option_values, update_product_option_values
from bs4 import BeautifulSoup  # Add this here
from variants_utils import get_predefined_translation  # ✅ Import the function

def sanitize_shopify_product(product):
    # Clean options
    for option in product.get("options", []):
        option["name"] = clean_translated_text(option["name"])
        option["values"] = [clean_translated_text(v) for v in option.get("values", [])]

    # Clean variants
    for variant in product.get("variants", []):
        for key in ["option1", "option2", "option3"]:
            if key in variant:
                variant[key] = clean_translated_text(variant[key])

    return product

# Define clean_html function here
def clean_html(html):
    """
    Fixes broken HTML by parsing and reformatting using BeautifulSoup.
    """
    soup = BeautifulSoup(html, "html.parser")
    return str(soup)

# If your modules are located one directory up
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))



# Custom modules
from shopify_api import fetch_product_by_id, fetch_products_by_collection, update_product_translation
from translation import chatgpt_translate, google_translate, deepl_translate, chatgpt_translate_title  # Extend as needed
from google_sheets import process_google_sheet

# ✅ Global variable to track translation progress
translation_progress = {
    "total": 0,
    "completed": 0
}


# ------------------------------ #
# Load Environment Variables
# ------------------------------ #

DEEPL_API_KEY = os.getenv("DEEPL_API_KEY")
GOOGLE_TRANSLATE_API_KEY = os.getenv("GOOGLE_TRANSLATE_API_KEY")  # If needed for advanced Google Translate API
CHATGPT_API_KEY = os.getenv("CHATGPT_API_KEY")
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

@app.route('/shopify-test')
def test_shopify_api():
    return jsonify({"message": "API is running on Render!"})
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
    Post-process a translated product description:
    - ChatGPT: Full formatting (title, intro, bullet points, images, CTA).
    - Other methods: Only inject two images (first after introduction, second after bullet points).
    """
    try:
        logging.debug("[post_process_description] Starting post-processing.")

        # Validate product images
        images = product_data.get("images", []) if product_data else []
        image1_url = images[0].get("src") if len(images) > 0 else ""
        image2_url = images[1].get("src") if len(images) > 1 else ""


        if method.lower() == "chatgpt":
            # Full formatting for ChatGPT method
            parsed = _parse_chatgpt_description(new_html)
            labels = _get_localized_labels(target_lang)
            bullet_html = _build_bullet_points(parsed.get('features', []))

            final_html_parts = [
                '<div style="text-align:center; margin:0 auto; max-width:800px;">',
                f'<h3 style="font-weight:bold;">{parsed.get("title", "")}</h3>',
                f'<p>{parsed.get("introduction", "")}</p>',
            ]

            # First image
            if image1_url:
                final_html_parts.append(
                    f"<div style='margin:1em 0;'><img src='{image1_url}' style='width:480px; max-width:100%;' loading='lazy'/></div>"
                )

            # Advantages and bullets
            final_html_parts += [
                f'<h3 style="font-weight:bold;">{labels.get("advantages", "Product Advantages")}</h3>',
                '<div style="display: flex; justify-content: center;">',
                '<ul style="list-style-position: inside; text-align: center;">',
                bullet_html,
                '</ul></div>',
            ]

            # Second image
            if image2_url:
                final_html_parts.append(
                    f"<div style='margin:2em 0;'><img src='{image2_url}' style='width:480px; max-width:100%;' loading='lazy'/></div>"
                )

            # CTA
            cta_html = parsed.get('cta') or labels.get('cta', 'Check it out now!')
            final_html_parts.append(
                f'<h4 style="font-weight:bold; margin:1.5em 0; font-size:1.2em;">{cta_html}</h4>'
            )

            final_html_parts.append('</div>')

            logging.info("✅ [post_process_description] Successfully constructed ChatGPT-formatted HTML.")
            return "\n".join(final_html_parts).strip()

        else:
            logging.info(f"[post_process_description] Injecting images into HTML for method '{method}'.")

            # Parse and clean HTML
            soup = BeautifulSoup(new_html, "html.parser")

            # Step 1: Remove all existing images
            for img in soup.find_all('img'):
                img.decompose()
            logging.info("🧼 Removed all existing <img> tags.")

            # Step 2: Insert first image after first <p>
            paragraphs = soup.find_all('p')
            if paragraphs and image1_url:
                first_para = paragraphs[0]
                img_div_1 = soup.new_tag('div', style='text-align:center; margin:1em 0;')
                img_1 = soup.new_tag('img', src=image1_url, style='width:480px; max-width:100%;', loading='lazy')
                img_div_1.append(img_1)
                first_para.insert_after(img_div_1)
                logging.info("✅ Inserted first image after first <p> paragraph.")

            # Step 3: Insert second image before last block tag inside main container
            if image2_url:
                # Find the outermost main content container
                main_container = soup.find('div', style=lambda v: v and 'max-width:800px' in v)
                if not main_container:
                    main_container = soup  # fallback to whole doc

                # Find the last text block tag inside this container
                last_block = None
                for tag in ['h4', 'h3', 'h2', 'h1', 'p', 'div']:
                    blocks = main_container.find_all(tag)
                    if blocks:
                        last_block = blocks[-1]
                        break  # stop at first type found in reverse priority

                # Insert second image before that block
                if last_block:
                    img_div_2 = soup.new_tag('div', style='text-align:center; margin:2em 0;')
                    img_2 = soup.new_tag('img', src=image2_url, style='width:480px; max-width:100%;', loading='lazy')
                    img_div_2.append(img_2)
                    last_block.insert_before(img_div_2)
                    logging.info(f"✅ Inserted second image before <{last_block.name}> inside main container.")
                else:
                    # Fallback: add at end
                    img_div_2 = soup.new_tag('div', style='text-align:center; margin:2em 0;')
                    img_2 = soup.new_tag('img', src=image2_url, style='width:480px; max-width:100%;', loading='lazy')
                    img_div_2.append(img_2)
                    soup.append(img_div_2)
                    logging.warning("⚠️ No final block found — inserted second image at end.")

                        # Fix all layout-divs with Shopify column classes
            for grid_div in soup.find_all('div', class_=lambda x: x and 'grid__item' in x):
                # Remove Shopify column classes (they mess with layout)
                grid_div['class'] = ['grid__item']
                # Apply inline styles to ensure full width & center
                grid_div['style'] = "width:100%; max-width:800px; margin: 0 auto; text-align:center;"
        

            # Final HTML cleanup
            final_inner_html = str(soup)

            # 🛠 Fix rare layout issue (Shopify grid forcing half width)
            final_inner_html = final_inner_html.replace(
                'class="grid__item large--six-twelfths medium--six-twelfths"',
                'class="grid__item" style="width:100%; max-width:800px; margin: 0 auto; text-align:center;"'
            )

            # ✅ Wrap everything in a centered container
            final_wrapped_html = f'<div style="text-align: center; margin: 0 auto; max-width: 800px;">{final_inner_html}</div>'

            logging.info(f"🔥 Final HTML sent to Shopify:\n{final_wrapped_html[:1000]}...")
            return final_wrapped_html.strip()

    except Exception as e:
        logging.exception(f"❌ [post_process_description] Exception occurred: {e}")
        return new_html

def _parse_chatgpt_description(ai_text):
    """
    Extracts title, introduction, bullet features, and CTA
    from text that follows this ChatGPT format:

        Product Title: ...
        Short Introduction: ...
        Product Advantages:
        - ...
        - ...
        Call to Action: ...
    """
    parsed_data = {
        'title': '',
        'introduction': '',
        'features': [],
        'cta': ''
    }

    # Product Title
    match_title = re.search(r"(?i)product title\s*:\s*(.*)", ai_text)
    if match_title:
        parsed_data['title'] = match_title.group(1).strip()

    # Short Introduction
    match_intro = re.search(r"(?i)short introduction\s*:\s*(.*)", ai_text)
    if match_intro:
        parsed_data['introduction'] = match_intro.group(1).strip()

    # Product Advantages: lines that begin with a dash
    features_section = re.search(r"(?is)product advantages\s*:(.*?)(?:call to action:|$)", ai_text)
    if features_section:
        raw_features = features_section.group(1).strip()
        bullet_lines = re.findall(r"-\s*(.+)", raw_features)
        # Filter out "additional feature" placeholders
        parsed_data['features'] = [
            line.strip() for line in bullet_lines
            if line.strip() and not line.lower().startswith("additional feature")
        ]

    # Call to Action
    match_cta = re.search(r"(?i)call to action\s*:\s*(.*)", ai_text)
    if match_cta:
        parsed_data['cta'] = match_cta.group(1).strip()

    return parsed_data


def _get_localized_labels(target_lang):
    """Localizes 'Product Advantages' heading and a fallback CTA."""
    localized_map = {
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
    return localized_map.get(target_lang.lower(), localized_map['en'])


def _build_bullet_points(features):
    """
    Converts an array of feature lines into <li> tags.
    Bold text before ':' or '-', if present.
    """
    bullet_li_list = []
    for line in features:
        # Remove possible "Feature 1:" prefix
        line = re.sub(r'(?i)^Feature \d+:\s*', '', line)
        # Split on first ':' or '-'
        parts = re.split(r'[:\-]', line, 1)
        if len(parts) == 2:
            bold_part, rest_part = parts
            bullet_li_list.append(f"<li><strong>{bold_part.strip()}</strong>: {rest_part.strip()}</li>")
        else:
            bullet_li_list.append(f"<li><strong>{line.strip()}</strong></li>")

    return "".join(bullet_li_list)


def _get_first_two_images(product_data):
    """
    Returns the URLs of the first two images from product_data['images'],
    or empty strings if none exist.
    """
    image1_url = ""
    image2_url = ""
    if product_data and 'images' in product_data:
        imgs = product_data['images']
        if len(imgs) > 0:
            image1_url = imgs[0].get('src', '')
        if len(imgs) > 1:
            image2_url = imgs[1].get('src', '')
    return image1_url, image2_url

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
# ------------------------------ 

def apply_translation_method(
    original_text, 
    method, 
    custom_prompt, 
    source_lang, 
    target_lang, 
    product_title="", 
    field_type=None,
    description=None
):
    logging.info("🔁 [apply_translation_method] START:")
    logging.info(f"   → method: {method}")
    logging.info(f"   → source_lang: {source_lang}")
    logging.info(f"   → target_lang: {target_lang}")
    logging.info(f"   → field_type: {field_type or 'N/A'}")
    logging.info(f"   → description length: {len(description or '')}")

    if not original_text or not method:
        logging.warning("⚠️ Missing original_text or method, returning original.")
        return original_text

    method_lower = method.lower()

    try:
        if method_lower == "chatgpt":
            logging.info("🤖 Using ChatGPT — calling once for full HTML...")
            return chatgpt_translate(original_text, custom_prompt, target_lang, field_type, product_title)

        # For Google or DeepL, do language detection if needed
        if method_lower in ["google", "deepl"] and source_lang.lower() == "auto" and description:
            try:
                from langdetect import detect
                detected = detect(description)
                source_lang = detected
                logging.info(f"🌍 Detected source_lang: {source_lang}")
            except Exception as e:
                logging.warning(f"⚠️ Language detection failed: {e}")
        
        # Parse HTML & translate text nodes individually
        soup = BeautifulSoup(original_text, "html.parser")
        text_nodes = soup.find_all(string=True)
        logging.info(f"📄 Found {len(text_nodes)} text nodes inside HTML.")

        # Clean up empty divs
        empty_divs = 0
        for div in soup.find_all('div'):
            if not div.text.strip() and not div.find(['img', 'ul', 'p', 'h1', 'h2', 'h3']):
                div.decompose()
                empty_divs += 1
        logging.info(f"🧼 Removed {empty_divs} empty <div> elements.")

        translated_parts = {}

        for i, node in enumerate(text_nodes):
            stripped = node.strip()
            if not stripped:
                translated_parts[i] = node
                continue

            if method_lower == "google":
                translated = google_translate(stripped, source_lang, target_lang)
            elif method_lower == "deepl":
                translated = deepl_translate(stripped, source_lang, target_lang)
            else:
                logging.warning(f"⚠️ Unknown method '{method}' — skipping.")
                translated = stripped

            translated_parts[i] = translated
            logging.debug(f"🔤 Node {i}: '{stripped[:40]}' → '{translated[:40]}'")

        # Replace text nodes with translated versions
        for i, new_text in translated_parts.items():
            text_nodes[i].replace_with(new_text)

        result_html = str(soup)
        logging.info("✅ HTML translation complete with structure preserved.")
        return result_html

    except Exception as e:
        logging.error(f"❌ Translation failed: {e}")
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
    Returns collection name, product count, and product list.
    """
    try:
        data = request.json
        collection_id = data.get("collection_id")
        if not collection_id:
            return jsonify({"error": "No collection selected"}), 400

        # We fetch "images" too, in case we want them for post-processing
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

        return jsonify({
            "success": True,
            "collection_name": data.get("collection_name", "Unknown Collection"),
            "product_count": len(products),
            "products": products
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
        logging.info(f"🔍 Incoming Translation Request: {data}")  # ✅ Add this for debugging

        fields = data.get("fields", [])
        methods = data.get("field_methods", {})

        logging.info(f"📌 Fields to translate: {fields}")
        logging.info(f"📌 Methods chosen: {methods}")

        prompt_title = data.get("prompt_title", "")
        prompt_desc = data.get("prompt_desc", "")
        prompt_tags = data.get("prompt_tags", "")
        prompt_handle = data.get("prompt_handle", "")
        prompt_variants = data.get("prompt_variants", "")
    
        source_lang = data.get("source_language", "auto")
        target_lang = data.get("target_language", "de")

        if not product_id:
            return jsonify({"error": "No product ID provided"}), 400

        BASE_URL = SHOPIFY_STORE_URL if SHOPIFY_STORE_URL.startswith("https://") else f"https://{SHOPIFY_STORE_URL}"

        url_get = f"{BASE_URL}/admin/api/2023-04/products/{product_id}.json"
        logging.info(f"📡 Fetching product from Shopify: {url_get}") 

        resp = shopify_request("GET", url_get)
        # ✅ Debug Logging
        logger.info(f"🔍 Shopify API Response Code: {resp.status_code}")
        logger.info(f"🔍 Shopify API Response Body: {resp.text}")

        if resp.status_code != 200:
            return jsonify({"error": f"Failed to fetch product {product_id}"}), 500

        product_data = resp.json().get("product", {})
        if not product_data:
            return jsonify({"error": "Product not found"}), 404
        
        logging.info(f"✅ Fetched product successfully: {json.dumps(product_data, indent=2)[:500]}...")

        updated_data = {}

        # --- TITLE ---
        if "title" in fields:
            chosen_method = methods.get("title", "google")
            logging.info("🚀 [chatgpt_translate] Sending request to ChatGPT for description...- translate test product")

            # If using ChatGPT for the title:
            if chosen_method == "chatgpt":
                title = chatgpt_translate_title(
                    product_data.get("title", ""),
                    custom_prompt=prompt_title,
                    target_language=target_lang
                )
            else:
                # Pass body_html as `description`:
                title = apply_translation_method(
                    original_text=product_data.get("title", ""),
                    method=chosen_method,
                    custom_prompt=prompt_title,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    description=product_data.get("body_html", "")  # <-- ADDED
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
            logging.info(f"📝 Translating Description using: {chosen_method}")
            original_html = product_data.get("body_html", "") or ""

            logger.info("🧪 Calling apply_transalation_method")

            new_desc = apply_translation_method(
                original_text=original_html,
                method=chosen_method,
                custom_prompt=prompt_desc,
                source_lang=source_lang,
                target_lang=target_lang,
                product_title=product_data.get("title", "")  # clearly pass product title!
            )
            logger.info(f"🔎 Description returned from apply_translation_method:\n{new_desc[:500]}")
            logger.info("🧪 Calling post_process_description()")

            new_desc = post_process_description(
                original_html=original_html,
                new_html=new_desc,
                method=chosen_method,
                product_data=product_data,
                target_lang=target_lang  # clearly pass target_lang!
            )
            logger.info(f"🎯 Final processed HTML:\n{new_desc[:500]}")

            logging.info(f"🔥 IMAGE URL CHECK: Image1='{product_data['images'][0].get('src', '')}', Image2='{product_data['images'][1].get('src', '')}'")
            logging.info(f"🔥 Final HTML sent to Shopify:\n{new_desc}")

            
            updated_data["body_html"] = new_desc

            logging.info(f"📤 Sending updated product data to Shopify: {json.dumps(updated_data, indent=2)}")

        # --- TAGS ---
        if "tags" in fields:
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

        # --- HANDLE ---
        if "handle" in fields:
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

        # --- VARIANT OPTIONS ---
        if "variant_options" in fields:
            chosen_method = methods.get("variant_options", "google")
            new_options = []

            for opt in product_data.get("options", []):
                original_option_name = opt.get("name", "")
                translated_name = apply_translation_method(
                    original_text=original_option_name,
                    method=chosen_method,
                    custom_prompt=prompt_variants or "",  # ✅ Prevent NoneType error
                    source_lang=source_lang,
                    target_lang=target_lang
                )
                logging.info(f"✅ Translated Option Name: {original_option_name} → {translated_name}")

                new_values = []
                for value in opt.get("values", []):
                    logging.info(f"🔄 Translating Option Value: {value}")  # ✅ Log before translation

                    # ✅ Check if predefined translation exists
                    predefined_translation = get_predefined_translation(value, target_lang)
                    if predefined_translation:
                        logging.info(f"✅ Using predefined translation: {value} → {predefined_translation}")
                        translated_value = predefined_translation
                    else:
                        # ✅ Skip translation if the value is a known size (S, M, L, XL, XXL, etc.)
                        KNOWN_SIZES = {"XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL", "XXXXL", "2XL", "3XL", "4XL"}
                        if value.upper() in KNOWN_SIZES:
                            logging.info(f"🔒 Skipping translation for universal size '{value}'")
                            translated_value = value  # ✅ Keep the original size
                        else:
                            # ✅ Otherwise, translate using API
                            translated_value = apply_translation_method(
                                original_text=value,
                                method=chosen_method,
                                custom_prompt=prompt_variants or "",
                                source_lang=source_lang,
                                target_lang=target_lang
                            )
                    
                    logging.info(f"✅ Translated Option Value: {value} → {translated_value}")  # ✅ Log after translation
                    new_values.append(translated_value)

                new_options.append({"name": translated_name, "values": new_values})  # ✅ Assign translated values

            # ✅ Update Shopify product structure correctly
            updated_data["options"] = new_options

        # If no fields were translated, return an error
        if not updated_data:
            logging.error("❌ No fields selected or no translations applied.")
            return jsonify({"error": "No fields selected or no translations applied."}), 400

        # ✅ Log the translated data before sending it to Shopify
        logging.info(f"📤 Sending updated product data to Shopify: {json.dumps(updated_data, indent=2)}")

        # Create a mapping of translated options
        translated_options_map = {}
        for option in updated_data.get("options", []):  
            original_values = product_data["options"][updated_data["options"].index(option)]["values"]
            translated_options_map.update(dict(zip(original_values, option["values"])))  # Map original -> translated
        
        # Update variants to match translated option values
        translated_variants = []
        for variant in product_data.get("variants", []):
            translated_variant = {
                "id": variant["id"],
                "option1": translated_options_map.get(variant.get("option1"), variant.get("option1")),
                "option2": translated_options_map.get(variant.get("option2"), variant.get("option2")),
                "option3": translated_options_map.get(variant.get("option3"), variant.get("option3")),
            }
            translated_variants.append(translated_variant)



        # ✅ Ensure put_payload is always assigned before using it
        try:
            logging.info("🧪 Preparing Shopify update payload...")
            logging.info(f"🧾 Translated Fields: {json.dumps(updated_data, indent=2)[:1000]}")
            put_payload = {
    "product": {
        "id": product_id,
        **updated_data,
        "variants": translated_variants  # ✅ Ensure variants reflect translated options
    }
}
            put_payload["product"] = sanitize_shopify_product(put_payload["product"])

        # ✅ Log final payload before sending
            logging.info(f"📦 Final Shopify PUT Payload:\n{json.dumps(put_payload, indent=2)[:1000]}")
            url_put = f"https://{SHOPIFY_STORE_URL}/admin/api/2023-04/products/{product_id}.json"
            update_resp = shopify_request("PUT", url_put, json=put_payload)

            logging.info(f"📥 Shopify Response Status: {update_resp.status_code}")
            logging.info(f"📥 Shopify Response Content: {update_resp.text}")

            # ✅ Log Shopify's response
            if update_resp.status_code not in (200, 201):
                logging.error(f"❌ Failed to update product! Shopify Response: {update_resp.text}")
                return jsonify({"error": "Failed to update product", "details": update_resp.text}), 500
            
                    # 🔍 Debugging: Log the exact payload before sending it to Shopify
            logging.info(f"📤 Sending Shopify PUT Request: {json.dumps(put_payload, indent=2)}")

            logging.info(f"✅ Successfully updated product in Shopify! Response: {update_resp.text}")

            return jsonify({
                "success": True,
                "product_id": product_id,
                "translated_title": updated_data.get("title", ""),
                "translated_description": updated_data.get("body_html", ""),
                "translated_tags": updated_data.get("tags", ""),
                "translated_handle": updated_data.get("handle", ""),
                "translated_options": updated_data.get("options", []),
            })

        except Exception as e:
            logging.exception(f"❌ Exception while updating Shopify: {str(e)}")
            return jsonify({"error": str(e)}), 500

    except Exception as e:
        logger.exception(e)
        return jsonify({"error": str(e)}), 500



# --- Translate Entire Collection (ChatGPT example) ---
@app.route("/translate_collection_fields", methods=["POST"])
def translate_collection_fields():
    print("🧪 translate_collection_fields HIT!")

    """
    Translate selected fields for all products in a collection using selected methods.
    Supports ChatGPT, Google Translate, and DeepL.
    Tracks translation progress.
    """
    try:
        data = request.json
        collection_id = data.get("collection_id")
        fields_to_translate = data.get("fields", [])
        field_methods = data.get("field_methods", {})  # e.g. {"title": "chatgpt", "body_html": "google"}
        target_lang = data.get("target_language", "de")  # default to German

        if not collection_id:
            return jsonify({"error": "No collection_id provided"}), 400
        
        prompt_title = data.get("prompt_title", "")
        prompt_desc = data.get("prompt_desc", "")

    
        url = (
            f"https://{SHOPIFY_STORE_URL}/admin/api/2023-04/products.json"
            f"?collection_id={collection_id}&fields=id,title,body_html,tags,product_type,variants,images"
        )
        resp = shopify_request("GET", url)
        if resp.status_code != 200:
            return jsonify({"error": "Failed to load products from Shopify"}), 500

        products = resp.json().get("products", [])

        # ✅ Start tracking progress
        translation_progress["total"] = len(products)
        translation_progress["completed"] = 0

        for idx, product in enumerate(products):
            logger.info(f"🔁 Translating product {idx+1}/{len(products)}: {product.get('title', '')}")
            updates = {}

            for field in fields_to_translate:
                method = field_methods.get(field, "chatgpt")
                original_value = product.get(field, "")

                if not original_value:
                    continue
                logging.info("🚀 [chatgpt_translate] Sending request to ChatGPT for description... -translate collection fields")
        
                if method == "chatgpt":
                    if field == "title":
                        translated = chatgpt_translate_title(original_value, custom_prompt=prompt_title, target_language=target_lang)
                    else:
                        translated = chatgpt_translate(original_value, custom_prompt=prompt_desc, target_language=target_lang)
                elif method == "google":
                    translated = google_translate(original_value, target_language=target_lang)
                elif method == "deepl":
                    translated = deepl_translate(original_value, target_language=target_lang)
                else:
                    continue

                if field == "body_html":
                    translated = post_process_description(original_value, translated, method, product, target_lang)

                updates[field] = translated
            logger.info(f"✅ Finished translating product {product.get('id')}")
            if updates:
                payload = {"product": {"id": product["id"], **updates}}
                update_url = f"https://{SHOPIFY_STORE_URL}/admin/api/2023-04/products/{product['id']}.json"
                update_resp = shopify_request("PUT", update_url, json=payload)

                if update_resp.status_code in (200, 201):
                    translation_progress["completed"] = idx + 1  # ✅ Only increment if update was successful
                else:
                    logger.error(f"❌ Error updating product {product['id']}: {update_resp.text}")

        return jsonify({"success": True, "message": "Translation complete for selected fields."})

    except Exception as e:
        logger.exception("❌ Error in translate_collection_fields:")
        traceback.print_exc()
        return jsonify({"error": f"💥 Error occurred: {str(e)}"}), 500


# --- Translate Selected Fields on Single Product (ChatGPT only) ---
@app.route("/translate_selected_fields", methods=["POST"])
def translate_selected_fields():
    """
    Translate selected fields for a single product using ChatGPT, Google, or DeepL.
    """
    try:
        data = request.json
        product_id = data.get("product_id")
        fields_to_translate = data.get("fields", [])
        field_methods = data.get("field_methods", {})  # e.g. {"title": "chatgpt", "body_html": "google"}
        target_lang = data.get("target_language", "de")  # Default language
        user_prompt = data.get("prompt", "Translate the following")

        if not product_id:
            return jsonify({"error": "No product ID provided"}), 400

        # Fetch product from Shopify
        url_get = f"https://{SHOPIFY_STORE_URL}/admin/api/2023-04/products/{product_id}.json"
        resp = shopify_request("GET", url_get)
        if resp.status_code != 200:
            return jsonify({"error": "Failed to fetch product from Shopify"}), 500

        product_data = resp.json().get("product", {})
        if not product_data:
            return jsonify({"error": "Product not found"}), 404

        updates = {}

        for field in fields_to_translate:
            method = field_methods.get(field, "chatgpt")
            original_value = product_data.get(field, "")

            if not original_value:
                continue
            logging.info("🚀 [chatgpt_translate] Sending request to ChatGPT for description...- translate selected fields")
    
            # Translation logic
            if method == "chatgpt":
                translated = chatgpt_translate(original_value, user_prompt)
            elif method == "google":
                translated = google_translate(original_value, target_lang=target_lang)
            elif method == "deepl":
                translated = deepl_translate(original_value, target_lang=target_lang)
            else:
                continue

            # Post-process for HTML field
            if field == "body_html":
                translated = post_process_description(
                    original_value, translated, method, product_data, target_lang
                )

            # Slugify if it's a handle
            if field == "handle":
                translated = slugify(translated)

            updates[field] = translated

        # Update product in Shopify
        if updates:
            url_put = f"https://{SHOPIFY_STORE_URL}/admin/api/2023-04/products/{product_id}.json"
            payload = {"product": {"id": product_id, **updates}}
            update_resp = shopify_request("PUT", url_put, json=payload)
            if update_resp.status_code not in (200, 201):
                return jsonify({"error": "Failed to update product with translations"}), 500

        return jsonify({"success": True, "message": "Selected fields translated successfully!"})

    except Exception as e:
        logger.exception("❌ Error in translate_selected_fields:")
        return jsonify({"error": str(e)}), 500

# --- Start AI Translation Process (Bulk) ---
@app.route("/start_translation", methods=["POST"])
def start_translation():
    """
    Start the bulk translation process for multiple variants.
    Updates the local database with status='Pending Approval'.
    Here we only do chatgpt_translate, but you could adapt.
    """
    data = request.json
    variants = data.get("variants", [])
    prompt = data.get("prompt", "")

    if not variants:
        return jsonify({"error": "No variants selected"}), 400

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

    return jsonify({"success": True, "message": "Translation started successfully!"})

# --- Approve Translations ---
@app.route("/approve_translations", methods=["POST"])
def approve_translations():
    """
    Approve multiple translations and update them in Shopify.
    Applies HTML post-processing to translated descriptions.
    """
    data = request.json
    product_ids = data.get("product_ids", [])
    target_lang = data.get("target_language", "de")

    if not product_ids:
        return jsonify({"error": "No products selected for approval"}), 400

    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        for pid in product_ids:
            # Fetch translations
            cursor.execute("""
                SELECT translated_title, translated_description 
                FROM translations 
                WHERE product_id=?
            """, (pid,))
            product = cursor.fetchone()

            if product:
                translated_title, translated_description = product

                # Fetch original product for full image data (needed for image injection)
                url_get = f"https://{SHOPIFY_STORE_URL}/admin/api/2023-04/products/{pid}.json"
                resp = shopify_request("GET", url_get)
                if resp.status_code != 200:
                    continue

                product_data = resp.json().get("product", {})
                original_description = product_data.get("body_html", "")

                # Post-process description with image reinjection
                final_description = post_process_description(
                    original_description,
                    translated_description,
                    method="chatgpt",  # You can adapt this if you store the actual method
                    product_data=product_data,
                    target_lang=target_lang
                )

                # Prepare update
                payload = {
                    "product": {
                        "id": pid,
                        "title": translated_title,
                        "body_html": final_description
                    }
                }

                url_put = f"https://{SHOPIFY_STORE_URL}/admin/api/2023-04/products/{pid}.json"
                update_resp = shopify_request("PUT", url_put, json=payload)

                if update_resp.status_code in (200, 201):
                    # Mark as approved in DB
                    cursor.execute("UPDATE translations SET status='Approved' WHERE product_id=?", (pid,))
                    log_translation(pid, translated_title, final_description, "Approved")
                else:
                    logger.error(f"❌ Failed to update product {pid}: {update_resp.text}")

        conn.commit()

    return jsonify({"success": True, "message": f"✅ Approved {len(product_ids)} translations!"})


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

    # ✅ Add this endpoint below your other routes
@app.route("/translation_progress", methods=["GET"])
def get_translation_progress():
    return jsonify({
        "total": translation_progress["total"],
        "completed": translation_progress["completed"]
    })
# ------------------------------ #

# --- Utility: Log Translation ---
def log_translation(product_id, title, description, status):
    """Optional: Log translation events (prints to console)."""
    logger.info(f"Translation log - Product ID: {product_id}, Status: {status}")


# Main Entry Point
# ------------------------------ #
if __name__ == "__main__":
    logger.info("Starting Flask app in %s", os.getcwd())
    app.run(debug=True, port=5006
            )