# File: text_processing_utils.py

import logging
import re
from bs4 import BeautifulSoup # Requires: pip install beautifulsoup4
import html
import unicodedata

# Setup logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
logger = logging.getLogger(__name__)

# --- Text Cleaning & Formatting ---

def clean_translated_text(text: str) -> str:
    """
    Clean up HTML-escaped characters from a translated string.
    """
    if not text:
        return ""
    text = html.unescape(text) # Handles &amp;, &lt;, &gt;, etc.
    text = text.strip()       # Remove leading/trailing whitespace
    return text

def strip_html(html_content: str) -> str:
     """Removes HTML tags from text using BeautifulSoup."""
     if not html_content: return ""
     try:
         # Using html.parser is generally robust and doesn't require external C libraries like lxml might
         soup = BeautifulSoup(html_content, "html.parser")
         return soup.get_text(separator=' ') # Use space as separator for better readability
     except Exception as e:
         logger.warning(f"Error stripping HTML: {e}. Returning original.")
         return html_content # Fallback to original content on error

# --- Title Processing ---

def extract_name_from_title(title: str) -> str | None:
    """
    Extracts the 'name' part (typically before a separator like '|', '–', or '-')
    from a product title string.
    """
    if not title or not isinstance(title, str):
        logger.debug("extract_name_from_title: Input title is empty or not a string.")
        return None
    # Split by common separators, handling optional surrounding whitespace
    parts = re.split(r'\s*[\|–\-]\s*', title, maxsplit=1)
    if len(parts) > 1:
        name = parts[0].strip()
        # Basic check: ensure name isn't overly long or just symbols (simple heuristic)
        if name and len(name) < 50 and re.search(r'[a-zA-Z0-9]', name):
             logger.debug(f"extract_name_from_title: Extracted '{name}' from '{title}'")
             return name
        else:
             logger.debug(f"extract_name_from_title: Potential name part '{name}' seems invalid.")
             return None
    else:
        logger.debug(f"extract_name_from_title: No separator found in '{title}'.")
        return None # Return None if no suitable separator found

def post_process_title(ai_output: str) -> str:
    """ Extracts and cleans title, robust to different AI outputs. """
    # --- Copy the FULL post_process_title function from your post_processing.py HERE ---
    # Make sure it uses logger.info/debug/warning/error appropriately
    if not ai_output: return ""
    logger.info(f"🔍 post_process_title Raw: '''{ai_output}'''")

    try: text = BeautifulSoup(ai_output, "html.parser").get_text(separator=' ')
    except Exception: text = ai_output
    text = re.sub(r"\*\*", "", text); text = ' '.join(text.split()).strip()
    logger.info(f"🧼 post_process_title Cleaned: '''{text}'''")

    title = "" # Initialize

    # Strategy 1: Extract 'Name | Anything', clean trail
    pattern_extract_broad = r"([A-ZÄÖÜ][a-zäöüß]*(?:\s+[A-ZÄÖÜ][a-zäöüß]+)*)\s*\|\s*(.*)"
    match = re.search(pattern_extract_broad, text)
    if match:
        name_part = match.group(1).strip(); product_part_raw = match.group(2).strip()
        trailing_junk_patterns = [ r"\s*\.?\s*Anpassungen.*$", r"\s*\.?\s*Überarbeitet.*$", r"\s*\.?\s*SEO-Opt.*$", r"\s*\*\*.*$", r"\s*-\s*Struktur.*$", r"\s*-\s*Keyword.*$" ]
        product_part_cleaned = product_part_raw
        for junk_pattern in trailing_junk_patterns: product_part_cleaned = re.sub(junk_pattern, "", product_part_cleaned, flags=re.IGNORECASE).strip()
        product_part_cleaned = product_part_cleaned.strip('"').strip().rstrip('.').strip()
        if len(name_part)>1 and len(product_part_cleaned) > 3 and len(product_part_cleaned) < 150:
            title = f"{name_part} | {product_part_cleaned}"
            logger.info(f"✅ post_process_title: Extracted Broadly -> '{title}'")
            return title

    # Strategy 2: Extract between labels (only if title empty)
    if not title:
        pattern_between = r"(?i)(?:Produkttitel:|Product Title:)\s*(.*?)\s*(?:Kurze Einführung:|Short Introduction:|$)"
        match = re.search(pattern_between, text)
        if match:
             candidate = match.group(1).strip().rstrip(':,')
             logger.info(f"🧩 post_process_title: Matched between labels -> '{candidate}'")
             if len(candidate) > 5 and '|' in candidate: title = candidate
             else: logger.warning(f"⚠️ Match between labels ignored (format issue): '{candidate}'")
        if title: return title

    # Strategy 3: Extract after label (only if title empty)
    if not title:
        pattern_after = r"(?i)(?:Produkttitel:|Product Title:)\s*(.*)"
        match = re.search(pattern_after, text)
        if match:
            candidate = match.group(1).strip().rstrip(':,')
            if not re.search(r"(?i)(Kurze Einführung:|Short Introduction:)", candidate):
                logger.info(f"🧩 post_process_title: Matched after label -> '{candidate}'")
                if len(candidate) > 5 and '|' in candidate: title = candidate
                else: logger.warning(f"⚠️ Match after label ignored (format issue): '{candidate}'")
            else: logger.warning(f"⚠️ Match after label contained intro label: '{candidate}'")
        if title: return title

    # Strategy 4: Final Fallback (only if title still empty)
    if not title:
        common_non_title = r"(?i)(Kurze Einführung|Short Introduction|Vorteile|Advantages)"
        if '|' in text and len(text) < 150 and len(text) > 5 and not re.search(common_non_title, text):
            logger.warning(f"⚠️ post_process_title: No pattern/label matched, using plausible cleaned text: '{text}'")
            title = text
        else:
            logger.error(f"❌ post_process_title: All methods failed. Input: '{text[:100]}...'")
            title = ""

    return title


def clean_title_output(title: str, required_name: str | None = None) -> str:
    """Final cleaning, enforces required_name if provided"""
    # --- Copy the FULL clean_title_output function from your post_processing.py HERE ---
    if not title: return ""
    logger.debug(f"Cleaning title output: '{title}'")

    # Remove common AI prefixes
    try:
        prefixes = [r"Neuer Titel:", r"Product Title:", r"Title:", r"Titel:", r"Translated Title:"]
        prefix_pattern = r"^\s*(?:" + "|".join(prefixes) + r")\s*"
        title = re.sub(prefix_pattern, "", title, flags=re.IGNORECASE).strip()
    except Exception as e: logger.error(f"Error removing prefixes in clean_title_output: {e}")

    # Remove wrapping quotes/brackets
    title = re.sub(r'^[\'"“”‘’\[\]\(\){}<>]+|[\'"“”‘’\[\]\(\){}<>]+$', '', title).strip()

    # Remove specific placeholders
    try:
        placeholders = ["[Produktname]", "[Brand]", "[Marke]"] # Add others if needed
        for placeholder in placeholders:
             placeholder_pattern = r"(?i)\s*\[?\s*" + re.escape(placeholder.strip('[] ')) + r"\s*\]?\s*"
             title = re.sub(placeholder_pattern, "", title).strip()
    except Exception as e: logger.error(f"Error removing placeholders in clean_title_output: {e}")

    # Remove parentheses symbols
    title = title.replace('(', '').replace(')', '')

    # Enforce required name if provided
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
        logger.warning(f"clean_title_output: Title '{title}' missing separator. Forcing format with required name '{required_name}'.")
        title = f"{required_name} | {title}" # Assumes rest of title is the product part

    # Remove common trailing punctuation/symbols & consolidate spaces
    title = title.strip().rstrip(",.;:!?-*")
    title = ' '.join(title.split())

    return title.strip()


def apply_title_constraints(title: str) -> str:
     """Applies length/word constraints to a title string."""
     # --- Copy the apply_title_constraints logic from your app.py or export_routes.py HERE ---
     # Example constraint logic:
     logger.debug(f"Applying constraints to title: '{title}'")
     MAX_TITLE_WORDS = 15 # Example word limit for product part
     MAX_CHARS = 255
     final_title_constrained = title

     if "|" in title:
         parts = title.split("|", 1)
         brand = parts[0].strip()
         product_part = parts[1].strip() if len(parts) > 1 else ""
         product_words = product_part.split()
         if len(product_words) > MAX_TITLE_WORDS:
             product_part = " ".join(product_words[:MAX_TITLE_WORDS])
             logger.warning(f"Trimmed product part of title to {MAX_TITLE_WORDS} words.")
         final_title_constrained = f"{brand} | {product_part}" # Reconstruct

     if len(final_title_constrained) > MAX_CHARS:
         logger.warning(f"Trimmed title exceeding {MAX_CHARS} chars.")
         final_title_constrained = final_title_constrained[:MAX_CHARS].rsplit(" ", 1)[0] # Cut at last space

     return final_title_constrained.strip()

# --- Description Processing ---

def _parse_chatgpt_description(ai_text):
    """ Robust parser v2: Finds labels sequentially. """
    # --- Copy the FULL _parse_chatgpt_description function from your post_processing.py HERE ---
    parsed_data = {'title': '', 'introduction': '', 'features': [], 'cta': ''}
    if not ai_text: logger.warning("Parser v2 received empty input."); return parsed_data

    try: text = BeautifulSoup(ai_text, "html.parser").get_text(separator="\n")
    except Exception as e: logger.warning(f"BS cleaning failed: {e}. Using raw."); text = ai_text
    text = text.lstrip('\ufeff').strip()
    if not text: logger.warning("Parser v2 input empty after cleaning."); return parsed_data
    logger.debug(f"--- Parser v2 Input Text ---\n{text}\n--------------------------")

    labels_map = {
        "title": ["Product Title", "Produkt-Titel", "Title"],
        "introduction": ["Short Introduction", "Kurze Einführung"],
        "advantages": ["Product Advantages", "Produktvorteile"],
        "cta": ["Call to Action", "Handlungsaufforderung"]
    }
    label_lookup = {lbl.lower(): key for key, patterns in labels_map.items() for lbl in patterns}
    all_label_patterns_str = "|".join(re.escape(p) for patterns in labels_map.values() for p in patterns)
    label_finder_regex = re.compile(rf"^\s*(?:\*\*)*\s*({all_label_patterns_str})\s*:?\s*(?:\*\*)*", flags=re.IGNORECASE | re.MULTILINE)

    matches = []
    for match in label_finder_regex.finditer(text):
        label_text = match.group(1).strip().lower()
        section_key = label_lookup.get(label_text)
        if section_key:
            matches.append({"key": section_key, "start_line": match.start(), "start_content": match.end()})
            logger.debug(f"Parser v2 found label '{label_text}' (key: {section_key}) at index {match.start()}.")

    if not matches:
         logger.warning("Parser v2 found NO section labels. Using basic split fallback.")
         lines = [line.strip() for line in text.split('\n') if line.strip()];
         if len(lines) >= 1: parsed_data['title'] = lines[0]
         if len(lines) >= 2: parsed_data['introduction'] = "\n".join(lines[1:])
         return parsed_data

    matches.sort(key=lambda x: x['start_content'])

    for i, current_match in enumerate(matches):
        content_start = current_match['start_content']
        content_end = matches[i+1]['start_line'] if i + 1 < len(matches) else len(text)
        content = text[content_start:content_end].strip().strip('*').strip()
        section_key = current_match['key']

        if section_key == "advantages":
             bullet_lines = re.findall(r"^\s*[-*•]\s*(.+)", content, re.MULTILINE)
             parsed_data['features'] = [line.strip().strip('*').strip() for line in bullet_lines if line.strip()]
             logger.debug(f"Extracted {len(parsed_data['features'])} features.")
        elif section_key in parsed_data:
             parsed_data[section_key] = content
             logger.debug(f"Assigned content to section '{section_key}'. Length: {len(content)}")

    if not parsed_data['introduction'] and not parsed_data['features']:
         logger.warning("Parser v2 resulted in empty introduction and features.")

    logger.info(f"Robust Parser v2 Result: Title='{parsed_data['title'][:30]}...', IntroLen={len(parsed_data['introduction'])}, Features={len(parsed_data['features'])}, CTA='{parsed_data['cta']}'")
    return parsed_data


def _get_localized_labels(target_lang):
    """Localizes 'Product Advantages' heading and a fallback CTA."""
    # --- Copy the FULL _get_localized_labels function from your post_processing.py HERE ---
    localized_map = { 'en': {'advantages': 'Product Advantages', 'cta': 'Buy Now!'}, 'de': {'advantages': 'Produktvorteile', 'cta': 'Jetzt kaufen!'}, 'es': {'advantages': 'Ventajas del producto', 'cta': '¡Compra ahora!'}, 'fr': {'advantages': 'Avantages du produit', 'cta': 'Achetez maintenant !'}, 'it': {'advantages': 'Vantaggi del prodotto', 'cta': 'Acquista ora!'}, 'nl': {'advantages': 'Productvoordelen', 'cta': 'Koop nu!'}, 'pt': {'advantages': 'Vantagens do produto', 'cta': 'Compre agora!'}, 'ru': {'advantages': 'Преимущества товара', 'cta': 'Купить сейчас!'}, 'ja': {'advantages': '製品の特長', 'cta': '今すぐ購入！'}, 'zh': {'advantages': '产品优势', 'cta': '立即购买！'}, }
    return localized_map.get(target_lang.lower(), localized_map['en'])


def _build_bullet_points(features):
    """ Converts feature lines into clean <li> HTML list items. """
    # --- Copy the FULL _build_bullet_points function from your post_processing.py HERE ---
    bullet_li_list = []
    for line in features:
        line = re.sub(r"^[✔️•\-* ]+", "", line)
        line = re.sub(r"\*\*(.*?)\*\*", r"\1", line)
        parts = re.split(r'[:\-]', line, maxsplit=1)
        if len(parts) == 2:
            bold, rest = parts
            bullet_li_list.append(f"<li><strong>{bold.strip()}</strong>: {rest.strip()}</li>")
        else:
            bullet_li_list.append(f"<li>{line.strip()}</li>") # Make whole line bold if no separator
            # bullet_li_list.append(f"<li><strong>{line.strip()}</strong></li>") # Alternative: Bold whole line
    return "\n".join(bullet_li_list)


def _get_first_two_images(product_data):
    """ Returns the URLs of the first two images. """
    # --- Copy the FULL _get_first_two_images function from your post_processing.py HERE ---
    image1_url, image2_url = "", ""
    if product_data and 'images' in product_data:
        imgs = product_data.get('images_flat', product_data['images']) # Prefer flattened list if available
        if isinstance(imgs, list): # Check if it's actually a list
             if len(imgs) > 0 and isinstance(imgs[0], dict): image1_url = imgs[0].get('src', '')
             if len(imgs) > 1 and isinstance(imgs[1], dict): image2_url = imgs[1].get('src', '')
    return image1_url, image2_url


def post_process_description(original_html, new_html, method, product_data=None, target_lang='en', final_product_title=None, product_name=None):
    """ Post-processes description: structures AI output, injects images/name. """
    # --- Copy the FULL post_process_description function from your post_processing.py HERE ---
    # Make sure it calls the _helpers defined above (_parse_chatgpt_description, etc.)
    # and handles both structured (ChatGPT/DeepSeek) and basic (Google/DeepL) paths.
    current_product_id = product_data.get("id", "UnknownID") if product_data else "UnknownID"
    logger.info(f"[{current_product_id}] === ENTERING post_process_description (Method received: '{method}') ===")
    try:
        # Normalize method name
        if isinstance(method, dict): method_name = method.get("method", "").lower()
        else: method_name = str(method).lower()

        # Determine Name
        name_to_use = product_name
        if not name_to_use and product_data:
             original_title_for_name = product_data.get("title", "")
             if original_title_for_name:
                  cleaned_title_for_name = re.sub(r"<.*?>|\(Note:.*?\)|:\s*$", "", original_title_for_name, flags=re.IGNORECASE).strip()
                  name_to_use = extract_name_from_title(cleaned_title_for_name)

        # HTML Cleaning
        if new_html: new_html = html.unescape(re.sub(r'\*\*', '', new_html))
        else: return ""

        image1_url, image2_url = _get_first_two_images(product_data)
        alt_text_base = f"{name_to_use} product image" if name_to_use else "Product image"

        # ChatGPT / DeepSeek Path
        if method_name in ["chatgpt", "deepseek"]:
            logger.info(f"[{current_product_id}] Applying structured formatting for {method_name}.")
            parsed = _parse_chatgpt_description(new_html) # Use the parser
            if not parsed.get('introduction') and not parsed.get('features'):
                 logger.error(f"[{current_product_id}] PARSING FAILED for {method_name}.")
                 return clean_translated_text(new_html) # Fallback to cleaned raw

            description_h3_title = parsed.get("title", "").strip()
            if final_product_title: description_h3_title = final_product_title
            elif not description_h3_title: logger.warning(f"[{current_product_id}] No title determined for H3.")

            # Inject name if needed (simplified example)
            if name_to_use and parsed.get("introduction"):
                 # Placeholder logic - implement your actual replacement
                 if name_to_use.lower() not in parsed['introduction'].lower():
                     logger.info(f"Injecting/Replacing name '{name_to_use}' in intro (placeholder logic).")
                     # parsed['introduction'] = ... # Implement replacement
                     pass

            labels = _get_localized_labels(target_lang)
            bullet_html = _build_bullet_points(parsed.get("features", []))

            final_html_parts = [
                '<div style="text-align:center; margin:0 auto; max-width:800px;">',
                f'<h3 style="font-weight:bold;">{description_h3_title}</h3>' if description_h3_title else "",
                f'<p>{parsed.get("introduction", "").strip()}</p>' if parsed.get("introduction", "").strip() else "",
                (f"<div style='margin:1em 0;'><img src='{image1_url}' style='width:480px; max-width:100%;' loading='lazy' alt='{alt_text_base} 1'/></div>" if image1_url else ""),
            ]
            if bullet_html:
                final_html_parts += [
                    f'<h4 style="font-weight:bold; margin-top: 1.5em; margin-bottom: 0.5em;">{labels.get("advantages", "Product Advantages")}</h4>',
                    '<ul class="product-bulletpoints">', bullet_html, '</ul>' # Simple structure
                ]
            if image2_url: final_html_parts.append(f"<div style='margin:2em 0;'><img src='{image2_url}' style='width:480px; max-width:100%;' loading='lazy' alt='{alt_text_base} 2'/></div>")
            cta_html = parsed.get('cta', '').strip() or labels.get('cta', 'Jetzt entdecken!')
            if cta_html: final_html_parts.append(f'<h4 style="font-weight:bold; margin:1.5em 0; font-size:1.2em;">{cta_html}</h4>')
            final_html_parts.append('</div>')
            final_html_output = "\n".join(filter(None, final_html_parts)).strip()
            logger.info(f"✅ [{current_product_id}] Built structured HTML ({method_name}). Length: {len(final_html_output)}")
            return final_html_output

        # Google / DeepL Path
        elif method_name in ["google", "deepl"]:
            logger.info(f"[{current_product_id}] Processing Google/DeepL output.")
            soup = BeautifulSoup(new_html, "html.parser")
            for img in soup.find_all('img'): img.decompose() # Remove existing images

            # Inject name (simplified example)
            if name_to_use:
                 for tag in soup.find_all(string=True):
                     if name_to_use.lower() in tag.string.lower(): # Simple check
                          # Placeholder: Implement replacement if needed
                          pass

            # Inject images
            paragraphs = soup.find_all('p')
            if paragraphs and image1_url and not soup.find('img', src=image1_url):
                img_div_1 = soup.new_tag('div', style='text-align:center; margin:1em 0;')
                img_1 = soup.new_tag('img', src=image1_url, style='width:480px; max-width:100%;', loading='lazy', alt=f'{alt_text_base} 1')
                img_div_1.append(img_1)
                paragraphs[0].insert_after(img_div_1)
            if image2_url and not soup.find('img', src=image2_url):
                 last_p = soup.find_all('p')[-1] if paragraphs else None
                 img_div_2 = soup.new_tag('div', style='text-align:center; margin:2em 0;')
                 img_2 = soup.new_tag('img', src=image2_url, style='width:480px; max-width:100%;', loading='lazy', alt=f'{alt_text_base} 2')
                 img_div_2.append(img_2)
                 if last_p: last_p.insert_before(img_div_2)
                 else: soup.append(img_div_2)

            # Final wrapping
            final_inner_html = f'<div style="text-align: center; margin: 0 auto; max-width: 800px;">{str(soup)}</div>'
            logger.info(f"✅ [{current_product_id}] Final HTML generated (Google/DeepL).")
            return final_inner_html.strip()
        else:
            logger.warning(f"⚠️ [{current_product_id}] Unknown method '{method_name}'. Returning cleaned HTML.")
            return clean_translated_text(new_html)

    except Exception as e:
        logger.exception(f"❌ [{current_product_id}] Exception in post_process_description: {e}")
        # Fallback
        try: return clean_translated_text(new_html or "")
        except: return new_html if new_html else ""

# --- Other Utilities ---

def slugify(text):
    """ Generates a URL slug - requires unicodedata, re """
    if not text: return ""
    text = unicodedata.normalize('NFD', str(text)).encode('ascii', 'ignore').decode('ascii')
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text).strip()
    text = re.sub(r'[-\s]+', '-', text)
    text = text.strip('-')
    return text