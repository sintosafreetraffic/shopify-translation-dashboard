import logging
import re
from bs4 import BeautifulSoup
import html

logger = logging.getLogger(__name__)
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

# --- Parser with added DEBUG logging ---
def _parse_chatgpt_description(ai_text):
    """ Robust parser v2: Finds labels sequentially. """
    parsed_data = {'title': '', 'introduction': '', 'features': [], 'cta': ''}
    if not ai_text: logger.warning("Parser v2 received empty input."); return parsed_data

    try: text = BeautifulSoup(ai_text, "html.parser").get_text(separator="\n")
    except Exception as e: logger.warning(f"BS cleaning failed: {e}. Using raw."); text = ai_text
    text = text.lstrip('\ufeff').strip()
    if not text: logger.warning("Parser v2 input empty after cleaning."); return parsed_data
    logger.debug(f"--- Parser v2 Input Text ---\n{text}\n--------------------------")

    # Define labels and create lookup map
    labels_map = {
        "title": ["Product Title", "Produkt-Titel", "Title"],
        "introduction": ["Short Introduction", "Kurze Einführung"],
        "advantages": ["Product Advantages", "Produktvorteile"],
        "cta": ["Call to Action", "Handlungsaufforderung"]
    }
    label_lookup = {lbl.lower(): key for key, patterns in labels_map.items() for lbl in patterns}
    all_label_patterns_str = "|".join(re.escape(p) for patterns in labels_map.values() for p in patterns)

    # Regex to find the start of any known label line
    label_finder_regex = re.compile(rf"^\s*(?:\*\*)*\s*({all_label_patterns_str})\s*:?\s*(?:\*\*)*", flags=re.IGNORECASE | re.MULTILINE)

    matches = []
    for match in label_finder_regex.finditer(text):
        label_text = match.group(1).strip().lower()
        section_key = label_lookup.get(label_text)
        if section_key:
            matches.append({
                "key": section_key,
                "start_line": match.start(), # Start position of the label line itself
                "start_content": match.end() # Position *after* the label line (where content begins)
            })
            logger.debug(f"Parser v2 found label '{label_text}' (key: {section_key}) at index {match.start()}.")

    if not matches:
         logger.warning("Parser v2 found NO section labels. Using basic split fallback.")
         lines = [line.strip() for line in text.split('\n') if line.strip()];
         if len(lines) >= 1: parsed_data['title'] = lines[0]
         if len(lines) >= 2: parsed_data['introduction'] = "\n".join(lines[1:])
         return parsed_data

    # Sort matches by their starting position
    matches.sort(key=lambda x: x['start_content'])

    # Extract content between matches
    for i, current_match in enumerate(matches):
        content_start = current_match['start_content']
        # Content ends at the start of the *next* label line, or end of text
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

    # Check if critical parts are empty
    if not parsed_data['introduction'] and not parsed_data['features']:
         logger.warning("Parser v2 resulted in empty introduction and features.")

    logger.info(f"Robust Parser v2 Result: Title='{parsed_data['title'][:30]}...', IntroLen={len(parsed_data['introduction'])}, Features={len(parsed_data['features'])}, CTA='{parsed_data['cta']}'")
    return parsed_data

# In post_processing.py
def post_process_description(original_html, new_html, method, product_data=None, target_lang='en', final_product_title=None, product_name=None):
    # ---> MOVED variable definition HERE, BEFORE first use <---
    current_product_id = product_data.get("id", "UnknownID") if product_data else "UnknownID"
    # ---> Log line now comes AFTER variable definition <---
    logger.info(f"[{current_product_id}] === ENTERING post_process_description (Method received: '{method}') ===")
    try:
        logger.debug(f"[{current_product_id}] [post_process_description] Starting.") # This debug log is fine here
        # ... rest of function ...
        logger.debug(f"[{current_product_id}] [post_process_description] Starting.")

        # Normalize method name
        if isinstance(method, dict):
            method_name = method.get("method", "").lower()
        else:
            method_name = method.lower()
        logger.info(f"[{current_product_id}] Normalized method_name: '{method_name}'")    

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
        
          # --- Start Structured Path ---
        logger.info(f"[{current_product_id}] Applying structured formatting for {method_name}.")
        # ---> Log Raw Input to Parser <---
        logger.debug(f"[{current_product_id}] Input to parser (new_html):\n'''\n{new_html}\n'''")
        parsed = _parse_chatgpt_description(new_html)
        # ---> Log Parser Output <--- (Already added in parser function, but good here too)
        logger.info(f"[{current_product_id}] Parser output: Intro Len={len(parsed.get('introduction',''))}, Features Found={len(parsed.get('features',[]))}")



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
            if bullet_html:
                # ... (Your CURRENT code for adding the h4 and ul/div might be here) ...
                # Make sure to REMOVE the old structure before adding the new one below
                final_html_parts += [
                    f'<h4 style="font-weight:bold; margin-top: 1.5em; margin-bottom: 0.5em;">{labels.get("advantages", "Product Advantages")}</h4>',
                    # vvv Just add a class to the UL, remove inline styles vvv
                    '<ul class="product-bulletpoints">', # Added class="product-bulletpoints"
                    bullet_html, # The generated <li> items
                    '</ul>',
                    # ^^^ Make sure any wrapper <div> around the UL here is REMOVED ^^^
                ]
            else:
                logger.info(f"[{current_product_id}] DEBUG: Skipping bullet point section (bullet_html is empty).")
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
                # ---> Log Final Built HTML <---
            logger.info(f"✅ [{current_product_id}] BUILT HTML Structure ({method_name}). Length: {len(final_html_output)}")
            logger.debug(f"✅ [{current_product_id}] Final Output HTML:\n'''\n{final_html_output}\n'''")
            logger.info(f"✅ [{current_product_id}] === EXITING post_process_description (Success - Structured path) ===")        
            logger.info(f"✅ [{current_product_id}] DEBUG: Final HTML output (ChatGPT/DeepSeek):\n'''\n{final_html_output}\n'''")
            return final_html_output

        # --- GOOGLE / DEEPL → Clean + inject images + inject  xame ---
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

