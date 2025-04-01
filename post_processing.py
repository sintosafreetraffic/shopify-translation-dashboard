import logging
import re
from bs4 import BeautifulSoup

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
                        # Find the first meaningful <p> (not too short, not just &nbsp;)
            paragraphs = soup.find_all('p')
            for para in paragraphs:
                if para.text.strip() and len(para.text.strip()) > 40:
                    img_div_1 = soup.new_tag('div', style='text-align:center; margin:1em 0;')
                    img_1 = soup.new_tag('img', src=image1_url, style='width:480px; max-width:100%;', loading='lazy')
                    img_div_1.append(img_1)
                    para.insert_after(img_div_1)
                    logging.info("✅ Inserted first image after meaningful paragraph.")
                    break


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

