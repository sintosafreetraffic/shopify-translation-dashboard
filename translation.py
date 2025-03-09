import os
import requests
import logging
import openai
import re
from dotenv import load_dotenv
from deep_translator import GoogleTranslator

# ---------------------------------- #
# ENVIRONMENT VARIABLES / API KEYS
# ---------------------------------- #
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # For ChatGPT
DEEPL_API_KEY = os.getenv("DEEPL_API_KEY")    # For DeepL

# Set OpenAI key for global usage
openai.api_key = OPENAI_API_KEY

load_dotenv()

client = openai.OpenAI(api_key=OPENAI_API_KEY)

# ---------------------------------- #
# GOOGLE TRANSLATE
# ---------------------------------- #
def google_translate(
    text: str,
    source_language: str = "auto",  # "auto" => Google attempts detection
    target_language: str = "de"     # e.g. "en", "de", "fr", "es", ...
) -> str:
    """
    Translate text using Google (deep_translator).
    
    Args:
        text (str): The text to translate.
        source_language (str): The source language code (e.g. "en") or "auto".
        target_language (str): The target language code (e.g. "de" for German).
    
    Returns:
        str: The translated text if successful, otherwise the original text.
    """
    if not text.strip():
        return text  # Empty or whitespace-only

    try:
        translator = GoogleTranslator(
            source=source_language,
            target=target_language
        )
        return translator.translate(text)
    except Exception as e:
        print(f"[google_translate] Error: {e}")
        return text  # Fallback


def language_code_to_descriptive(lang_code: str) -> str:
    """
    Maps language codes like "de" -> "German", "en" -> "English", etc.
    Expand or adjust as needed.
    """
    mapping = {
        "de": "German",
        "en": "English",
        "fr": "French",
        "es": "Spanish",
        "it": "Italian",
        "nl": "Dutch"
    }
    return mapping.get(lang_code.lower(), "English")
def get_default_title(target_lang):
    """Returns a default product title in the target language."""
    placeholders = {
        "en": "Premium Product",
        "de": "Premium-Produkt",
        "fr": "Produit Premium",
        "es": "Producto Premium",
        "nl": "Premium Product",
    }
    return placeholders.get(target_lang, "Premium Product")

def get_default_intro(target_lang):
    """Returns a default product introduction in the target language."""
    placeholders = {
        "en": "Experience unmatched quality and design.",
        "de": "Erleben Sie unvergleichliche Qualität und Design.",
        "fr": "Découvrez une qualité et un design incomparables.",
        "es": "Experimenta una calidad y un diseño incomparables.",
        "nl": "Ervaar ongeëvenaarde kwaliteit en design.",
    }
    return placeholders.get(target_lang, "Experience unmatched quality and design.")

def get_default_features(target_lang):
    """Returns a list of default product features in the target language."""
    placeholders = {
        "en": [
            "High-quality materials for durability.",
            "Designed for comfort and style.",
            "Perfect for everyday use.",
        ],
        "de": [
            "Hochwertige Materialien für Langlebigkeit.",
            "Entworfen für Komfort und Stil.",
            "Perfekt für den täglichen Gebrauch.",
        ],
        "fr": [
            "Matériaux de haute qualité pour une durabilité maximale.",
            "Conçu pour le confort et le style.",
            "Idéal pour une utilisation quotidienne.",
        ],
        "es": [
            "Materiales de alta calidad para mayor durabilidad.",
            "Diseñado para comodidad y estilo.",
            "Perfecto para el uso diario.",
        ],
        "nl": [
            "Hoogwaardige materialen voor duurzaamheid.",
            "Ontworpen voor comfort en stijl.",
            "Perfect voor dagelijks gebruik.",
        ],
    }
    return placeholders.get(target_lang, placeholders["en"])

def get_default_cta(target_lang):
    """Returns a default call-to-action in the target language."""
    placeholders = {
        "en": "Order now and elevate your wardrobe today!",
        "de": "Bestellen Sie jetzt und verbessern Sie Ihre Garderobe!",
        "fr": "Commandez maintenant et améliorez votre garde-robe!",
        "es": "¡Ordene ahora y eleve su estilo!",
        "nl": "Bestel nu en verbeter je garderobe!",
    }
    return placeholders.get(target_lang, "Order now and elevate your wardrobe today!")


# ---------------------------------- #
# DEEPL TRANSLATE
# ---------------------------------- #
def deepl_translate(
    text: str,
    source_language: str = "",     # If blank => auto-detect
    target_language: str = "DE"    # e.g. "EN", "DE", "FR", ...
) -> str:
    """
    Translate text using DeepL API.
    
    If source_language is empty, DeepL will attempt to auto-detect.
    If DEEPL_API_KEY is missing or there's an error, returns original text.
    
    Args:
        text (str): The text to translate.
        source_language (str): DeepL source code (e.g. "EN"). If blank, auto-detect.
        target_language (str): DeepL target code (e.g. "DE").
    
    Returns:
        str: Translated text or the original if something fails.
    """
    if not text.strip():
        return text
    if not DEEPL_API_KEY:
        print("[deepl_translate] DeepL API key not found. Skipping translation.")
        return text

    url = "https://api-free.deepl.com/v2/translate"
    params = {
        "auth_key": DEEPL_API_KEY,
        "text": text,
        "target_lang": target_language.upper()
    }
    if source_language:
        params["source_lang"] = source_language.upper()

    try:
        resp = requests.post(url, data=params)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("translations", [{}])[0].get("text", text)
        else:
            print(f"[deepl_translate] Error from DeepL: {resp.text}")
            return text
    except Exception as e:
        print(f"[deepl_translate] API Request Failed: {e}")
        return text


# ---------------------------------- #
# CHATGPT TRANSLATE
# ---------------------------------- #

# ---------- PRODUCT TITLE TRANSLATION ----------
def chatgpt_translate_title(product_title: str, custom_prompt: str = "", target_language: str = "German") -> str:
    """
    Translate product title while enforcing constraints:
    - '[Human Name] | [Product Name]'
    - Max 25 tokens
    - Max 255 characters
    - '[Product Name]' max 5 words
    """
    if not product_title.strip():
        return product_title

    system_instructions = (
        "You are an expert e-commerce copywriter and translator. "
        "Translate and rewrite product titles to make them persuasive, SEO-friendly, and fully adapted to the target language. "
        "Ensure the translation follows the exact format '[Brand or Key Name] | [Product Name]'.\n\n"

        "- **DO NOT** add quotation marks, brackets, or any extra formatting characters.\n"
        "- The title must be **completely translated into {target_language}**—NO mixing of languages.\n"
        "- Keep the exact format: '[Brand or Key Name] | [Product Name]'.\n"
        "- The '[Product Name]' part must be **≤ 5 words**, but it must always be a complete phrase.\n"
        "- The final title must be **≤ 25 tokens and ≤ 255 characters**, but NEVER cut off mid-word or mid-phrase.\n"
        "- **DO NOT stop mid-sentence**—always return a full, readable, and well-structured title.\n"
        "- **If a title is too long, rephrase or summarize it naturally instead of cutting it off.**\n"
        "- **NEVER return an incomplete response.** If shortening is necessary, **keep the full product meaning.**\n"
        "- Ensure the title remains persuasive, engaging, and suitable for e-commerce SEO.\n"
        "- Use strong, emotionally engaging language that fits local marketing trends.\n"
    )



    user_content = f"""
    Original Title: {product_title}

    User Modifications (if any): {custom_prompt}

    Translate and rewrite this **entirely** into {target_language}, ensuring the title is fully localized, SEO-optimized, and persuasive.
    The response **MUST be a complete, well-structured title**—DO NOT return half-finished titles.
    If necessary, rephrase the title to fit the length while keeping it readable and natural.
    """


    messages = [{"role": "system", "content": system_instructions}, {"role": "user", "content": user_content}]

    try:
        response = client.chat.completions.create(
        model="gpt-4",
        messages=messages,
        max_tokens=50
    )

        title = response.choices[0].message.content.strip()

        logging.info("🔥 Full ChatGPT Output:\n%s", title)


        # Enforce constraints
        title_tokens = title.split()
        title = " ".join(title_tokens[:25])[:255]

        if "|" in title:
            parts = title.split("|")
            human_name = parts[0].strip()
            product_name_words = parts[1].strip().split()
            if len(product_name_words) > 5:
                trimmed_product_name = " ".join(product_name_words[:5])
                title = f"{human_name} | {trimmed_product_name}"

        return title

    except Exception as e:
        logging.error(f"chatgpt_translate_title error: {e}")
        return product_title  # Fallback
    
    
def chatgpt_translate(text: str, custom_prompt: str = "", target_language: str = "German",
                      field_type: str = "description", product_title: str = "") -> str:
    """
    Translate or rewrite product description using ChatGPT with structured output.
    """

    if not text.strip():
        return text

    if not OPENAI_API_KEY:
        logging.error("[chatgpt_translate] OpenAI API key not found. Returning original text.")
        return text

    client = openai.OpenAI(api_key=OPENAI_API_KEY)

    # **Force ChatGPT to always follow the structure**
    system_instructions = (
        "You are an expert e-commerce copywriter. Clearly rewrite the provided product description "
        "into a structured format exactly as follows (strictly in the target language provided):\n\n"
        "Product Title: (Enticing, SEO-friendly title in format: '[Human Name] | [Product Name]')\n"
        "Short Introduction: (minimum 3 and maximum 5 sentence of introduction to engage the buyer)\n\n"
        "Product Advantages:\n"
        "- [Feature Name]: [A compelling, benefit-driven description that highlights why this feature improves comfort, style, or versatility. Make it feel exclusive.]\n"
        "- [Feature Name]: [Use power words like ‘luxurious,’ ‘effortlessly stylish,’ ‘perfect fit,’ ‘irresistible comfort’ to create desire.]\n"
        "- [Feature Name]: [Connect the feature to real-life benefits. Example: ‘The breathable fabric keeps you cool and confident all day long.’]\n"
        "- (Add more if needed)\n\n"
        "\n💡 **Important: Write bullet points in a way that sells the product! Don't just describe features, explain why they matter and why the customer needs them.**"
        "DO NOT list single-word features, and DO NOT omit the description.**"
        "Call to Action: Short, persuasive closing sentence\n\n"
        "**IMPORTANT:** Always respond exactly in this structure with no missing sections."
    )

    user_content = (
        f"{custom_prompt}\n\n"
        f"Original Title:\n{product_title}\n\n"
        f"Original Description:\n{text}\n\n"
        f"Translate and rewrite clearly into {target_language}, following exactly the structure provided."
    )

    messages = [
        {"role": "system", "content": system_instructions},
        {"role": "user", "content": user_content}
    ]

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=0.7,
            max_tokens=1500,
        )

        ai_output = response.choices[0].message.content.strip()

        logging.info("✅ ChatGPT response received:")
        logging.info(ai_output)  # Debugging output

        return ai_output

    except Exception as e:
        logging.error(f"[chatgpt_translate] Error: {e}")
        return text  # Fallback to original
    


    
# ---------------------------------- #
# PRIMARY DISPATCH: apply_method
# ---------------------------------- #

def apply_translation_method(original_text, method, custom_prompt, source_lang, target_lang, product_title="", field_type=None):
    """
    Translates text using the selected method (Google, DeepL, or ChatGPT).
    """
    if not original_text or not method:
        logging.warning("⚠️ Empty text or missing method. Returning original text.")
        return original_text

    logging.info(f"🚀 Translating [{original_text[:50]}...] via '{method}' to '{target_lang}' (Field: {field_type})")

    try:
        translated_text = original_text

        if isinstance(original_text, list):
            return [apply_translation_method(text, method, custom_prompt, source_lang, target_lang, field_type=field_type) for text in original_text]

        method_lower = method.lower()
        
        if method_lower == "chatgpt":
            translated_text = chatgpt_translate(original_text, custom_prompt, target_lang, product_title)
        elif method_lower == "google":
            translated_text = google_translate(original_text, source_lang, target_lang)
        elif method_lower == "deepl":
            translated_text = deepl_translate(original_text, source_lang, target_lang)
        else:
            logging.warning(f"⚠️ Unknown translation method '{method}'. Returning original text.")

    except Exception as e:
        logging.error(f"❌ Translation failed: {e}")
        translated_text = original_text

    logging.info(f"✅ Translation complete: '{original_text[:50]}...' → '{translated_text[:50]}...'")
    return translated_text

def parse_ai_description(ai_text, language='en'):
    # Initialize defaults
    title = intro = cta = ""
    features = []

    # 1. Extract Title
    # Look for a line that starts with "Title:" (case-insensitive) or take the first line as title.
    match = re.search(r'^(?:Title|Product\s*Title)[:\-]\s*(.+)', ai_text, flags=re.IGNORECASE | re.MULTILINE)
    if match:
        title = match.group(1).strip()
    else:
        # If no explicit "Title" label, use the first non-empty line as title
        lines = ai_text.strip().splitlines()
        if lines:
            title = lines[0].strip()

    # 2. Extract Introduction
    match = re.search(r'(?:(?:Short\s+)?Introduction)[:\-]\s*(.+)', ai_text, flags=re.IGNORECASE | re.MULTILINE)
    if match:
        intro = match.group(1).strip()
    else:
        # If not found by label, use the line after the title (if it exists)
        if 'intro' not in locals() or not intro:  # not already set by label
            lines = ai_text.strip().splitlines()
            if len(lines) > 1:
                intro = lines[1].strip()

    # 3. Extract Features (bullet points list)
    features_section = ""
    match = re.search(r'Features?[:\-](.+?)(?=(CTA:|$))', ai_text, flags=re.IGNORECASE | re.DOTALL)
    if match:
        features_section = match.group(1)
    else:
        # If no "Features" label, attempt to find bullet points in text
        features_section = ai_text

    # Split the features section into individual bullet points.
    for line in features_section.splitlines():
        line = line.strip()
        if not line:
            continue  # skip empty lines
        # Identify bullet point lines (starting with a dash, asterisk, or number)
        if line.startswith(('-', '*', '•', '1.', '2.', '3.')):
            # Remove any leading bullet symbols or numbering
            point = line.lstrip("-*•0123456789. ").strip()
            if point:
                features.append(point)

    # 4. Extract CTA
    match = re.search(r'CTA[:\-]\s*(.+)', ai_text, flags=re.IGNORECASE)
    if match:
        cta = match.group(1).strip()
    else:
        # If "CTA" label not found, take the last line as CTA (if it's not already used as a feature)
        lines = ai_text.strip().splitlines()
        if lines:
            last_line = lines[-1].strip()
            if last_line and last_line.lower().startswith(('cta', 'call to action')):  # labeled differently
                # If the last line has 'CTA' text without colon
                cta = last_line.split(':', 1)[-1].strip() if ':' in last_line else last_line
            elif last_line and last_line not in title and last_line not in intro and last_line not in " ".join(features):
                cta = last_line

    return {
    "title": title.strip(),
    "introduction": intro.strip(),
    "features": features,
    "cta": cta.strip()
}



def apply_method(
    text: str,
    method: str,
    custom_prompt: str = "",
    source_language: str = "auto",
    target_language: str = "de",
    field_type: str = "description"
) -> str:
    """
    Dispatch to the correct translation approach:
      - "google"
      - "deepl"
      - "chatgpt"
    (No chaining references here.)
    
    Args:
        text (str): The text to translate or rewrite.
        method (str): The chosen method ("google", "deepl", or "chatgpt").
        custom_prompt (str): Additional instructions for ChatGPT.
        source_language (str): Source language code or "auto" for Google/"" for DeepL.
        target_language (str): Target language code (e.g. "de", "en", "fr").
        field_type (str): Type of content (title, description, handle, etc.).
    
    Returns:
        str: The translated or rewritten text.
    """
    method_lower = method.lower()

    if method_lower == "google":
        return google_translate(
            text,
            source_language=source_language,
            target_language=target_language
        )
    elif method_lower == "deepl":
        # DeepL typically expects uppercase for the target_lang
        return deepl_translate(
            text,
            source_language=source_language,
            target_language=target_language.upper()
        )
    elif method_lower == "chatgpt":
        # e.g., "de" => "German", "en" => "English", etc.
        descriptive_lang = language_code_to_descriptive(target_language)
        return chatgpt_translate(
            text,
            custom_prompt=custom_prompt,
            target_language=descriptive_lang,
            field_type=field_type
        )
    else:
        print(f"[apply_method] Unrecognized method '{method}'. Returning original text.")
        return text

