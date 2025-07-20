import os
import sys
from dotenv import load_dotenv
import traceback
from variants_utils import clean_translated_text
from variants_utils import get_product_option_values, update_product_option_values
from translation import deepseek_translate_title, deepl_translate, deepseek_translate, chatgpt_translate, chatgpt_translate_title
import unicodedata
import html
from dotenv import load_dotenv
load_dotenv()

print("SHOPIFY_STORE_URL:", os.getenv("SHOPIFY_STORE_URL"))

sys.path.append(os.path.abspath(os.path.dirname(__file__)))  # Ensure current directory is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))  # Add parent directory

print("PYTHONPATH:", sys.path)  # Debugging output

import sqlite3
import requests
import json
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
import re  # For simple HTML pattern matching
from translation import chatgpt_translate, google_translate, deepl_translate
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from variants_utils import get_product_option_values, update_product_option_values
from bs4 import BeautifulSoup  # Add this here
from variants_utils import get_predefined_translation  # ✅ Import the function
from google_sheets import process_google_sheet

# --- CORRECTED IMPORT BLOCK ---
try:
    from product_actions import (
        assign_product_type,
        move_product_to_pinterest_collection,
        get_ai_type_from_description, # Import this from product_actions
        ALLOWED_PRODUCT_TYPES,        # Needed by get_ai_type_from_description
        TARGET_COLLECTION_NAME,
        TARGET_COLLECTION_ID, 
        SOURCE_COLLECTION_ID,   # <<<--- ADD THIS IMPORT (To access the configured ID)
        SOURCE_COLLECTION_NAME,
        platform_api_remove_product_from_collection # <<<--- ADD THIS IMPORT (For logging)        # Needed by move_product_to_pinterest_collection
    )
    logger.info("Successfully imported actions and AI type function from product_actions.py")
except ImportError as e:
    logger.error(f"❌ Failed to import required functions/constants from product_actions.py: {e}")
    logger.error("Ensure product_actions.py exists, is in the Python path, and contains all necessary definitions.")
    # Define dummy functions so the app doesn't crash immediately
    def assign_product_type(*args, **kwargs): logger.error("Dummy assign_product_type called!"); return False
    def move_product_to_pinterest_collection(*args, **kwargs): logger.error("Dummy move_product_to_pinterest_collection called!"); return False
    def get_ai_type_from_description(*args, **kwargs): logger.error("DUMMY get_ai_type_from_description called!"); return None # Make dummy log clearer
    def platform_api_remove_product_from_collection(*args, **kwargs): logger.error("Dummy platform_api_remove_product_from_collection called!"); return False
    ALLOWED_PRODUCT_TYPES = set()
    TARGET_COLLECTION_NAME = "Unknown"
# --- END OF CORRECTED IMPORT BLOCK ---

# ------------------------------ #
# Logging Configuration
# ------------------------------ #


# ---> ADD THIS BLOCK <---
try:
    # Import gender detection and all name functions from random_name.py
    from random_name import determine_product_gender, get_random_female_name, get_random_male_name, get_random_name
    RANDOM_NAME_AVAILABLE = True
    logger.info("✅ Successfully imported gender detector and random name generators.")
except ImportError:
    RANDOM_NAME_AVAILABLE = False
    logger.warning("⚠️ random_name.py not found or critical functions missing. Gender check/name generation unavailable. Using fallbacks.")
    # Define dummy functions if import fails
    def determine_product_gender(product_data): return 'neutral' # Default gender
    def get_random_name(): return "Product"
    def get_random_female_name(): return "ProductF"
    def get_random_male_name(): return "ProductM"


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
# Initialize Flask App
# ------------------------------ #
app = Flask(__name__, template_folder="templates")
CORS(app)  

# ✅ Only now import/export blueprint and register
from export_routes import export_bp
app.register_blueprint(export_bp)

# Ensure the current directory is in the Python module search path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

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

def extract_name_from_title(title: str) -> str | None:
    """
    Extracts the 'name' part (typically before a separator like '|')
    from a product title string.

    Args:
        title: The product title string (e.g., "Daisy | 3-teiliges Set").

    Returns:
        The extracted name (e.g., "Daisy") stripped of whitespace,
        or None if no suitable separator is found or title is empty.
    """
    if not title or not isinstance(title, str):
        logger.debug("extract_name_from_title: Input title is empty or not a string.")
        return None

    # Split by common separators: |, –, - (using regex for flexibility)
    # maxsplit=1 ensures we only split at the first occurrence
    parts = re.split(r'\s*[\|–\-]\s*', title, maxsplit=1) # \s* handles optional space around separator

    if len(parts) > 1:
        # Separator found, the first part is the name
        name = parts[0].strip()
        logger.debug(f"extract_name_from_title: Extracted '{name}' from '{title}'")
        return name
    else:
        # No separator found, cannot extract name in the expected format
        logger.debug(f"extract_name_from_title: No separator found in '{title}'. Cannot extract name.")
        # Optional: You could return the whole title as a fallback, but None is clearer
        # return title.strip()
        return None


logger = logging.getLogger(__name__)


def post_process_description(original_html, new_html, method, product_data=None, target_lang='en', final_product_title=None, product_name=None):
    """
    Post-process a translated product description:
    - ChatGPT & DeepSeek: Full formatting (title, intro, bullets, images, CTA).
      Uses final_product_title (if provided) for the H3 heading.
      Uses product_name (if provided) for name injection/consistency checks.
    - Google/DeepL: Inject product images into cleaned HTML and apply name consistency.
    """
    try:
        # Use product ID in logs if available
        current_product_id = product_data.get("id", "UnknownID") if product_data else "UnknownID"
        logger.debug(f"[{current_product_id}] [post_process_description] Starting.")

        # Normalize method name
        if isinstance(method, dict):
            method_name = method.get("method", "").lower()
        else:
            method_name = method.lower()

        # --- Determine the name to use (Prioritize passed-in name) ---
        name_to_use = product_name # Use the name passed from the main loop if available
        if not name_to_use and product_data:
             original_title_for_name = product_data.get("title", "")
             if original_title_for_name:
                  # Clean title before extracting name
                  cleaned_title_for_name = re.sub(r"<.*?>|\(Note:.*?\)|:\s*$", "", original_title_for_name, flags=re.IGNORECASE).strip()
                  name_to_use = extract_name_from_title(cleaned_title_for_name) # Fallback: extract from product data
                  logger.info(f"[{current_product_id}] Extracted name inside post_process_description (fallback): '{name_to_use}'")
             else:
                  logger.warning(f"[{current_product_id}] Cannot determine name: product_name not passed and product_data has no title.")
        elif not name_to_use:
             logger.warning(f"[{current_product_id}] Cannot determine name: product_name not passed and no product_data.")
        else:
             logger.info(f"[{current_product_id}] Using explicitly passed product_name for consistency: '{name_to_use}'")
        # --- End Name Determination ---


        # --- HTML Cleaning ---
        if new_html:
             new_html = html.unescape(new_html)
             new_html = re.sub(r'(&#x2714;|&#10003;|&#9989;|\u2714|\u2713|\u2705|✔️|✔|✓|✅)\s*', '', new_html)
             new_html = re.sub(r'\*\*', '', new_html)
        else:
             logger.warning(f"[{current_product_id}] [post_process_description] new_html input was empty or None.")
             return ""


        # --- Product image setup ---
        images = product_data.get("images", []) if product_data else []
        image1_url = images[0].get("src") if len(images) > 0 else ""
        image2_url = images[1].get("src") if len(images) > 1 else ""
        alt_text_base = f"{name_to_use} product image" if name_to_use else "Product image"


        # --- CHATGPT / DEEPSEEK → Structured formatting ---
        if method_name in ["chatgpt", "deepseek"]:
            logger.info(f"[{current_product_id}] DEBUG: Entering ChatGPT/DeepSeek processing block.")
            logger.info(f"[{current_product_id}] Parsing structured description (Method: {method_name}).")
            parsed = _parse_chatgpt_description(new_html)
            parsed_features = parsed.get("features", [])
            logger.info(f"[{current_product_id}] DEBUG: Parsed features result: {parsed_features}")
            logger.debug(f"[{current_product_id}] 📊 Output from _parse_chatgpt_description: {parsed}")

            # *** Determine H3 Title ***
            description_h3_title = parsed.get("title", "").strip()
            if final_product_title:
                if description_h3_title and description_h3_title != final_product_title:
                     logger.info(f"[{current_product_id}] Overriding description H3 ('{description_h3_title}') with final product title: '{final_product_title}'")
                description_h3_title = final_product_title
            elif not description_h3_title:
                logger.warning(f"[{current_product_id}] No title in parsed description & no final_product_title provided. Using empty H3.")

            # *** Inject/Replace Name using name_to_use ***
            if name_to_use:
                 # Introduction
                 intro_text = parsed.get("introduction", "")
                 if intro_text:
                      modified_intro = intro_text
                      # Regex to find likely placeholder (Capitalized word before common product type descriptors)
                      match = re.search(r"\b([A-Z][a-z]{3,})\b(?=\s+(?:3-teilige|Set|Collection|Outfit|Mode|Kapuzenpullover|Lingerie|Dessous|Besteckset|Spitzenset))", intro_text)
                      placeholder_name_found = None
                      if match: placeholder_name_found = match.group(1)

                      if placeholder_name_found and placeholder_name_found.lower() != name_to_use.lower():
                            logging.info(f"[{current_product_id}] Replacing name in parsed intro: '{placeholder_name_found}' -> '{name_to_use}'")
                            modified_intro = re.sub(r'\b' + re.escape(placeholder_name_found) + r'\b', name_to_use, intro_text, count=1)
                      elif name_to_use.lower() not in modified_intro.lower():
                            logging.warning(f"[{current_product_id}] Name '{name_to_use}' not found in intro & no clear placeholder replaced.")
                      parsed['introduction'] = modified_intro # Update dict

                 # Features (less likely to need name, but include for completeness)
                 updated_features = []
                 for feature in parsed_features: # Use the variable defined earlier
                      modified_feature = feature
                      # Add similar replacement logic if needed, e.g., checking for placeholders in feature text
                      # match_feature = re.search(...)
                      # if match_feature and match_feature.group(1).lower() != name_to_use.lower():
                      #    modified_feature = re.sub(...)
                      #    logging.info(f"[{current_product_id}] Replacing name in feature: ...")
                      updated_features.append(modified_feature)
                 parsed['features'] = updated_features # Update dict

            # --- Build HTML ---
            labels = _get_localized_labels(target_lang)
            bullet_html = _build_bullet_points(parsed.get("features", [])) # Use potentially updated features
            logger.info(f"[{current_product_id}] DEBUG: Generated bullet_html (first 100 chars): {bullet_html[:100]}")

            final_html_parts = [
                '<div style="text-align:center; margin:0 auto; max-width:800px;">',
                f'<h3 style="font-weight:bold;">{description_h3_title}</h3>' if description_h3_title else "",
                f'<p>{parsed.get("introduction", "").strip()}</p>' if parsed.get("introduction", "").strip() else "", # Use updated intro
            ]

            if image1_url:
                final_html_parts.append(
                    f"<div style='margin:1em 0;'><img src='{image1_url}' style='width:480px; max-width:100%;' loading='lazy' alt='{alt_text_base} 1'/></div>"
                )

            # --- Bullet Point Section ---
            # --- Add this NEW structure for the list ---
          #  if bullet_html:
              #  final_html_parts += [
                    # Keep your H4 heading for "Product Advantages"
               #     f'<h4 class="advantages-heading" style="font-weight:bold; margin-top: 1.5em; margin-bottom: 0.5em;">{labels.get("advantages", "Product Advantages")}</h4>',

                    # ---> ADDED WRAPPER DIV <---
                    # This div centers the list block itself because it's inline-block
                    # within a text-align:center parent. text-align:left keeps list text readable.
                 #   '<div class="centered-list-wrapper" style="display: inline-block; text-align: left;">',

                        # The UL inside the wrapper. Keep necessary list styles.
                        # Padding creates space for bullets; margin:0 removes default space.
              #          '<ul class="advantages-list" style="list-style-position: outside; padding-left: 1.5em; margin: 0;">',
                #            bullet_html, # Your generated <li> items
                  #      '</ul>',
#
              #      # ---> END ADDED WRAPPER <---
            #    ]
            # --- End New Structure ---
          #  else:
             #   logger.info(f"[{current_product_id}] DEBUG: Skipping bullet point section (bullet_html is empty).")


                # --- Bullet Point Section ---
            if bullet_html:
                final_html_parts += [
                    # Keep your H4 heading for "Product Advantages"
                    f'<h4 class="advantages-heading" style="font-weight:bold; margin-top: 1.5em; margin-bottom: 0.5em;">{labels.get("advantages", "Product Advantages")}</h4>',

                    # ---> REPLACED WITH SIMPLER UL STRUCTURE <---
                    # Add the desired class, relying on external CSS for ALL styling (centering, list appearance)
                    '<ul class="product-bulletpoints">',
                        bullet_html, # Your generated <li> items
                    '</ul>',
                    # ---> END REPLACEMENT <---
                ]
            else:
                logger.info(f"[{current_product_id}] DEBUG: Skipping bullet point section (bullet_html is empty).")
            # --- End Bullet Point Section ---
                # --- End Bullet Point Section ---
            
            if image2_url:
                final_html_parts.append(
                    f"<div style='margin:2em 0;'><img src='{image2_url}' style='width:480px; max-width:100%;' loading='lazy' alt='{alt_text_base} 2'/></div>"
                )

            cta_html = parsed.get('cta', '').strip() or labels.get('cta', 'Jetzt entdecken!')
            if cta_html:
                 final_html_parts.append(
                     f'<h4 style="font-weight:bold; margin:1.5em 0; font-size:1.2em;">{cta_html}</h4>'
                 )

            final_html_parts.append('</div>')

            final_html_output = "\n".join(filter(None, final_html_parts)).strip()
            logger.info(f"✅ [{current_product_id}] DEBUG: Final HTML output (ChatGPT/DeepSeek):\n'''\n{final_html_output}\n'''")
            return final_html_output

        # --- GOOGLE / DEEPL → Clean + inject images + inject name ---
        elif method_name in ["google", "deepl"]:
            logger.info(f"[{current_product_id}] Processing Google/DeepL output.")
            soup = BeautifulSoup(new_html, "html.parser")

            # Remove old <img> tags
            img_removed_count = 0
            for img in soup.find_all('img'):
                img.decompose(); img_removed_count += 1
            if img_removed_count > 0:
                 logger.info(f"[{current_product_id}] Removed {img_removed_count} pre-existing img tag(s).")

            # *** Inject/Replace Name using name_to_use ***
            if name_to_use:
                   replaced_in_para = False
                   # Iterate through likely text containers
                   for tag in soup.find_all(['p', 'li', 'span', 'div']): # Add other relevant tags if needed
                       if not tag.string: continue # Skip tags with no direct string content

                       original_text = tag.string.strip()
                       if not original_text: continue # Skip empty strings

                       # Example replacement logic: Find capitalized word before common product type words
                       match = re.search(r"\b([A-Z][a-z]{3,})\b(?=\s+(?:3-teilige|Set|Collection|Outfit|Mode|Kapuzenpullover|Lingerie|Dessous|Besteckset|Spitzenset))", original_text)
                       placeholder_name_found = None
                       if match: placeholder_name_found = match.group(1)

                       if placeholder_name_found and placeholder_name_found.lower() != name_to_use.lower():
                           new_text = re.sub(r'\b' + re.escape(placeholder_name_found) + r'\b', name_to_use, original_text, count=1)
                           logging.info(f"[{current_product_id}] Replacing name in G/D {tag.name}: '{placeholder_name_found}' -> '{name_to_use}'")
                           tag.string.replace_with(new_text) # Use replace_with for NavigableString
                           replaced_in_para = True
                           # Consider breaking or continuing based on desired behavior
                       elif name_to_use.lower() not in original_text.lower() and tag.name == 'p': # Only check primary paragraphs for absence
                            # This warning might be too noisy, consider removing or making debug level
                            logger.debug(f"[{current_product_id}] Name '{name_to_use}' not found in G/D paragraph and no placeholder replaced: '{original_text[:50]}...'")

                   if replaced_in_para:
                        logger.info(f"[{current_product_id}] Name replacement applied to Google/DeepL output.")


            # --- Inject images ---
            paragraphs = soup.find_all('p') # Re-find paragraphs
            if paragraphs and image1_url and not soup.find('img', src=image1_url):
                    img_div_1 = soup.new_tag('div', style='text-align:center; margin:1em 0;')
                    img_1 = soup.new_tag('img', src=image1_url, style='width:480px; max-width:100%;', loading='lazy', alt=f'{alt_text_base} 1')
                    img_div_1.append(img_1)
                    paragraphs[0].insert_after(img_div_1) # Insert after first paragraph
                    logging.info(f"✅ [{current_product_id}] Inserted first image (Google/DeepL).")

            if image2_url and not soup.find('img', src=image2_url):
                    last_p = soup.find_all('p')[-1] if soup.find_all('p') else None
                    img_div_2 = soup.new_tag('div', style='text-align:center; margin:2em 0;')
                    img_2 = soup.new_tag('img', src=image2_url, style='width:480px; max-width:100%;', loading='lazy', alt=f'{alt_text_base} 2')
                    img_div_2.append(img_2)
                    if last_p and hasattr(last_p, 'insert_before'):
                         try: last_p.insert_before(img_div_2); logging.info(f"✅ [{current_product_id}] Inserted second image (Google/DeepL).")
                         except Exception as insert_err: soup.append(img_div_2); logging.warning(f"[{current_product_id}] Failed image 2 insert, appended: {insert_err}")
                    else: soup.append(img_div_2); logging.warning(f"⚠️ [{current_product_id}] Appended second image (Google/DeepL fallback - no last p).")

            # --- Final wrapping ---
            final_inner_html = str(soup)
            direct_wrapper = soup.find('div', recursive=False, style=lambda v: v and 'max-width:800px' in v)
            if not direct_wrapper:
                 body = soup.find('body'); content_root = body if body else soup
                 if not content_root.name == 'div' or 'max-width:800px' not in content_root.get('style',''):
                      logging.info(f"[{current_product_id}] Adding final wrapper div for Google/DeepL.")
                      final_inner_html = f'<div style="text-align: center; margin: 0 auto; max-width: 800px;">{content_root.decode_contents()}</div>'
                 else: final_inner_html = str(content_root)

            logger.info(f"✅ [{current_product_id}] Final HTML generated (Google/DeepL).")
            return final_inner_html.strip()

        else:
            logger.warning(f"⚠️ [{current_product_id}] Unknown method '{method_name}'.")
            return new_html # Return cleaned HTML

    except Exception as e:
        logger.exception(f"❌ [{product_data.get('id', 'UnknownID') if product_data else 'UnknownID'}] [post_process_description] Exception occurred: {e}")
        # Attempt to return cleaned HTML as fallback
        try:
             cleaned_fallback = html.unescape(new_html or "")
             cleaned_fallback = re.sub(r'(&#x2714;|&#10003;|...)\s*', '', cleaned_fallback) # Ensure entities list is correct
             cleaned_fallback = re.sub(r'\*\*', '', cleaned_fallback)
             return cleaned_fallback.strip()
        except:
             return new_html if new_html else ""
        
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

# --- Ensure _get_localized_labels and _build_bullet_points are defined/imported ---
def _get_localized_labels(target_lang): # Placeholder
    return {'advantages': 'Product Advantages', 'cta': 'Buy Now'}
def _build_bullet_points(features): # Placeholder
    return "\n".join([f"<li>{f}</li>" for f in features])
def _get_first_two_images(product_data): # Placeholder Helper
     if not product_data or 'images' not in product_data: return "", ""
     imgs = product_data['images']; img1 = imgs[0].get('src','') if len(imgs)>0 else ""; img2 = imgs[1].get('src','') if len(imgs)>1 else ""; return img1, img2


# --- Main Function ---
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

# --- You no longer need generate_url_handle ---

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
                target_language=target_lang,
                style="ecommerce"
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

# ------------------------------ #
# Flask Routes
# ------------------------------ #

def ensure_https(url):
    url = url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        return f"https://{url}"
    return url


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
    url_custom = f"{ensure_https(SHOPIFY_STORE_URL)}/admin/api/2023-04/custom_collections.json"
    url_smart = f"{ensure_https(SHOPIFY_STORE_URL)}/admin/api/2023-04/smart_collections.json"


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
            f"{ensure_https(SHOPIFY_STORE_URL)}/admin/api/2024-04/products.json" # Use ensure_https and updated API Version
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

        url = f"{ensure_https(SHOPIFY_STORE_URL)}/admin/api/2023-04/products/{product_id}/variants.json"
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
            f"{ensure_https(SHOPIFY_STORE_URL)}/admin/api/2023-04/products/{test_product_id}.json"
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

# --- Translate Single Product ---
@app.route("/translate_test_product", methods=["POST"])
def translate_test_product():
    """
    Translate product fields using Google, DeepL, or ChatGPT, clearly preserving
    HTML formatting and structured content if ChatGPT is selected.
    """
    try:
        data = request.json
        fields_to_translate = data.get("fields", [])
        product_id = data.get("product_id")
        field_methods = data.get("field_methods", {})
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
        chosen_random_name_for_product = None

        # --- Input Validation ---
        if not fields_to_translate:
             return jsonify({"error": "No fields selected for translation"}), 400
        if not field_methods:
             # Allow empty if only handle generation is requested? Maybe not.
             return jsonify({"error": "No translation methods specified"}), 400

        if not product_id:
            return jsonify({"error": "No product ID provided"}), 400

        BASE_URL = SHOPIFY_STORE_URL if SHOPIFY_STORE_URL.startswith("https://") else f"https://{SHOPIFY_STORE_URL}"

        url_get = f"{BASE_URL}/admin/api/2023-04/products/{product_id}.json"
        logging.info(f"📡 Fetching product from Shopify: {url_get}") 

        resp = shopify_request("GET", url_get)
        # ✅ Debug Logging

        if resp.status_code != 200:
            return jsonify({"error": f"Failed to fetch product {product_id}"}), 500

        product_data = resp.json().get("product", {})
        if not product_data:
            return jsonify({"error": "Product not found"}), 404
        
        logging.info(f"✅ Fetched product ly: {json.dumps(product_data, indent=2)[:500]}...")

        updated_data = {} 
        original_title = product_data.get("title", "") # Existing line

        final_processed_title = original_title # Initialize with original title

        if "title" in fields:
            # Log entry into the block
            logging.info("✅ Entering TITLE processing block...")
            chosen_method_config = methods.get("title", {})
            chosen_method = chosen_method_config.get("method", "google") # Default if method not specified
            prompt_title = chosen_method_config.get("prompt", "")
            logging.info(f" Chosen method for TITLE: {chosen_method}")

            title = "" # Initialize title variable

            # Store original cleaned title for potential fallback ONLY IF title exists in product_data
            original_cleaned_title = ""
            original_raw_title = product_data.get("title") # Get original title
            if original_raw_title:
                # Clean HTML, Markdown, and the specific note pattern if present
                temp_title = re.sub(r"<p>|\*\*|Produkttitel:|Kurze Einführung:", "", original_raw_title, flags=re.IGNORECASE)
                temp_title = re.sub(r"\(Note:.*?\)", "", temp_title).strip()
                # A very basic assumption: take everything before potential intro text start
                original_cleaned_title = temp_title.split(" Verleihen Sie")[0].strip()
                logging.info(f" Stored cleaned original title for fallback: '{original_cleaned_title}'")
            else:
                logging.warning(" Original product title is empty or missing in product_data.")


            try: # Add a try block to catch potential errors within title processing
                # --- Method-Specific Translation ---
                if chosen_method == "chatgpt":
                    logging.info(" Calling chatgpt_translate_title...")
                    title = chatgpt_translate_title(
                        product_data.get("title", ""), # Pass original (potentially dirty) title
                        custom_prompt=prompt_title,
                        target_language=target_lang,
                        required_name=chosen_random_name_for_product # <<< ADD THIS ARGUMENT
                    )
                    logging.info(f" Result from chatgpt_translate_title: '{title}'")
                    # Apply basic cleaning needed after ChatGPT if any (optional)
                    # title = post_process_title(title) # Or a simpler cleaner

                elif chosen_method == "deepseek":
                    logging.info(" Calling deepseek_translate_title...")
                    # Pass the original title from product_data - let DeepSeek handle the raw input
                    # The prompt inside deepseek_translate_title asks it to fix format.
                    raw_title_output = deepseek_translate_title(
                        product_data.get("title", ""),
                        target_language=target_lang,
                        required_name=chosen_random_name_for_product # <<< ADD THIS ARGUMENT
                    )
                    # Log the exact raw output BEFORE any processing
                    logging.info(f"🧪 Raw DeepSeek Title Output (before post-processing):\n'''{raw_title_output}'''")

                    logging.info(" Calling post_process_title...")
                    title = post_process_title(raw_title_output) # Use the dedicated post-processor
                    logging.info(f" Result from post_process_title: '{title}'")

                else: # Google, DeepL etc. for title
                    logging.info(f" Calling apply_translation_method for title (method: {chosen_method})...")
                    # Assume apply_translation_method handles these simpler APIs
                    title = apply_translation_method(
                        original_text=product_data.get("title", ""), # Pass original (potentially dirty) title
                        method=chosen_method,
                        custom_prompt=prompt_title,
                        source_lang=source_lang,
                        target_lang=target_lang,
                        field_type="title" # Pass field type if needed by the function
                    )
                    logging.info(f" Result from apply_translation_method for {chosen_method} title: '{title}'")
                    # Basic cleaning might still be needed for non-DeepSeek/ChatGPT methods
                    title = post_process_title(title) # Reuse post_process_title for basic cleaning if suitable
                    # Or use a simpler cleaner:
                    # title = re.sub(r"<.*?>", "", title).strip()


                # --- Common Title Post-Processing (after method-specific translation) ---
                logging.info(f" Calling clean_title_output on: '{title}'") # Log input to next step
                # Make sure clean_title_output function is defined and handles potential empty strings
                # Pass the chosen name to the cleaner function as well
                title = clean_title_output(title if title else "", required_name=chosen_random_name_for_product) # <<< ADD THIS ARGUMENT                
                logging.info(f" Result from clean_title_output: '{title}'")


                # --- Apply Length & Format Constraints ---
                logging.info(f" Applying length and format constraints to: '{title}'")
                if title: # Only process if title is not empty
                    title_tokens = title.split()
                    if len(title_tokens) > 25:
                        logging.warning(f" Title exceeds 25 tokens, trimming.")
                        title = " ".join(title_tokens[:25])

                    # Ensure "[Brand Name] | [Product Name]" format is respected AND trim product name
                    if "|" in title:
                        parts = title.split("|", 1) # Split only once
                        brand_name = parts[0].strip()
                        product_name_part = parts[1].strip() if len(parts) > 1 else ""
                        product_name_words = product_name_part.split()

                        # Ensure product name part is max 10 words
                        if len(product_name_words) > 10:
                            trimmed_product_name = " ".join(product_name_words[:10])
                            logging.warning(f" Product name part exceeds 5 words, trimming to: '{trimmed_product_name}'")
                            title = f"{brand_name} | {trimmed_product_name}"
                        else:
                            # Reconstruct to ensure clean formatting even if not trimmed
                            title = f"{brand_name} | {product_name_part}"

                    # Ensure title does NOT exceed 255 characters & prevent abrupt cuts
                    if len(title) > 255:
                        logging.warning(f" Title exceeds 255 characters, trimming.")
                        # Trim and remove partial word at the end
                        title = title[:255].rsplit(' ', 1)[0]
                else:
                    logging.warning(" Title is empty before length/format checks.")


                logging.info(f" Title after length/format checks: '{title}'")


            except Exception as e:
                logging.error(f"❌ ERROR during title processing block: {e}", exc_info=True)
                # Fallback to the cleaned original title on any error during processing
                title = original_cleaned_title
                logging.warning(f"⚠️ Using fallback title due to error: '{title}'")


            # Final assignment (Only assign if title is not empty, otherwise keep original?)
            # Decide if you want to overwrite with empty title or keep original if all fails
            if title:
                logging.info(f"➡️ Assigning final title to updated_data: '{title}'")
                updated_data["title"] = title
            else:
                logging.warning(f"⚠️ Final title is empty after processing. Not updating title field.")
                # Optionally keep the original UNCLEANED title if needed, or leave updated_data unchanged for title
                # If you want to ensure title field is always present in updated_data:
                # updated_data["title"] = product_data.get("title", "") # Keep original dirty
                # OR
                # updated_data["title"] = original_cleaned_title # Keep cleaned original


            logging.info("✅ Exiting TITLE processing block.") # Log exit

        else:
            # Log if the block was skipped
            logging.warning("⚠️ Skipping title processing because 'title' not in fields.")

        # --- BODY_HTML ---
        # --- BODY_HTML ---
        if "body_html" in fields:
            try:
                logging.info("✅ Entering BODY_HTML processing block...") 
                # Make sure methods dict structure is handled correctly, assuming {'method': 'name'} for simplicity now
                method_name_or_config = methods.get("body_html", "chatgpt") 
                chosen_method = method_name_or_config if isinstance(method_name_or_config, str) else method_name_or_config.get("method", "chatgpt")
                prompt = prompt_desc # Use specific desc prompt

                original_value = product_data.get("body_html", "")
                logging.info(f" Original body_html length: {len(original_value)}")

                translated = "" # Initialize
                if not original_value:
                     logging.warning("⚠️ Original body_html is empty, skipping translation.")
                else:
                    logging.info(f" Calling translation function for body_html (method: {chosen_method})...")
                    # --- Direct calls based on method string ---
                    if chosen_method == "chatgpt":
                         translated = chatgpt_translate(original_value, custom_prompt=prompt, target_language=target_lang, product_title=final_processed_title, required_name=chosen_random_name_for_product)
                    elif chosen_method == "deepseek":
                         translated = deepseek_translate(original_value, custom_prompt=prompt, target_language=target_lang, product_title=final_processed_title, required_name=chosen_random_name_for_product)
                    elif chosen_method == "google":
                         translated = google_translate(original_value, source_language=source_lang, target_language=target_lang)
                    elif chosen_method == "deepl":
                         translated = deepl_translate(original_value, source_language=source_lang, target_language=target_lang)
                    else:
                         logger.warning(f"Unknown body_html method: {chosen_method}")
                         translated = original_value # Fallback
                         
                    logging.info(f" Result from translation function (raw): {translated[:200]}...") 

                # --- Post-process ---
                if translated: # Check if translation happened
                    logging.info(" Calling post_process_description...")
                    # --- ADD final_product_title HERE ---
                    final_description = post_process_description(
                        original_html=original_value, 
                        new_html=translated,
                        method=chosen_method, # Pass method name string
                        product_data=product_data, 
                        target_lang=target_lang,
                        final_product_title=final_processed_title,
                        product_name=chosen_random_name_for_product #  # Pass the definitive title
                    )
                    # --- End ADD ---
                    logging.info(f" Result from post_process_description: {final_description[:200]}...") 

                    if final_description and final_description != original_value:
                         logging.info(f"➡️ Assigning final description to updated_data.")
                         updated_data["body_html"] = final_description
                    elif not final_description:
                         logging.warning("⚠️ Final description is empty after processing. Not updating body_html field.")
                    else: # No change
                         logging.info("Body translation/processing resulted in no change.")

                logging.info("✅ Exiting BODY_HTML processing block.") 

            except Exception as e:
                logging.error(f"❌ ERROR during body_html processing block: {e}", exc_info=True)

        # --- HANDLE Processing ---
        # ... (rest of the function) ...
        # --- HANDLE Processing (using final_processed_title) ---
        if "handle" in fields: # Check if handle update was requested via 'fields' list
             logging.info("✅ Entering HANDLE processing block...")
             if final_processed_title: # Check if we have a title (original or translated)
                 new_handle = slugify(final_processed_title) # Use the improved slugify
                 logger.info(f"  - Generated Handle: '{new_handle}' from Title: '{final_processed_title}'")
                 if new_handle: 
                     # Optional: compare with original handle?
                     # original_handle = product_data.get("handle", "")
                     # if new_handle != original_handle:
                     updated_data["handle"] = new_handle # Add to updates
                 else:
                      logger.warning("  - Handle generation resulted in empty string. Skipping handle update.")
             else:
                 logger.warning("  - Skipping handle generation because final title is empty.")
             logging.info("✅ Exiting HANDLE processing block.")


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
                logging.info(f"🔍 Found Option: {opt.get('name')} with values: {opt.get('values')}")
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
        logging.info("🗺️ translated_options_map so far:")
        for k, v in translated_options_map.items():
            logging.info(f"    {k} → {v}")


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
            url_put = f"{BASE_URL}/admin/api/2023-04/products/{product_id}.json"
            update_resp = shopify_request("PUT", url_put, json=put_payload)

            # ✅ Log Shopify's response
            if update_resp.status_code not in (200, 201):
                return jsonify({"error": "Failed to update product", "details": update_resp.text}), 500
            
                    # 🔍 Debugging: Log the exact payload before sending it to Shopify

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
        logging.exception(f"❌ Exception while updating Shopify: {str(e)}")
        return jsonify({"error": str(e)}), 500    
        
# Global progress tracker (Reminder: Has concurrency limitations for simultaneous users)
translation_progress = {
    "total": 0,
    "completed": 0,
    "errors": 0
}

# --- Translate Entire Collection ---
# In your app.py

@app.route("/translate_collection_fields", methods=["POST"])
def translate_collection_fields():
    """
    Translate selected fields for all products in a collection.
    Ensures name and handle consistency by managing state per product.
    Tracks progress and handles errors gracefully.
    """
    global translation_progress # Declare intention to modify global

    try:
        data = request.json
        collection_id = data.get("collection_id")
        fields_to_translate = data.get("fields", [])
        field_methods = data.get("field_methods", {})
        target_lang = data.get("target_language", "de")
        source_lang = data.get("source_language", "auto")
        prompt_title = data.get("prompt_title", "")
        prompt_desc = data.get("prompt_desc", "")
        chosen_random_name_for_product = None
        # prompt_variants = data.get("prompt_variants", "") # If needed

        # --- Input Validation ---
        if not collection_id or not fields_to_translate or not field_methods:
            # Combine checks for required fields
            missing = []
            if not collection_id: missing.append("collection_id")
            if not fields_to_translate: missing.append("fields")
            if not field_methods: missing.append("field_methods")
            error_msg = f"Missing required fields: {', '.join(missing)}"
            logger.error(error_msg)
            return jsonify({"error": error_msg}), 400
        logger.info(f"Bulk translate request for collection {collection_id}, fields: {fields_to_translate}, methods: {field_methods}")
        # --- Fetch products ---
        # Fetch required fields, including handle if needed for comparison or update
        fetch_fields = "id,title,body_html,handle,images,variants,options"
        # --- Modify this section ---
        try:
            # Extract numeric ID from GID (e.g., "gid://shopify/Collection/644626448708")
            numeric_collection_id = collection_id.split('/')[-1]
            if not numeric_collection_id.isdigit():
                raise ValueError("Could not extract numeric ID from collection GID")
            logger.info(f"Using numeric Collection ID for REST API call: {numeric_collection_id}") # Add log
        except Exception as e:
            logger.error(f"Failed to process collection_id '{collection_id}': {e}")
            return jsonify({"error": f"Invalid collection_id format: {collection_id}"}), 400

        url = (
            f"{ensure_https(SHOPIFY_STORE_URL)}/admin/api/2023-04/products.json"
            f"?collection_id={numeric_collection_id}&fields={fetch_fields}" # <<< USE NUMERIC ID HERE
        )
        # --- End modification ---

        resp = shopify_request("GET", url)
        # ... rest of the function
        resp = shopify_request("GET", url)
        if resp.status_code != 200:
            logger.error(f"Failed to load products from Shopify. Status: {resp.status_code}, Response: {resp.text}")
            return jsonify({"error": "Failed to load products from Shopify"}), 500

        products = resp.json().get("products", [])
        if not products:
             logger.info(f"No products found in collection {collection_id}.")
             return jsonify({"message": "No products found in this collection.", "success": True})

        # --- Initialize Progress ---
        translation_progress["total"] = len(products)
        translation_progress["completed"] = 0
        translation_progress["errors"] = 0
        processed_count = 0
        error_count = 0
        successful_updates = 0
        successful_removals = 0
        successful_type_assignments = 0
        successful_moves = 0


        # --- Loop through products ---
        for idx, product_data in enumerate(products): # Use product_data consistently
            # --- Initialize PER PRODUCT ---
            product_id = product_data.get("id")
            original_title = product_data.get("title", "")
            original_body = product_data.get("body_html", "")
            original_handle = product_data.get("handle", "")
             # ... (after initializing product_id, original_title, original_body etc.) ...
            logger.debug(f"--- Starting processing for Product ID: {product_id} ---") # ADDED DEBUG

            # --->>> STEP 1: DETERMINE GENDER <<<---
            product_gender = determine_product_gender(product_data) # Call the function from random_name.py
            logger.info(f"[{product_id}] Determined Product Gender: {product_gender}")
        # --->>> END STEP 1 <<<---

            logger.info(f"🔁 Translating product {idx+1}/{len(products)}: ID {product_id} ('{original_title[:50]}...') Handle: '{original_handle}'")

            updates = {} # Reset updates for THIS product
            product_update_failed_fields = [] # Track which fields failed for THIS product
            final_processed_title = None # Reset definitive title for THIS product
            name_for_this_product = None # Reset definitive name for THIS product

                # ---> ADD THIS BLOCK (Select Random Name) <---
            # --->>> STEP 2: SELECT RANDOM NAME BASED ON GENDER (REPLACES old selection block) <<<---
            if RANDOM_NAME_AVAILABLE:
                try:
                    if product_gender == 'female':
                        chosen_random_name_for_product = get_random_female_name()
                    elif product_gender == 'male':
                        chosen_random_name_for_product = get_random_male_name()
                    else: # 'neutral' or fallback from determine_product_gender
                        chosen_random_name_for_product = get_random_name() # Use mixed list

                    if not chosen_random_name_for_product: raise ValueError("Random name generator returned empty.")
                    logger.info(f"[{product_id}] Chosen random name ({product_gender}): '{chosen_random_name_for_product}'")

                except Exception as name_gen_err:
                    logger.error(f"[{product_id}] Failed to get random name ({product_gender}): {name_gen_err}. Using fallback.")
                    # --- Fallback logic (using original name extraction) ---
                    try:
                        cleaned_title_for_name = re.sub(r"<.*?>|\(Note:.*?\)|:\s*$", "", original_title, flags=re.IGNORECASE).strip()
                        extracted_name = extract_name_from_title(cleaned_title_for_name)
                        chosen_random_name_for_product = extracted_name if extracted_name else "Product"
                        logger.info(f"[{product_id}] Using fallback extracted/default name: '{chosen_random_name_for_product}'")
                    except Exception as fallback_name_err:
                        logger.error(f"[{product_id}] Fallback name extraction failed: {fallback_name_err}")
                        chosen_random_name_for_product = "Product" # Ultimate fallback
            else: # Random name module not available
                # --- Fallback logic (using original name extraction) ---
                logger.warning(f"[{product_id}] Random name generation unavailable. Using fallback.")
                try:
                    cleaned_title_for_name = re.sub(r"<.*?>|\(Note:.*?\)|:\s*$", "", original_title, flags=re.IGNORECASE).strip()
                    extracted_name = extract_name_from_title(cleaned_title_for_name)
                    chosen_random_name_for_product = extracted_name if extracted_name else "Product"
                    logger.info(f"[{product_id}] Using fallback extracted/default name: '{chosen_random_name_for_product}'")
                except Exception as fallback_name_err:
                    logger.error(f"[{product_id}] Fallback name extraction failed: {fallback_name_err}")
                    chosen_random_name_for_product = "Product"
    # --->>> END STEP 2 (Replaced Block) <<<---
            # ---> END ADD <--
            # --- Extract Name ONCE per product (Critical Step) ---
            #try:
            #    if original_title:
                    # Clean original title before extracting name
             #       cleaned_title_for_name = re.sub(r"<.*?>|\(Note:.*?\)", "", original_title).strip()
                    # Ensure extract_name_from_title function is available and robust
              #      name_for_this_product = extract_name_from_title(cleaned_title_for_name)
             #       logger.info(f"[{product_id}] Extracted name for current iteration: '{name_for_this_product}'")
            #    else:
            #        logger.warning(f"[{product_id}] Cannot extract name, original title is empty.")
            #except Exception as name_exc:
             #   logger.error(f"[{product_id}] Failed to extract name: {name_exc}")
                # Decide how critical this is - maybe allow processing to continue without name?

            # Set a fallback title initially (cleaned original)
            # This will be overwritten if title processing succeeds
            current_title_for_processing = original_title
            if original_title:
                current_title_for_processing = re.sub(r"<.*?>|\(Note:.*?\)", "", original_title).strip()

            # --- TITLE Processing ---
            if "title" in fields_to_translate:
                chosen_method = field_methods.get("title", "google").lower()
                prompt = prompt_title
                logger.info(f"  [{product_id}] Translating Title using: {chosen_method}")
                try:
                    translated_title_raw = ""
                    if not original_title:
                        logger.warning(f"  [{product_id}] Skipping title: Original is empty.")
                    # --- Method-specific translation calls ---
                    elif chosen_method == "chatgpt":
                        translated_title_raw = chatgpt_translate_title(original_title, custom_prompt=prompt, target_language=target_lang, required_name=chosen_random_name_for_product)
                    elif chosen_method == "deepseek":
                        raw_output = deepseek_translate_title(original_title, custom_prompt=prompt, target_language=target_lang, required_name=chosen_random_name_for_product)
                        translated_title_raw = post_process_title(raw_output) # post_process_title cleans DeepSeek output
                    elif chosen_method == "google":
                         translated_title_raw = google_translate(original_title, source_language=source_lang, target_language=target_lang)
                         # Optionally clean simple API results too
                         translated_title_raw = post_process_title(translated_title_raw) if translated_title_raw else ""
                    elif chosen_method == "deepl":
                         translated_title_raw = deepl_translate(original_title, source_language=source_lang, target_language=target_lang)
                         translated_title_raw = post_process_title(translated_title_raw) if translated_title_raw else ""
                    else:
                        logger.warning(f"  [{product_id}] Unknown method '{chosen_method}' for title.")
                        translated_title_raw = original_title # Keep original if method unknown

                    # --- Cleaning and Constraints ---
                    if translated_title_raw:
                         logger.info(f"  [{product_id}] Raw translated title: '{translated_title_raw[:60]}...'")
                         cleaned_title = clean_title_output(translated_title_raw, required_name=chosen_random_name_for_product) # <<< ADD ARGUMENT HERE
                         logger.info(f"  [{product_id}] Cleaned title: '{cleaned_title[:60]}...'")

                         # Apply constraints (e.g., length, word count, format)
                         # Reuse your existing constraint logic here on 'cleaned_title'
                         # For example:
                         MAX_TITLE_WORDS = 15 # Define your constant
                         final_title_constrained = cleaned_title # Start with cleaned
                         if "|" in cleaned_title:
                             parts = cleaned_title.split("|", 1); brand = parts[0].strip(); product_part = parts[1].strip() if len(parts)>1 else ""
                             product_words = product_part.split();
                             if len(product_words) > MAX_TITLE_WORDS: product_part = " ".join(product_words[:MAX_TITLE_WORDS])
                             final_title_constrained = f"{brand} | {product_part}"
                         if len(final_title_constrained) > 255: final_title_constrained = final_title_constrained[:255].rsplit(" ", 1)[0]
                         # End constraint example

                         final_processed_title_candidate = final_title_constrained.strip()

                         # Assign to final_processed_title for use in other steps *if valid*
                         if final_processed_title_candidate:
                              final_processed_title = final_processed_title_candidate # Store the successful result
                              logger.info(f"  [{product_id}] Final title determined: '{final_processed_title}'")
                              # Add to updates only if it's different from the *original* raw title
                              if final_processed_title != original_title:
                                   updates["title"] = final_processed_title
                              else:
                                   logger.info(f"  [{product_id}] Title unchanged from original.")
                         else:
                              logger.warning(f"  [{product_id}] Title became empty after cleaning/constraints.")
                              final_processed_title = current_title_for_processing # Fallback to cleaned original

                    else: # Translation failed or original empty
                         logger.warning(f"  [{product_id}] Title translation failed or original empty.")
                         final_processed_title = current_title_for_processing # Fallback

                except Exception as e:
                    logger.exception(f"❌ Error during title translation for product {product_id}:")
                    product_update_failed_fields.append("title")
                    final_processed_title = current_title_for_processing # Fallback

            else: # Title not in fields_to_translate
                 final_processed_title = current_title_for_processing # Use cleaned original for context/handle

            # --- BODY_HTML Processing ---
            if "body_html" in fields_to_translate and "body_html" not in product_update_failed_fields:
                chosen_method = field_methods.get("body_html", "chatgpt").lower()
                prompt = prompt_desc
                logger.info(f"  [{product_id}] Translating Body HTML using: {chosen_method}")
                try:
                    translated_body = ""
                    if not original_body:
                         logger.warning(f"  [{product_id}] Skipping body: Original is empty.")
                    # --- Method-specific calls ---
                    elif chosen_method == "chatgpt":
                         translated_body = chatgpt_translate(original_body, custom_prompt=prompt, target_language=target_lang, product_title=final_processed_title, required_name=chosen_random_name_for_product) # Pass final title
                    elif chosen_method == "deepseek":
                         translated_body = deepseek_translate(original_body, custom_prompt=prompt, target_language=target_lang, product_title=final_processed_title, required_name=chosen_random_name_for_product) # Pass final title
                    elif chosen_method == "google":
                         translated_body = google_translate(original_body, source_language=source_lang, target_language=target_lang)
                    elif chosen_method == "deepl":
                         translated_body = deepl_translate(original_body, source_language=source_lang, target_language=target_lang)
                    else:
                         logger.warning(f"  [{product_id}] Unknown method '{chosen_method}' for body_html.")
                         translated_body = original_body

                    # --- Post-process ---
                    if translated_body:
                         logger.info(f"  [{product_id}] Raw translated body length: {len(translated_body)}")
                         # *** Pass name_for_this_product and final_processed_title ***
                         final_body = post_process_description(
                            original_html=original_body,
                            new_html=translated_body,
                            method=chosen_method,
                            product_data=product_data,
                            target_lang=target_lang,
                            final_product_title=final_processed_title,
                            product_name=chosen_random_name_for_product # <<< ADDED THIS LINE
                        )
                         final_body = final_body.strip()
                         logger.info(f"  [{product_id}] Final body length: {len(final_body)}")
                         if final_body and final_body != original_body:
                              logger.info(f"  [{product_id}] Final body update added.")
                              updates["body_html"] = final_body
                         elif not final_body:
                              logger.warning(f"  [{product_id}] Final body is empty after processing.")
                         else: # No change
                              logger.info(f"  [{product_id}] Body unchanged from original.")
                    else:
                         logger.warning(f"  [{product_id}] Body translation failed or original empty.")

                except Exception as e:
                    logger.exception(f"❌ Error during body_html translation for product {product_id}:")
                    product_update_failed_fields.append("body_html")

            # --- HANDLE Processing (using final_processed_title) --
            if "handle" not in product_update_failed_fields:
                logger.info(f"  [{product_id}] Entering HANDLE processing (Auto-update enabled).") # Log change
                if final_processed_title: # Still need a title to generate from
                    try:
                        new_handle = slugify(final_processed_title)
                        logger.info(f"  [{product_id}] Slugify input: '{final_processed_title}' -> Output: '{new_handle}'. Original handle: '{original_handle}'")
                        if new_handle and new_handle != original_handle: # Update only if changed
                            logger.info(f"  [{product_id}] Handle update added: '{new_handle}'")
                            updates["handle"] = new_handle
                        elif not new_handle:
                             logger.warning(f"  [{product_id}] Handle generation resulted in empty string.")
                        else: # Handle hasn't changed
                             logger.info(f"  [{product_id}] Handle unchanged ('{new_handle}').")
                    except Exception as e:
                         logger.exception(f"❌ Error during handle generation for product {product_id}:")
                         product_update_failed_fields.append("handle") # Log failure for this specific field
                else:
                     logger.warning(f"  [{product_id}] Skipping handle generation because final_processed_title is empty or missing.")

            # --- VARIANT OPTIONS Processing ---
            if "variant_options" in fields_to_translate and "variant_options" not in product_update_failed_fields:
                chosen_method = field_methods.get("variant_options", "google").lower()
                logger.info(f"  [{product_id}] Processing Variant Options using: {chosen_method}")
                try:
                    product_gid = f"gid://shopify/Product/{product_id}"
                    # Assuming variants_utils handle their own Shopify updates via GraphQL
                    options_to_translate = get_product_option_values(product_gid)
                    if options_to_translate:
                        logger.info(f"  [{product_id}] Found {len(options_to_translate)} option sets.")
                        # Ensure update_product_option_values handles errors internally or returns success/fail
                        options_list = get_product_option_values(product_gid)
                        if options_list:
                            for current_option in options_list:
                                success = update_product_option_values(
                                    product_gid=product_gid,
                                    option=current_option,    # <<< CHANGED: Use the correct parameter name (VERIFY THIS NAME in variants_utils.py)
                                    target_language=target_lang,
                                    source_language=source_lang,
                                    translation_method=chosen_method
                                )
                                if not success:
                                    logger.error(f"❌ variants_utils failed to update options for product {product_id}.")
                                    product_update_failed_fields.append("variant_options") # Mark field as failed
                        else:
                            logger.info(f"  [{product_id}] No options found or fetch failed.")
                except Exception as e:
                     logger.exception(f"❌ Error during variant option processing for product {product_id}:")
                     product_update_failed_fields.append("variant_options")

            logger.info(f"  [{product_id}] Determining product type via AI...")
            # Use the potentially translated/processed description and title for better context
            description_for_type = updates.get("body_html", original_body)
            title_for_context = final_processed_title if final_processed_title else original_title

            determined_type = None # Initialize for this product iteration
            try:
                 determined_type = get_ai_type_from_description(
                    product_description=description_for_type,
                    allowed_types_list=ALLOWED_PRODUCT_TYPES, # Pass the imported set/list
                    product_title=title_for_context
                 )
                 # determined_type will be None if AI fails or returns invalid type
            except Exception as ai_type_err:
                 logger.error(f"  [{product_id}] Exception calling get_ai_type_from_description: {ai_type_err}", exc_info=True)          


            # --- Update Product via REST API (Title, Body, Handle) ---
            critical_fields = ["title", "body_html"] # Example: Define critical fields
            critical_failures = any(field in product_update_failed_fields for field in critical_fields)

            if updates and not critical_failures:
                payload = {"product": {"id": product_id, **updates}}
                logger.info(f"  [{product_id}] Preparing Shopify REST update for fields: {list(updates.keys())}")

                update_url = f"{ensure_https(SHOPIFY_STORE_URL)}/admin/api/2023-04/products/{product_id}.json" # Consider using API_VERSION variable if defined
                update_resp = shopify_request("PUT", update_url, json=payload)

                # Check if the main product update (title, body etc.) was successful
                if update_resp.status_code in (200, 201):
                    logger.info(f"✅ Successfully updated product {product_id} via REST.")
                    successful_updates += 1

                    # --- Post-Update Actions (Type Assignment, Move, Remove) ---
                    if determined_type: # Check if AI determined a type
                        logger.info(f"  [{product_id}] Proceeding with post-update actions using AI type '{determined_type}'...")

                        # --- Assign Product Type ---
                        logger.info(f"  [{product_id}] Attempting to assign type '{determined_type}'...")
                        type_assigned = assign_product_type(product_id, determined_type) # Use the AI type
                        if not type_assigned:
                             logger.error(f"  [{product_id}] ❌ Failed to assign AI type '{determined_type}' after successful update.")

                        # --- Move Product to Target Collection (Conditional on Type Assignment) ---
                        if type_assigned:
                            successful_type_assignments += 1
                        
                            logger.info(f"  [{product_id}] Type assigned. Attempting to move to collection '{TARGET_COLLECTION_NAME}'...")
                            moved_to_target = move_product_to_pinterest_collection(product_id, from_collection_id=SOURCE_COLLECTION_ID)
                            if moved_to_target:
                                logger.info(f"  [{product_id}] ✅ Successfully moved product to '{TARGET_COLLECTION_NAME}'.")
                                successful_moves += 1
                            else:
                                logger.error(f"  [{product_id}] ❌ Failed to move to '{TARGET_COLLECTION_NAME}'. Removal skipped.")
                        
                            # 3. Remove from Source Collection (ALWAYS attempt, even if move fails)
                            removed_from_source = platform_api_remove_product_from_collection(product_id, SOURCE_COLLECTION_ID)
                            if removed_from_source:
                                logger.info(f"  [{product_id}] ✅ Removed product from source collection '{SOURCE_COLLECTION_ID}'.")
                                successful_removals += 1
                            else:
                                logger.error(f"  [{product_id}] ❌ Failed to remove product from source collection '{SOURCE_COLLECTION_ID}'.")

                else: # Main product update failed
                    logger.error(f"❌ Error updating product {product_id} via REST: {update_resp.status_code} {update_resp.text}")
                    error_count += 1 # Count update error

            elif not updates: # No updates were generated for REST API
                 logger.info(f"  [{product_id}] No REST updates generated. Skipping Shopify update and subsequent actions.")
            elif critical_failures: # Critical field processing failed
                 logger.error(f"  [{product_id}] Skipping Shopify REST update and subsequent actions due to critical processing errors in fields: {product_update_failed_fields}")
                 error_count += 1
            # Note: The 'else' for non-critical failures was removed as the payload wasn't used there.
            # If you want partial updates despite non-critical errors, that logic needs to be added back carefully.

            # --- Update Progress ---
            # (This should be outside the 'if updates and not critical_failures:' block
            # to ensure progress is updated even if an update wasn't attempted/failed)
            processed_count += 1
            translation_progress["completed"] = processed_count
            translation_progress["errors"] = error_count

        final_message = (
            f"Translation process completed for collection. "
            f"Products processed: {processed_count}/{len(products)}. "
            f"Successful updates: {successful_updates}. "
            f"Type assignments: {successful_type_assignments}. "
            f"Moves: {successful_moves}. "
            f"Removals: {successful_removals}. "
            f"Errors encountered: {error_count}."
        )
        logger.info(final_message)
        print(final_message)
        return jsonify({
            "success": True,
            "message": final_message,
            "processed_count": processed_count,
            "error_count": error_count,
            "successful_updates": successful_updates,
            "successful_type_assignments": successful_type_assignments,
            "successful_moves": successful_moves,
            "successful_removals": successful_removals
        })
    except Exception as e:
        logger.exception(f"❌ Uncaught error in translate_collection_fields: {e}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500



# --- Don't forget to include the modified post_process_description function definition above this route ---
# --- Ensure extract_name_from_title, slugify, clean_title_output and all translation functions are defined/imported ---
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
                url_get = f"{ensure_https(SHOPIFY_STORE_URL)}/admin/api/2023-04/products/{pid}.json"
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

                url_put = f"{ensure_https(SHOPIFY_STORE_URL)}/admin/api/2023-04/products/{pid}.json"
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
