# export_weekly.py

import os
import sys
import time
import json
import logging
from datetime import datetime, timedelta, UTC
from typing import Optional, Dict, Any, List
from translation import deepseek_translate, google_translate, deepl_translate
from bs4 import BeautifulSoup
import re
import html
import time

# --- Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# --- Logger
if not logging.getLogger().hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(name)s:%(lineno)d] - %(message)s')
logger = logging.getLogger(__name__)

# --- Imports
import shopify_utils
import google_sheets_utils
import variants_utils2

from variants_utils2 import (
    get_product_option_values,
    update_product_option_values,
    clean_translated_text,
    get_predefined_translation
)

# ------------------------------ #
# slugify
# ------------------------------ #
# In app.py (remove the old slugify and generate_url_handle)

import re
import unicodedata

def slugify(text):
    """
    Convert text to a URL-friendly slug. Handles Unicode characters,
    removes non-alphanumeric characters (except hyphens), and limits length.
    """
    if not text:
        return ""
        
    # Normalize unicode characters (e.g., accents -> base letters)
    # NFD decomposes characters, encode/decode removes the accents
    text = unicodedata.normalize('NFD', str(text)).encode('ascii', 'ignore').decode('ascii')
    
    # Lowercase
    text = text.lower()
    
    # Remove characters that aren't alphanumeric, whitespace, or hyphen
    text = re.sub(r'[^\w\s-]', '', text).strip()
    
    # Replace whitespace and consecutive hyphens with a single hyphen
    text = re.sub(r'[-\s]+', '-', text)
    
    # Remove leading/trailing hyphens that might result
    text = text.strip('-')
    
    # Optional: Limit length (e.g., to prevent overly long handles)
    # max_len = 70 # Example Shopify-like limit
    # if len(text) > max_len:
    #     text = text[:max_len].rsplit('-', 1)[0] # Trim at last hyphen before limit
    #     text = text.strip('-') # Ensure no trailing hyphen after cut
        
    return text

def post_process_title(ai_output: str) -> str:
    """
    Extracts and cleans the product title from potentially messy AI output.
    Prioritizes finding 'Name | Product' format anywhere in the text.
    Handles DeepSeek/ChatGPT formats with labels as fallbacks.
    Includes detailed logging.
    """
    if not ai_output:
        logger.warning("⚠️ post_process_title: Empty AI output.")
        return ""

    logger.info(f"🔍 post_process_title: Raw AI Output:\n'''{ai_output}'''")

    # Step 1: Basic Cleanup (HTML, Markdown, extra spaces)
    try:
        # Use html.parser for robustness, separate lines with spaces
        text = BeautifulSoup(ai_output, "html.parser").get_text(separator=' ')
    except Exception as e:
        logger.warning(f"⚠️ BeautifulSoup parsing failed: {e}. Using raw text.")
        text = ai_output # Fallback

    # Remove markdown bold, convert multiple spaces/newlines to single space
    text = re.sub(r"\*\*", "", text) # Remove **
    text = re.sub(r"[\r\n]+", " ", text) # Replace newlines with spaces
    text = ' '.join(text.split()).strip() # Consolidate spaces

    logger.info(f"🧼 post_process_title: Cleaned Text for Regex:\n'''{text}'''")

    # In app.py -> post_process_title function

    # Step 2: *** NEW STRATEGY: Extract Broadly then Clean Trail ***
    # Find 'Name | Anything Else', then clean the 'Anything Else' part
    pattern_extract_broad = r"([A-ZÄÖÜ][a-zäöüß]*(?:\s+[A-ZÄÖÜ][a-zäöüß]+)*)\s*\|\s*(.*)" # Greedy capture for product part
    match = re.search(pattern_extract_broad, text)
    if match:
        name_part = match.group(1).strip()
        product_part_raw = match.group(2).strip() # Includes potential junk

        # Define patterns for junk text typically found AFTER the real title
        # Add more patterns here if needed, make sure they anchor to the end ($)
        # or match specific phrases that mark the end of the title part
        trailing_junk_patterns = [
            r"\s*\.?\s*Anpassungen & SEO-Optimierung.*$",
            r"\s*\.?\s*Überarbeitete Beschreibung.*$",
            r"\s*\.?\s*SEO-Optimierung.*$",
            r"\s*\.?\s*Hier ist.*$", # Less likely at end, but possible
            r"\s*\*\*.*$", # Remove trailing markdown
            r"\s*-\s*Struktur beibehalten.*$", # Remove trailing explanations
            r"\s*-\s*Keyword-Fokus.*$",      # Remove trailing explanations
            # Add specific quote removal if needed AFTER removing junk text
            # r'^"(.*)"$', # To remove quotes wrapping the whole thing
        ]

        product_part_cleaned = product_part_raw
        for junk_pattern in trailing_junk_patterns:
            # Remove trailing junk case-insensitively
            product_part_cleaned = re.sub(junk_pattern, "", product_part_cleaned, flags=re.IGNORECASE).strip()

        # Final cleanup on the cleaned product part (quotes, trailing period)
        product_part_cleaned = product_part_cleaned.strip('"').strip().rstrip('.').strip()

        # Basic sanity check on length
        if len(name_part)>1 and len(product_part_cleaned) > 3 and len(product_part_cleaned) < 150:
             extracted_title = f"{name_part} | {product_part_cleaned}"
             logger.info(f"✅ post_process_title: Extracted Broadly + Cleaned Trail -> '{extracted_title}'")
             return extracted_title # Return the successfully extracted and cleaned title
        else:
             logger.warning(f"⚠️ post_process_title: Extracted Broadly but cleaned part length suspicious (Name: '{name_part}', Cleaned Product Len: {len(product_part_cleaned)}), continuing...")

    # Step 3: Fallback - Try extracting between known labels (like before)
    pattern_between_labels = r"(?i)(?:Produkttitel:|Product Title:)\s*(.*?)\s*(?:Kurze Einführung:|Short Introduction:|$)"
    match = re.search(pattern_between_labels, text)
    if match:
        title = match.group(1).strip().rstrip(':,')
        logger.info(f"🧩 post_process_title: Matched between labels -> '{title}'")
        # Check if it looks like a valid title (contains '|' and reasonable length)
        if len(title) > 5 and len(title) < 200 and '|' in title:
            return title
        else:
            logger.warning(f"⚠️ post_process_title: Match between labels ignored (length/format issue): '{title}'")

    # Step 4: Fallback - Try extracting content after a title label (like before)
    pattern_after_label = r"(?i)(?:Produkttitel:|Product Title:)\s*(.*)"
    match = re.search(pattern_after_label, text)
    if match:
        title = match.group(1).strip().rstrip(':,')
        # Ensure it doesn't contain the next section's label
        if not re.search(r"(?i)(Kurze Einführung:|Short Introduction:)", title):
            logger.info(f"🧩 post_process_title: Matched after title label -> '{title}'")
            # Check if it looks like a valid title
            if len(title) > 5 and len(title) < 200 and '|' in title:
                return title
            else:
                 logger.warning(f"⚠️ post_process_title: Match after label ignored (length/format issue): '{title}'")
        else:
             logger.warning(f"⚠️ post_process_title: Match after label contained intro label: '{title}'")

    # Step 5: Final Fallback - Use cleaned text ONLY if it clearly looks like JUST the title
    # Stricter check: must contain '|', reasonable length, and NOT common intro/section words
    common_non_title_words = r"(?i)(Kurze Einführung|Short Introduction|Vorteile|Advantages|Hier ist|Here is|Beschreibung|Description)"
    if '|' in text and len(text) < 150 and len(text) > 5 and not re.search(common_non_title_words, text):
       logger.warning(f"⚠️ post_process_title: No specific pattern/label matched, falling back to cleaned text as it contains '|' and seems plausible: '{text}'")
       return text
    else:
       logger.error(f"❌ post_process_title: All extraction methods failed. Could not isolate a valid title from input.")
       # Returning empty is safer than returning the whole junk string
       return ""

def clean_title_output(title, required_name=None):
    """
    Cleans AI-generated titles: removes common prefixes, placeholders, extra punctuation,
    and handles incomplete endings. Includes robust regex handling.
    """
    if not title:
        return "" # Return empty if input is empty
        
    # 1. Remove common AI prefixes (case-insensitive, compiled regex)
    try:
        # List of prefixes to remove (add more as needed)
        prefixes_to_remove = [
            r"Neuer Titel:",
            r"Product Title:",
            r"Title:",
            r"Titel:",
            r"Translated Title:",
            # Add more prefixes if observed...
        ]
        # Build the pattern string: ^\s*(?:prefix1|prefix2|...)\s*
        prefix_pattern_str = r"^\s*(?:" + "|".join(prefixes_to_remove) + r")\s*"
        
        # Compile the pattern with the IGNORECASE flag
        compiled_pattern = re.compile(prefix_pattern_str, flags=re.IGNORECASE)
        
        # Use the compiled pattern's sub method to remove the prefix
        title = compiled_pattern.sub("", title).strip()
        
    except re.error as e:
        logger.error(f"❌ Regex error during title prefix removal: {e}")
        # Log the pattern that caused the error for debugging
        logger.error(f"❌ Faulty pattern string might be: {prefix_pattern_str}")
        # Continue without prefix removal if regex fails
    except Exception as e:
        logger.error(f"❌ Unexpected error during title prefix removal: {e}")
        # Continue

    # 2. Remove wrapping quotes/brackets (if any remain after prefix removal)
    title = re.sub(r'^[\'"“”‘’\[\]\(\){}<>]+|[\'"“”‘’\[\]\(\){}<>]+$', '', title).strip()

    # 3. Remove other placeholders (like [Brand], [Produktname] etc.) - More Robustly
    try:
        placeholders = [
            "[Produktname]", "[Brand]", "[Marke]", # German
            "[Nom du produit]",                  # French
            "[Nombre del producto]",             # Spanish
            "[Nome do produto]",                 # Portuguese
            "[Nome do prodotto]",                # Italian
            "[Produktnavn]",                     # Danish
            "[Produktnamn]",                     # Swedish
            "[Προϊόν]",                          # Greek
            "[Produktnaam]",                     # Dutch
            "[Назва продукту]",                  # Ukrainian
            "[ชื่อผลิตภัณฑ์]"                    # Thai
            # Add any other placeholders seen in AI outputs
        ]
        for placeholder in placeholders:
             # Use regex for case-insensitivity and flexible spacing around optional brackets
             placeholder_pattern = r"(?i)\s*\[?\s*" + re.escape(placeholder.strip('[] ')) + r"\s*\]?\s*"
             title = re.sub(placeholder_pattern, "", title).strip()
    except re.error as e:
        logger.error(f"❌ Regex error during title placeholder removal: {e}")
    except Exception as e:
        logger.error(f"❌ Unexpected error during title placeholder removal: {e}")


    # 4. Remove parentheses (just the symbols)
    title = title.replace('(', '').replace(')', '')

    if required_name and "|" in title:
        parts = title.split("|", 1)
        current_name = parts[0].strip()
        product_part = parts[1].strip() if len(parts) > 1 else ""
        if current_name != required_name:
            logger.warning(f"clean_title_output: Enforcing required name '{required_name}' over '{current_name}'")
            title = f"{required_name} | {product_part}"
        else:
            # Ensure correct spacing even if name was correct
            title = f"{required_name} | {product_part}"
    elif required_name and title and "|" not in title:
        # If no pipe separator, maybe the AI failed format. Force it.
        logger.warning(f"clean_title_output: Title '{title}' missing separator. Forcing format with required name '{required_name}'.")
        title = f"{required_name} | {title}" # Assumes rest of title is the product part

    # 5. Remove common trailing punctuation and consolidate internal spaces
    # Added hyphen '-' to the list of characters to remove from the end
    title = title.strip().rstrip(",.;:!?-") 
    title = ' '.join(title.split()) # Consolidate internal whitespace to single spaces

    # 6. Handle incomplete endings (check if title has content)
    incomplete_endings = ("et", "à", "de", "avec", "pour", "en", "sur", "dans") # French examples
    if title and len(title.split()) > 1:
        words = title.split()
        last_word = words[-1]
        if last_word.lower() in incomplete_endings:
             if not title[-1] in ".!?…":
                  title += "..."

    return title.strip() # Final strip

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


def _parse_chatgpt_description(ai_text):
    """
    Robust parser for AI-generated structured descriptions from ChatGPT or DeepSeek.
    Extracts: Product Title, Short Introduction, Product Advantages, Call to Action.
    Supports both markdown and plain text formats.
    """

    parsed_data = {
        'title': '',
        'introduction': '',
        'features': [],
        'cta': ''
    }

    # Remove any HTML and clean up text
    ai_text = BeautifulSoup(ai_text, "html.parser").get_text(separator="\n")
    ai_text = ai_text.lstrip('\ufeff').strip()

    # --- Define section label aliases ---
    label_map = {
        "title": [r"Product Title", r"Produkt[-\s]?Titel", r"Title"],
        "introduction": [r"Short Introduction", r"Kurze Einführung"],
        "advantages": [r"Product Advantages", r"Produktvorteile"],
        "cta": [r"Call to Action", r"Handlungsaufforderung"]
    }

    # --- Create a combined regex pattern ---
    label_section_map = {}
    for section, patterns in label_map.items():
        for p in patterns:
            label_section_map[p] = section

    combined_pattern = "|".join(label_section_map.keys())

    # --- Compile regex to match sections with optional **bold** and flexible colons ---
    section_regex = re.compile(
        rf"(?i)(?:\*\*)?\s*({combined_pattern})\s*:?\s*(?:\*\*)?\s*\n?(.*?)(?=(?:\n\s*(?:\*\*)?\s*(?:{combined_pattern})\s*:?)|\Z)",
        flags=re.DOTALL
    )

    matches = section_regex.findall(ai_text)

    raw_advantages = ""
    for label, content in matches:
        section_key = None
        for pattern, key in label_section_map.items():
            if re.fullmatch(pattern, label.strip(), flags=re.IGNORECASE):
                section_key = key
                break

        if section_key == "advantages":
            raw_advantages = content.strip()
        elif section_key:
            parsed_data[section_key] = content.strip()

    # --- Extract bullet points from advantages ---
    if raw_advantages:
        bullet_lines = re.findall(r"^\s*[-*•]\s*(.+)", raw_advantages, re.MULTILINE)
        parsed_data["features"] = [line.strip() for line in bullet_lines if line.strip()]

    # --- Fallback if everything failed ---
    if not any([parsed_data['title'], parsed_data['introduction'], parsed_data['features']]):
        logging.warning("⚠️ Structured parsing failed. Trying fallback split.")
        lines = [line.strip() for line in ai_text.strip().split("\n") if line.strip()]
        if lines:
            parsed_data["title"] = lines[0]
            parsed_data["introduction"] = "\n".join(lines[1:])

    # --- Debug Logging ---
    logging.debug(f"🔍 Parsed Title: {parsed_data['title']}")
    logging.debug(f"📝 Parsed Introduction: {parsed_data['introduction'][:80]}...")
    logging.debug(f"✅ Parsed Features: {parsed_data['features']}")
    logging.debug(f"📣 Parsed CTA: {parsed_data['cta']}")

    return parsed_data

def _get_localized_labels(target_lang):
    """
    Localizes 'Product Advantages' heading and a fallback CTA ('Buy Now') for supported languages.
    Returns a dict with keys: 'advantages' and 'cta'.
    """
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
        'da': {'advantages': 'Produktfordele', 'cta': 'Køb nu!'},   # <-- Danish
    }
    return localized_map.get(target_lang, localized_map['en'])


def _build_bullet_points(features):
    """
    Converts feature lines into clean <li> HTML list items.
    Removes markdown, emojis, and excess symbols.
    """
    bullet_li_list = []
    for line in features:
        # Clean leading emojis, dashes, stars, markdown bold
        line = re.sub(r"^[✔️•\-* ]+", "", line)
        line = re.sub(r"\*\*(.*?)\*\*", r"\1", line)

        # Optional: bold up to first colon/dash
        parts = re.split(r'[:\-]', line, maxsplit=1) # Use keyword argument
        if len(parts) == 2:
            bold, rest = parts
            bullet_li_list.append(f"<li><strong>{bold.strip()}</strong>: {rest.strip()}</li>")
        else:
            bullet_li_list.append(f"<li>{line.strip()}</li>")
    return "\n".join(bullet_li_list)

def post_process_description(original_html, new_html, method, product_data=None, target_lang='en', final_product_title=None, product_name=None):
    """
    Post-process description. Applies structure for ChatGPT AND DeepSeek.
    """
    current_product_id = product_data.get("id", "UnknownID") if product_data else "UnknownID"
    logger.info(f"[{current_product_id}] === ENTERING post_process_description (Method received: '{method}') ===")
    try:
        # Normalize method name
        if isinstance(method, dict): method_name = method.get("method", "").lower()
        else: method_name = str(method).lower()
        logger.info(f"[{current_product_id}] Normalized method_name: '{method_name}'")

        # Determine Name
        name_to_use = product_name # ... (keep your name logic) ...
        logger.info(f"[{current_product_id}] Using name: '{name_to_use}'")

        # HTML Cleaning
        if new_html: new_html = html.unescape(re.sub(r'\*\*', '', new_html)); # Simplified
        else: return ""

        # Image Setup
        image1_url, image2_url = _get_first_two_images(product_data)
        alt_text_base = f"{name_to_use} product image" if name_to_use else "Product image"

        # --->>> CORRECTED CONDITION BELOW <<<---
        if method_name in ["chatgpt", "deepseek"]:
            logger.info(f"[{current_product_id}] Applying structured formatting for {method_name}.")

            # Ensure robust parser is called
            parsed = _parse_chatgpt_description(new_html)
            logger.info(f"[{current_product_id}] DEBUG: Parsed features count: {len(parsed.get('features',[]))}")

            if not parsed.get('introduction') and not parsed.get('features'):
                 logger.error(f"[{current_product_id}] PARSING FAILED for {method_name}.")
                 return new_html # Return cleaned raw text if parse fails

            # Determine H3 Title
            description_h3_title = parsed.get("title", "").strip()
            if final_product_title: description_h3_title = final_product_title
            elif not description_h3_title: logger.warning(f"[{current_product_id}] No title determined for H3.")

            # Inject/Replace Name if needed
            if name_to_use:
                 # Apply your name replacement logic to parsed['introduction'] / parsed['features']
                 pass # Placeholder for your name injection logic

            # Build HTML structure
            labels = _get_localized_labels(target_lang)
            bullet_html = _build_bullet_points(parsed.get("features", []))

            # Using the CORRECT centering structure for bullets
            final_html_parts = [
                '<div style="text-align:center; margin:0 auto; max-width:800px;">',
                f'<h3 style="font-weight:bold;">{description_h3_title}</h3>' if description_h3_title else "",
                f'<p>{parsed.get("introduction", "").strip()}</p>' if parsed.get("introduction", "").strip() else "",
                (f"<div style='margin:1em 0;'><img src='{image1_url}' style='width:480px; max-width:100%;' loading='lazy' alt='{alt_text_base} 1'/></div>" if image1_url else ""),
            ]
            if bullet_html:
                final_html_parts += [
                    f'<h4 class="advantages-heading" style="font-weight:bold; margin-top: 1.5em; margin-bottom: 0.5em;">{labels.get("advantages", "Product Advantages")}</h4>',
                    '<div class="centered-list-wrapper" style="display: inline-block; text-align: left;">',
                    '<ul class="advantages-list" style="list-style-position: outside; padding-left: 1.5em; margin: 0;">',
                    bullet_html, '</ul>', '</div>'
                ]
            if image2_url: final_html_parts.append(f"<div style='margin:2em 0;'><img src='{image2_url}' style='width:480px; max-width:100%;' loading='lazy' alt='{alt_text_base} 2'/></div>")
            cta_html = parsed.get('cta', '').strip() or labels.get('cta', 'Jetzt entdecken!')
            if cta_html: final_html_parts.append(f'<h4 style="font-weight:bold; margin:1.5em 0; font-size:1.2em;">{cta_html}</h4>')
            final_html_parts.append('</div>')

            final_html_output = "\n".join(filter(None, final_html_parts)).strip()
            logger.info(f"✅ [{current_product_id}] Built structured HTML ({method_name}). Length: {len(final_html_output)}")
            return final_html_output

        else: # Fallback for Google, DeepL, others
            logger.info(f"[{current_product_id}] Using basic image injection path for method '{method_name}'.")
            # ... (Keep your existing BeautifulSoup logic for Google/DeepL here) ...
            soup = BeautifulSoup(new_html, "html.parser"); # Example start
            # ... logic to remove existing images ...
            # ... logic to inject image1_url / image2_url ...
            # ... logic to wrap in centered div ...
            final_wrapped_html = f'<div style="text-align: center; margin: 0 auto; max-width: 800px;">{str(soup)}</div>' # Example wrap
            logger.info(f"✅ [{current_product_id}] Finished basic processing ({method_name}).")
            return final_wrapped_html.strip()

    except Exception as e:
        logger.exception(f"❌ [{current_product_id}] Exception in post_process_description: {e}")
        # Fallback
        try: return html.unescape(new_html or "").strip()
        except: return new_html if new_html else ""


# --- Helper: extract numeric product ID from Shopify GID
def extract_numeric_id_from_gid(gid):
    """Extracts the numeric product ID from a Shopify GID."""
    if gid and 'Product/' in gid:
        return gid.split('/')[-1]
    return gid

# --- Constants (update for your real sheet names!)
DEFAULT_STATUS_SHEET_NAME = os.getenv("STATUS_SHEET_NAME", "Sheet1")
DEFAULT_ARCHIVE_SHEET_NAME = os.getenv("ARCHIVE_SHEET_NAME", "Archive")
DEFAULT_PID_COLUMN_HEADER = "Product ID"
DEFAULT_TITLE_COLUMN_HEADER = "Product Title"
DEFAULT_SALES_COLUMN_HEADER = "Sales Count"

def load_configuration() -> Optional[Dict[str, Any]]:
    config = {}
    config["SOURCE_STORE_URL"] = os.getenv("SHOPIFY_STORE_URL")
    config["SOURCE_STORE_API_KEY"] = os.getenv("SHOPIFY_API_KEY")
    config["SHOPIFY_STORES_CONFIG_JSON"] = os.getenv("SHOPIFY_STORES_CONFIG")
    config["GOOGLE_SHEET_ID"] = os.getenv("GOOGLE_SHEET_ID")
    config["GOOGLE_CREDENTIALS_FILE"] = os.getenv("GOOGLE_CREDENTIALS_FILE")
    config["STATUS_SHEET_NAME"] = os.getenv("STATUS_SHEET_NAME", DEFAULT_STATUS_SHEET_NAME)
    config["ARCHIVE_SHEET_NAME"] = os.getenv("ARCHIVE_SHEET_NAME", DEFAULT_ARCHIVE_SHEET_NAME)
    config["SOURCE_CONTENT_LANGUAGE"] = os.getenv("SOURCE_CONTENT_LANGUAGE", "de")
    config["SHOPIFY_API_VERSION"] = os.getenv("SHOPIFY_API_VERSION", "2024-04")

    # Validate required variables
    required = [
        "SOURCE_STORE_URL", "SOURCE_STORE_API_KEY",
        "SHOPIFY_STORES_CONFIG_JSON", "GOOGLE_SHEET_ID", "GOOGLE_CREDENTIALS_FILE"
    ]
    for key in required:
        if not config.get(key):
            logger.critical(f"Missing config value: {key}")
            return None

    try:
        config["TARGET_STORES"] = json.loads(config["SHOPIFY_STORES_CONFIG_JSON"])
    except Exception as e:
        logger.critical(f"Failed to parse SHOPIFY_STORES_CONFIG: {e}")
        return None

    return config

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
    prompt = custom_prompt
    if isinstance(method, dict):
        method_name = method.get("method", "").lower()
        prompt = method.get("prompt", custom_prompt)
    else:
        method_name = method.lower()
    
    if not original_text or not method:
        logging.warning("⚠️ Missing original_text or method, returning original.")
        return original_text
    
    if method_name not in ["chatgpt", "deepseek", "google", "deepl"]:
        logging.warning(f"⚠️ Unknown method '{method_name}' — returning original text.")
        return original_text


    try:
        # Handle ChatGPT and DeepSeek first (direct returns)
        if method_name == "chatgpt":
            logging.info("🤖 Using ChatGPT — calling once for full HTML...")
            return chatgpt_translate(
    original_text,
    prompt,
    target_lang,
    field_type,
    product_title
)
        if method_name == "deepseek":
            logging.info("🚀 Using DeepSeek translation")
            result = deepseek_translate(
                original_text,
                target_language=target_lang
            )
            if "<" not in result:
                result = f"<p>{result.strip()}</p>"
            return result

        # Existing Google/DeepL handling below
        # For Google or DeepL, do language detection if needed
        if method_name in ["google", "deepl"] and source_lang.lower() == "auto" and description:
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

            if method_name == "google":
                translated = google_translate(stripped, source_lang, target_lang)
            elif method_name == "deepl":
                translated = deepl_translate(stripped, source_lang, target_lang)

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

def main():
    logger.info("=== Weekly Export & Translate Script Starting ===")

    config = load_configuration()
    if not config:
        logger.critical("Config failed to load. Exiting.")
        return

    status_sheet = config["STATUS_SHEET_NAME"]
    archive_sheet = config["ARCHIVE_SHEET_NAME"]

    # 1. Sheet header and initial product map
    sheet_header, headers_ok = google_sheets_utils.ensure_sheet_headers(status_sheet)
    if not headers_ok or not sheet_header:
        logger.critical("Could not ensure Google Sheet headers. Exiting.")
        return

    _h, sheet_data = google_sheets_utils.get_sheet_data_by_header(status_sheet)
    sheet_data_map = {str(r.get(DEFAULT_PID_COLUMN_HEADER, "")).strip(): r for r in sheet_data if r.get(DEFAULT_PID_COLUMN_HEADER, "")}

    # 2. Move finished rows to archive if needed
    google_sheets_utils.move_fully_done_to_sheet2()

    # 3. Get sold products from source Shopify store
    source_session = shopify_utils.create_shopify_session(
        store_domain=config["SOURCE_STORE_URL"],
        access_token=config["SOURCE_STORE_API_KEY"]
    )
    if not source_session:
        logger.critical("Could not create source session. Exiting.")
        return

    days_to_check = int(os.getenv("SOLD_PRODUCTS_DAYS_AGO", "7"))
    min_sales = int(os.getenv("SOLD_PRODUCTS_MIN_SALES", "1"))
    end_date_utc = datetime.now(UTC)
    start_date_utc = end_date_utc - timedelta(days=days_to_check)
    start_date_str = start_date_utc.strftime('%Y-%m-%d')
    end_date_str = end_date_utc.strftime('%Y-%m-%d')

    sold_products = shopify_utils.get_sold_product_details(
        date_from=start_date_str,
        date_to=end_date_str,
        session_context=source_session,
        min_sales=min_sales
    ) or []

    # 4. Add new sold products to sheet if missing
    archived_ids = google_sheets_utils.get_archived_product_ids(archive_sheet) or set()
    new_rows = []
    for item in sold_products:
        pid = str(item.get('product_id', '')).strip()
        if pid and pid not in sheet_data_map and pid not in archived_ids:
            row = [''] * len(sheet_header)
            try:
                if DEFAULT_PID_COLUMN_HEADER in sheet_header:
                    row[sheet_header.index(DEFAULT_PID_COLUMN_HEADER)] = pid
                if DEFAULT_TITLE_COLUMN_HEADER in sheet_header:
                    row[sheet_header.index(DEFAULT_TITLE_COLUMN_HEADER)] = item.get("title", "N/A")
                if DEFAULT_SALES_COLUMN_HEADER in sheet_header:
                    row[sheet_header.index(DEFAULT_SALES_COLUMN_HEADER)] = item.get("sales_count", 0)
            except Exception as e:
                logger.warning(f"Failed to set sheet row for {pid}: {e}")
            new_rows.append(row)
    if new_rows:
        google_sheets_utils.add_new_product_rows(new_rows, status_sheet)

    # Refresh map after adding new products
    _h, sheet_data = google_sheets_utils.get_sheet_data_by_header(status_sheet)
    sheet_data_map = {str(r.get(DEFAULT_PID_COLUMN_HEADER, "")).strip(): r for r in sheet_data if r.get(DEFAULT_PID_COLUMN_HEADER, "")}

    # 5. Process/Export/Translate for Each Target Store
    for pid, row in sheet_data_map.items():
        for store in config["TARGET_STORES"]:
            store_name = store["value"]
            target_url = store["shopify_store_url"]
            target_api_key = store["shopify_api_key"]
            target_lang = store["language"]
            gid_col = store["sheet_gid_col_header"]
            status_col = store["sheet_status_col_header"]

            current_status = str(row.get(status_col, "")).upper()
            if current_status.startswith("DONE") or current_status in ("APPROVED",):
                continue

            # --- 1. Fetch source product data
            source_product = shopify_utils.fetch_product_by_id(
                product_id_or_url=pid,
                session_context=source_session
            )
            if not source_product:
                logger.error(f"[{pid}] Could not fetch source product.")
                google_sheets_utils.update_export_status_for_store(
                    original_product_id=pid, target_store_value=store_name, status_value="ERROR_FETCH_SOURCE", cloned_gid="", cloned_title="", sheet_name=status_sheet
                )
                continue

            # --- 2. Clone if not cloned yet
            cloned_gid = str(row.get(gid_col, "")).strip()
            if not cloned_gid:
                clone_result = shopify_utils.clone_product(source_product, store)
                time.sleep(2)
                logger.info(f"[{pid}] Clone result in {store_name}: {clone_result}")
                if clone_result and clone_result.get("cloned_product_gid"):
                    cloned_gid = clone_result["cloned_product_gid"]

                    # ⬇️ NEW: Verify in target store ⬇️
                    target_session = shopify_utils.create_shopify_session(target_url, target_api_key)
                    numeric_cloned_id = extract_numeric_id_from_gid(cloned_gid)
                    target_product = shopify_utils.fetch_product_by_id(
                        product_id_or_url=numeric_cloned_id,
                        session_context=target_session
                    )
                    if not target_product:
                        logger.error(f"[{pid}] Cloned GID {cloned_gid} not found in {store_name}! Aborting update.")
                        google_sheets_utils.update_export_status_for_store(
                            original_product_id=pid, target_store_value=store_name, status_value="ERROR_CLONE_MISSING",
                            cloned_gid=cloned_gid, cloned_title=source_product["title"], sheet_name=status_sheet
                        )
                        continue  # Do NOT continue to translation/update!

                    # ----------- PRICE MULTIPLIER LOGIC -----------
                    price_multiplier = float(store.get("price_multiplier", 1.0))

                    if price_multiplier != 1.0:
                        try:
                            for variant in target_product.get("variants", []):
                                old_price = float(variant["price"])
                                new_price = old_price * price_multiplier  # Do not round here!
                                variant_id = variant["id"]

                                update_variant_payload = {
                                    "variant": {
                                        "id": variant_id,
                                        "price": new_price
                                        # No need to add compare_at_price here: your helper does it!
                                    }
                                }

                                resp = shopify_utils.update_variant(
                                    store_url=target_url,
                                    api_key=target_api_key,
                                    payload=update_variant_payload,
                                    apply_smart_round=True,         # Use smart rounding (default: True)
                                    double_compare_price=True,      # Set compare_at_price = 2x price (default: True)
                                    compare_at_integer=True         # Compare at price as integer (default: True)
                                )
                                logger.info(
                                    f"[{pid}] Updated variant {variant_id} price: {old_price} -> {resp.get('variant', {}).get('price')}, compare_at_price: {resp.get('variant', {}).get('compare_at_price')}"
                                )
                        except Exception as e:
                            logger.error(f"[{pid}] Failed to update variant prices: {e}")


                    # Only if found, update sheet as CLONED:
                    google_sheets_utils.update_export_status_for_store(
                        original_product_id=pid, target_store_value=store_name, status_value="CLONED",
                        cloned_gid=cloned_gid, cloned_title=source_product["title"], sheet_name=status_sheet
                    )
                else:
                    logger.error(f"[{pid}] Clone failed: {clone_result}")
                    google_sheets_utils.update_export_status_for_store(
                        original_product_id=pid, target_store_value=store_name, status_value="ERROR_CLONING",
                        cloned_gid="", cloned_title="", sheet_name=status_sheet
                    )
                    continue
            else:
                # Also verify that the already-stored GID actually exists before attempting an update!
                target_session = shopify_utils.create_shopify_session(target_url, target_api_key)
                numeric_cloned_id = extract_numeric_id_from_gid(cloned_gid)
                target_product = shopify_utils.fetch_product_by_id(
                    product_id_or_url=numeric_cloned_id,
                    session_context=target_session
                )
                if not target_product:
                    logger.error(f"[{pid}] Existing cloned_gid {cloned_gid} not found in {store_name}! Aborting update.")
                    google_sheets_utils.update_export_status_for_store(
                        original_product_id=pid, target_store_value=store_name, status_value="ERROR_CLONE_MISSING",
                        cloned_gid=cloned_gid, cloned_title="", sheet_name=status_sheet
                    )
                    continue

            # --- 3. Translate fields using best AI post-processing logic
            translation_methods = {
                "title": "deepseek",
                "body_html": "deepseek",
                "handle": "google",
                "tags": "google",
                "variants": "google"
            }

            # ----------- TRANSLATE & POST-PROCESS TITLE AND DESCRIPTION -----------

            # Get one DeepSeek output block for both title/description:
            ai_output = apply_translation_method(
                source_product["title"],
                translation_methods["title"],
                "",
                config["SOURCE_CONTENT_LANGUAGE"],
                target_lang,
                product_title=source_product["title"],
                field_type="title",
                description=source_product.get("body_html", "")
            )

            # Title (clean line for Shopify)
            translated_title = post_process_title(ai_output)
            if not translated_title:
                logger.error(f"[{pid}] Title cleaning failed. Fallback to original title.")
                translated_title = source_product["title"]
            translated_title = translated_title[:255]  # Shopify max length

            logger.info(f"[{pid}] Translated title (cleaned): {translated_title}")

            # Description (fully structured HTML block)
            translated_body_html = post_process_description(
                original_html=source_product.get("body_html", ""),
                new_html=ai_output,
                method=translation_methods["body_html"],
                product_data=source_product,
                target_lang=target_lang,
                final_product_title=translated_title,
                product_name=translated_title.split('|')[0].strip() if '|' in translated_title else translated_title
            )
            logger.info(f"[{pid}] Translated description (cleaned): {translated_body_html[:120]}...")

            # Handle (Google Translate)
            translated_handle = apply_translation_method(
                source_product.get("handle", ""),
                translation_methods["handle"],
                "",
                config["SOURCE_CONTENT_LANGUAGE"],
                target_lang,
                product_title=translated_title,
                field_type="handle"
            )
            logger.info(f"[{pid}] Translated handle: {translated_handle}")

            # Tags (Google Translate)
            translated_tags = apply_translation_method(
                source_product.get("tags", ""),
                translation_methods["tags"],
                "",
                config["SOURCE_CONTENT_LANGUAGE"],
                target_lang,
                product_title=translated_title,
                field_type="tags"
            )
            logger.info(f"[{pid}] Translated tags: {translated_tags}")

            # Variants/Options (Google Translate via variants_utils)
            try:
                options = target_product.get('options', [])
                all_translated_options = []
                for option in options:
                    translated_option = variants_utils2.update_product_option_values(
                        product_gid=target_product["id"],
                        option=option,
                        target_language=target_lang,
                        source_language=config["SOURCE_CONTENT_LANGUAGE"],
                        translation_method=translation_methods["variants"],
                        shopify_store_url=target_url,
                        shopify_api_key=target_api_key
                    )
                    all_translated_options.append(translated_option)
                logger.info(f"[{pid}] Translated variants/options: {all_translated_options}")

                # Assign to the variable used below!
                variants_and_options = all_translated_options if all_translated_options else None

            except Exception as e:
                logger.error(f"[{pid}] Variant/option translation failed: {e}")
                variants_and_options = None

            # --- 4. Update cloned product with translated fields & variants
            update_payload = {
                "title": translated_title,
                "bodyHtml": translated_body_html,
                "handle": translated_handle,
                "tags": translated_tags,
                # Add other fields if your update function supports them
            }
            update_success, resp = shopify_utils.update_product_advanced(
                product_gid=cloned_gid,   # <-- Use the GID, not the integer ID!
                payload=update_payload,
                api_key=target_api_key,
                store_url=target_url
            )
            time.sleep(2)

            # Now update variants/options if possible
            # --- TRANSLATE & UPDATE VARIANT OPTIONS (robust logic from variants_utils2) ---
            try:
                options = variants_utils2.get_product_option_values(
                    product_gid=cloned_gid,        # GID for the cloned product
                    shopify_store_url=target_url,
                    shopify_api_key=target_api_key
                )
                if options:
                    for option in options:
                        success = variants_utils2.update_product_option_values(
                            product_gid=cloned_gid,
                            option=option,
                            target_language=target_lang,
                            source_language=config["SOURCE_CONTENT_LANGUAGE"],
                            translation_method=translation_methods["variants"],
                            shopify_store_url=target_url,
                            shopify_api_key=target_api_key
                        )
                        if success:
                            logger.info(f"[{pid}] ✅ Option updated: {option['name']} on product {cloned_gid}")
                        else:
                            logger.error(f"[{pid}] ❌ Option update failed: {option['name']} on product {cloned_gid}")
                    time.sleep(2)
                else:
                    logger.warning(f"[{pid}] No options found for product {cloned_gid} in {store_name} (nothing to update)")
            except Exception as e:
                logger.error(f"[{pid}] Exception during option translation/update: {e}")

            if update_success:
                google_sheets_utils.update_export_status_for_store(
                    original_product_id=pid, target_store_value=store_name, status_value="DONE",
                    cloned_gid=cloned_gid, cloned_title=translated_title, sheet_name=status_sheet
                )
                logger.info(f"[{pid}] DONE for {store_name}.")

                collection_id = store.get("pinterest_collection_rest_id")
                if collection_id:
                    session = {
                        "store_url": target_url,
                        "access_token": target_api_key,
                    }
                    added = shopify_utils.add_product_to_collection(
                        product_id=int(numeric_cloned_id),  # Must be int, not GID string
                        collection_id=int(collection_id),
                        session=session
                    )
                    if added:
                        logger.info(f"[{pid}] ✅ Added to collection {collection_id} in {store_name}")
                    else:
                        logger.warning(f"[{pid}] ❌ Failed to add to collection {collection_id} in {store_name}")
                else:
                    logger.warning(f"[{pid}] No collection_id found in config for {store_name}")
            else:
                google_sheets_utils.update_export_status_for_store(
                    original_product_id=pid, target_store_value=store_name, status_value="ERROR_TRANSLATING",
                    cloned_gid=cloned_gid, cloned_title=translated_title, sheet_name=status_sheet
                )
                logger.error(f"[{pid}] Update failed for {store_name}.")

            # --- Optional: Delay for rate-limiting
            time.sleep(float(os.getenv("DELAY_BETWEEN_PRODUCTS", "1.0")))

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Script interrupted by user.")
    except Exception as e:
        logger.critical(f"💥 UNHANDLED ERROR: {e}", exc_info=True)
