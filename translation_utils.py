import logging
from utils import slugify

logger = logging.getLogger(__name__)


import os
import sys
from dotenv import load_dotenv
load_dotenv()
import uuid

import requests
import logging
import openai
import re
from openai import OpenAI

client = OpenAI(api_key=os.getenv("CHATGPT_API_KEY"))

# 1) langdetect for auto-detection from descriptions
from langdetect import detect, LangDetectException

# 2) Google Translate from deep_translator
from deep_translator import GoogleTranslator

logger = logging.getLogger(__name__)

# ---------------------------------- #
# ENVIRONMENT VARIABLES / API KEYS
# ---------------------------------- #
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # For ChatGPT
DEEPL_API_KEY = os.getenv("DEEPL_API_KEY")    # For DeepL
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# --- Initialize API Clients --- # (Slightly reorganized for clarity)
openai_client = None
deepseek_client = None # <-- ADDED

# Initialize OpenAI Client
if OPENAI_API_KEY:
    try:
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
        # openai.api_key = OPENAI_API_KEY # Keep if needed globally elsewhere
        logger.info("✅ OpenAI Client Initialized.")
    except Exception as e: logger.error(f"❌ Failed to initialize OpenAI Client: {e}")
else: logger.warning("⚠️ OPENAI_API_KEY not found.")

# ---> ADD THIS BLOCK <---
# Initialize DeepSeek Client
if DEEPSEEK_API_KEY:
    try:
        deepseek_client = OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com/v1"
            )
        logger.info("✅ DeepSeek Client Initialized.")
    except Exception as e:
        logger.error(f"❌ Failed to initialize DeepSeek Client: {e}")
else:
    logger.warning("⚠️ DEEPSEEK_API_KEY not found. DeepSeek features disabled.")
# ---> END ADDED BLOCK <---

# Set OpenAI key for global usage
openai.api_key = OPENAI_API_KEY

# Optional: confirm environment variables loaded
logger.info(f"OPENAI_API_KEY present? {'Yes' if OPENAI_API_KEY else 'No'}")
logger.info(f"DEEPL_API_KEY present? {'Yes' if DEEPL_API_KEY else 'No'}")

# ---------------------------------- #
# DETECT LANGUAGE FROM DESCRIPTION
# ---------------------------------- #

def clean_title_output(title):
    """ Cleans final titles: removes extra prefixes, placeholders, punctuation. """
    if not title: return ""
    logger.debug(f"Cleaning title output: '{title}'")

    # Remove common AI prefixes
    try:
        prefixes = [r"Neuer Titel:", r"Product Title:", r"Title:", r"Titel:", r"Translated Title:"]
        prefix_pattern = r"^\s*(?:" + "|".join(prefixes) + r")\s*"
        title = re.sub(prefix_pattern, "", title, flags=re.IGNORECASE).strip()
    except Exception as e: logger.error(f"Error removing prefixes: {e}")

    # Remove wrapping quotes/brackets
    title = re.sub(r'^[\'"“”‘’\[\]\(\){}<>]+|[\'"“”‘’\[\]\(\){}<>]+$', '', title).strip()

    # Remove specific placeholders
    try:
        placeholders = ["[Produktname]", "[Brand]", "[Marke]"] # Add others if needed
        for placeholder in placeholders:
             placeholder_pattern = r"(?i)\s*\[?\s*" + re.escape(placeholder.strip('[] ')) + r"\s*\]?\s*"
             title = re.sub(placeholder_pattern, "", title).strip()
    except Exception as e: logger.error(f"Error removing placeholders: {e}")

    # Remove parentheses symbols
    title = title.replace('(', '').replace(')', '')

    # Remove common trailing punctuation/symbols & consolidate spaces
    title = title.strip().rstrip(",.;:!?-*")
    title = ' '.join(title.split())

    return title.strip()

def post_process_title(ai_output: str) -> str:
    """
    Extracts and cleans a proper product title from an AI response (ChatGPT or DeepSeek).
    Looks for 'Name | Product Name' format and strips extra formatting.
    """
    if not ai_output:
        return ""

    # Remove markdown or HTML formatting like ** or <p>
    cleaned_text = re.sub(r"(\*\*|<\/?p>)", "", ai_output).strip()

    # Try to find a title like "Name | Product"
    match = re.search(r"([A-ZÄÖÜ][a-zäöüß]+)\s*[\|–\-]\s*([A-ZÄÖÜa-zäöüß0-9 ,\-]+)", cleaned_text)
    if match:
        name, product = match.groups()
        return f"{name.strip()} | {product.strip()}"

    # Fallback: use the first line, trimmed
    return cleaned_text.split("\n")[0].strip()

def clean_title(title: str) -> str:
    """
    Remove wrapping quotes or brackets from title.
    """
    return re.sub(r'^[\'"“”‘’\[\]\(\){}<>]+|[\'"“”‘’\[\]\(\){}<>]+$', '', title.strip())


def detect_language_from_description(description: str) -> str:
    """
    Detects the source language from a larger description text using `langdetect`.
    Returns 'auto' if detection fails or description is empty.

    Args:
        description (str): The product’s longer text/body_html from Shopify.

    Returns:
        str: A 2-letter ISO code like 'de', 'en', etc., or 'auto' if detection fails.
    """
    desc = description.strip()
    if not desc:
        logger.info("[detect_language_from_description] Description empty => returning 'auto'.")
        return "auto"

    try:
        detected_lang = detect(desc)
        logger.info(f"[detect_language_from_description] Detected language: {detected_lang}")
        return detected_lang
    except LangDetectException:
        logger.info("[detect_language_from_description] Could not detect => 'auto'.")
        return "auto"

# ---------------------------------- #
# GOOGLE TRANSLATE WRAPPER
# ---------------------------------- #
def google_translate(
    text: str,
    source_language: str = "auto",  # "auto" => Google attempts detection (but can override with your own detection)
    target_language: str = None     # e.g., "en", "de", "fr", "es", etc.
) -> str:
    """
    Translate text using `deep_translator`'s GoogleTranslator.
    
    Args:
        text (str): The text to translate.
        source_language (str): The source language code (e.g., 'en', 'de') or 'auto'.
        target_language (str): The target language code (e.g., 'de', 'en').

    Returns:
        str: The translated text if successful, otherwise the original text on error.
    """
    if not text.strip():
        # Empty or whitespace text => return original
        return text

    # Ensure language codes are normalized
    source_language = (source_language or "auto").lower()
    target_language = (target_language or "en").lower()

    try:
        translator = GoogleTranslator(source=source_language, target=target_language)
        translated = translator.translate(text)
        logger.info(f"[google_translate] '{text[:30]}...' ({source_language} -> {target_language}) => '{translated[:30]}...'")
        return translated
    except Exception as e:
        logger.error(f"[google_translate] Error: {e}")
        return text  # fallback to original text

# ---------------------------------- #
# LANGUAGE CODE MAPPING
# ---------------------------------- #
def language_code_to_descriptive(lang_code: str) -> str:
    """
    Maps language codes like 'de' -> 'German', 'en' -> 'English'.
    Extend or modify as needed for your store’s languages.
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

# Below are placeholders for default texts you may optionally use
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
    source_language: str = "",    # If blank => auto-detect
    target_language: str = "DE"   # e.g., "EN", "DE", "FR", ...
) -> str:
    """
    Translate text using the DeepL API.
    If source_language is empty => DeepL attempts detection.
    If DEEPL_API_KEY is missing or there's an error, returns the original text.
    """
    if not text.strip():
        return text
    if not DEEPL_API_KEY:
        logger.warning("[deepl_translate] No DeepL API key found => skipping translation.")
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
            resp_data = resp.json()
            return resp_data.get("translations", [{}])[0].get("text", text)
        else:
            logger.error(f"[deepl_translate] DeepL returned {resp.status_code}: {resp.text}")
            return text
    except Exception as e:
        logger.error(f"[deepl_translate] Request failed: {e}")
        return text

# ---------------------------------- #
# CHATGPT TITLE TRANSLATION
# ---------------------------------- #
def chatgpt_translate_title(product_title: str, custom_prompt: str = "", target_language: str = "German") -> str:
    """
    Translate product title with ChatGPT, enforcing constraints like '[Brand] | [Product Name]'.
    Keeps final text ≤ 30 tokens, ≤ 285 chars, and max 6 words in the '[Product Name]' portion.
    """
    if not product_title.strip():
        return product_title

    system_instructions = (
        f"You are an expert e-commerce copywriter and translator. "
        f"Translate and rewrite product titles to make them persuasive, SEO-friendly, and fully adapted to the target language. "
        f"Ensure the translation follows the exact format '[Brand or Key Name] | [Product Name]'.\n\n"
        "- DO NOT add quotation marks, brackets, or any extra formatting characters.\n"
        "- The title must be completely translated into {target_language} — NO mixing of languages.\n"
        "- Keep the exact format: '[Brand or Key Name] | [Product Name]'.\n"
        "- '[Product Name]' part must be a complete phrase, but keep it under 4 words. \n"
        "The final title must be under 20 tokens and under 200 characters. Always complete the phrase, never truncate.\n"
        "- If a title is too long, rephrase or summarize naturally.\n"
        "- NEVER return an incomplete response.\n"
        "- Use persuasive, localized language.\n"
    )

    user_content = f"""
    Original Title: {product_title}

    User Modifications: {custom_prompt}

    Translate and rewrite entirely into {target_language}, fully localized and SEO-optimized.
    Return a complete, well-structured title. If too long, rephrase naturally while keeping the meaning.
    """

    messages = [
        {"role": "system", "content": system_instructions},
        {"role": "user", "content": user_content}
    ]

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            max_tokens=60
        )

        if not response.choices or not response.choices[0].message.content:
            logger.warning("⚠️ Empty ChatGPT title response. Using original title.")
            return product_title

        raw_title = response.choices[0].message.content.strip()
        logger.info("🔥 Full ChatGPT Output:\n%s", raw_title)

        # Enforce length limits
        title_tokens = raw_title.split()
        title = " ".join(title_tokens[:30])
        if len(title) > 285:
            title = title[:285]
            if " " in title:
                title = title.rsplit(" ", 1)[0]

        # Enforce max 6 words in [Product Name] portion
        if "|" in title:
            parts = title.split("|")
            brand = parts[0].strip()
            product_name_words = parts[1].strip().split()
            if len(product_name_words) > 6:
                product_name_trimmed = " ".join(product_name_words[:6])
                title = f"{brand} | {product_name_trimmed}"

        # 🧼 Clean wrapping quotes/brackets
        title = clean_title(title)
         

        return title

    except Exception as e:
        logger.error(f"chatgpt_translate_title error: {e}")
        return product_title  # fallback

    
    
def chatgpt_translate(
    text: str, 
    custom_prompt: str = "", 
    target_language: str = "German",
    field_type: str = "description", 
    product_title: str = ""
) -> str:

    """
    Translate or rewrite product text using ChatGPT with a structured output format.

    Args:
        text (str): The text (usually product description) to translate or rewrite.
        custom_prompt (str): Additional user instructions for ChatGPT.
        target_language (str): The language code for translation (e.g. "en", "de").
        field_type (str): Type of content ("description", "title", etc.) – for potential future usage.
        product_title (str): An optional product title to pass as context to ChatGPT.

    Returns:
        str: The translated or rewritten text. Returns original text on failure.
    """
    if not text.strip():
        return text

    if not OPENAI_API_KEY:
        logging.error("[chatgpt_translate] No OPENAI_API_KEY found. Returning original text.")
        return text

    client = openai.OpenAI(api_key=OPENAI_API_KEY)

    # **Force ChatGPT to always follow the structure**
    system_instructions = (
        "You are an expert e-commerce copywriter. Clearly rewrite the provided product description "
        "into a structured format exactly as follows (strictly in the target language provided):\n\n"
        "Product Title: (Enticing, SEO-friendly title in format: '[Human Name] | [Product Name]')\n"
        "Short Introduction: (3–5 sentences to engage the buyer)\n\n"
        "Product Advantages:\n"
        "- [Feature Name]: [Benefit-driven detail that explains why the customer needs it.]\n"
        "- [Feature Name]: [Use power words like ‘luxurious’ or ‘perfect fit’ to create desire.]\n"
        "- [Feature Name]: [Link each feature to a real-life benefit. E.g. ‘Breathable fabric...’]\n"
        "- (Add more bullets if needed)\n\n"
        "💡 **Important**: bullet points must SELL, not just describe. Do NOT omit the product description.\n"
        "Call to Action: short, persuasive closing sentence.\n\n"
        "**IMPORTANT**: Respond exactly in this structure, no missing sections."
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
            n=1  # Single response 
        )

        ai_output = response.choices[0].message.content.strip()
        logging.info("✅ [chatgpt_translate] ChatGPT response received:\n%s", ai_output)

        return ai_output

    except Exception as e:
        logging.error(f"[chatgpt_translate] Error: {e}")
        return text  # Fallback
    

# ---> ADD THESE TWO FUNCTIONS (e.g., after chatgpt_translate) <---


def deepseek_translate_title(product_title: str, custom_prompt: str = "", target_language: str = "German") -> str:
    """Translate product title using DeepSeek API with formatting constraints."""
    # --- ADD Check for client ---
    if not deepseek_client:
        logger.error("❌ DeepSeek client is not initialized. Cannot translate title.")
        return product_title # Return original text if client not ready
        
    if not product_title.strip():
        return product_title

    # --- Simplified System Instructions ---
    system_instructions = (
        f"Translate the following product title into {target_language}. "
        f"Return ONLY the translated title in the exact format '[Human Name] | [Product Name]'. "
        f"ABSOLUTELY DO NOT add any introductory text, notes, markdown, quotes, or explanations. "
        f"Just output the final title string and nothing else."
    )
    # --- End Simplified System Instructions ---

    user_content = f"""
    Original Title: {product_title}

    Translate into {target_language}. Remember to only output the final title in the correct format.
    """
    # (Keep custom_prompt if needed, maybe append to user_content: f"\nUser Modifications: {custom_prompt}")

    messages = [
        {"role": "system", "content": system_instructions},
        {"role": "user", "content": user_content}
    ]

    try:
        # --- THIS IS THE LINE TO CHANGE ---
        # Change 'client' to 'deepseek_client'
        response = deepseek_client.chat.completions.create( 
            model="deepseek-chat",
            messages=messages,
            max_tokens=120
        )
        # --- End of change ---

        translated_title = response.choices[0].message.content.strip()
        logging.info("✅ DeepSeek Title Output:\n%s", translated_title) # Changed log message slightly

        return translated_title

    except Exception as e:
        logging.error(f"deepseek_translate_title error: {e}")
        # Optional: Add specific NameError check like in the other function if needed
        # if isinstance(e, NameError) and 'deepseek_client' in str(e):
        #      logger.error("❌❌❌ It seems 'deepseek_client' was used but not defined correctly at the top of the file.")
        return product_title  # Fallback

def deepseek_translate(
    text: str,
    custom_prompt: str = "",
    target_language: str = "German",
    style=None,
    product_title: str = "" # Added product_title argument
) -> str:
    """
    Translate product descriptions using the DeepSeek API, aiming for structured output.

    Args:
        text (str): The product description text to translate.
        custom_prompt (str): Additional user instructions.
        target_language (str): Target language (e.g., "German", "French").
        style: Optional style parameter (currently unused in logic).
        product_title (str): Optional product title for context.

    Returns:
        str: The translated text, ideally structured, or original text on failure.
    """
    # 1. Check if the deepseek_client was initialized
    if not deepseek_client:
        logger.error("❌ DeepSeek client is not initialized. Cannot translate using DeepSeek.")
        return text # Return original text if client is not available

    # 2. Check if input text is empty
    if not text.strip():
        logger.warning("⚠️ Input text for DeepSeek translation is empty.")
        return text

    # 3. Define System Instructions (asking for structured output)
    system_instructions = (
        "You are an expert e-commerce copywriter. Rewrite the product description "
        f"into fluent, persuasive {target_language} in a structured format exactly as follows:\n\n"
        "Product Title: [Create an enticing, SEO-friendly title in the target language based on the original title/description]\n"
        "Short Introduction: [Write 3–5 engaging sentences in the target language introducing the product]\n\n"
        "Product Advantages:\n"
        "- [Feature Name in target language]: [Benefit-driven detail in the target language explaining why the customer needs it.]\n"
        "- [Feature Name in target language]: [Use power words like ‘luxurious’ or ‘perfect fit’ in the target language to create desire.]\n"
        "- [Feature Name in target language]: [Link each feature to a real-life benefit in the target language. E.g. ‘Breathable fabric...’]\n"
        "- (Add more relevant bullet points as needed based on the original description)\n\n"
        "Call to Action: [Write a short, persuasive closing sentence in the target language]\n\n"
        "**IMPORTANT**: Respond *only* with the structured text in {target_language}. Strictly follow this structure with the exact English labels (Product Title:, Short Introduction:, Product Advantages:, Call to Action:). Do not add any extra explanations before or after."
    )

    # 4. Define User Content (providing original text and context)
    user_content = f"""
Original Description:
{text}

Original Title (for context):
{product_title}

User Custom Instructions:
{custom_prompt}

Translate the original description into {target_language} following the structured format specified precisely.
"""

    # 5. Prepare messages for the API
    messages = [
        {"role": "system", "content": system_instructions},
        {"role": "user", "content": user_content}
    ]

    # 6. Make the API Call
    try:
        logger.info(f"Attempting DeepSeek API call for description translation to {target_language}...")
        response = deepseek_client.chat.completions.create( # Use deepseek_client
            model="deepseek-chat",
            messages=messages,
            temperature=0.5, # Slightly lowered temperature for potentially better structure adherence
            max_tokens=1500 # Adjust as needed
        )

        raw_output = response.choices[0].message.content.strip()
        # Log the raw output critically for debugging formatting issues
        logging.critical(f"🔥🔥🔥 RAW DeepSeek Output:\n---\n{raw_output}\n---")

        translated_text = raw_output
        logger.info(f"✅ DeepSeek Translation Output received (length: {len(translated_text)}).")

        return translated_text

    # 7. Handle Exceptions
    except Exception as e:
        logger.error(f"❌ deepseek_translate error: {e}")
        # Check if it's a NameError related to the client, although the check at the start should prevent this
        if isinstance(e, NameError) and 'deepseek_client' in str(e):
             logger.error("❌❌❌ It seems 'deepseek_client' variable was used but not properly defined/initialized.")
        return text  # Fallback to original text on any error

    except Exception as e:
        logging.error(f"deepseek_translate error: {e}")
        return text  # Fallback
    
# ---> END ADDED FUNCTIONS <---    

# ---------------------------------- #
# apply_translation_method
# ---------------------------------- #
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
    logging.info("Using this apply_translation_method. The one of tranlsation.py")
    """
    Translates text using the chosen method (google, deepl, or chatgpt).
    If source_lang=='auto' and method=='google', attempts language detection from `description`.

    Args:
        original_text (str): The text to translate (title, description, etc.).
        method (str): "google", "deepl", or "chatgpt".
        custom_prompt (str): Additional instructions for ChatGPT (if used).
        source_lang (str): Source language (e.g. "auto", "en", "de", ...).
        target_lang (str): Target language code (e.g. "de", "en", ...).
        product_title (str): Optional product title for ChatGPT context.
        field_type (str): e.g. "title", "description" – for logging or future usage.
        description (str): A larger chunk of text (e.g. body_html) to help detect the language if `source_lang=="auto"`.

    Returns:
        str: The translated text, or original if something fails.
    """
    logging.info(
        "[apply_translation_method] START: method=%s, source_lang=%s, target_lang=%s, "
        "field_type=%s, has_description=%s",
        method,
        source_lang,
        target_lang,
        field_type,
        bool(description)
    )

    if not original_text or not method:
        logging.warning("⚠️ [apply_translation_method] Missing text or method => returning original.")
        return original_text

    try:
        method_config = method if isinstance(method, dict) else {"method": str(method)}
        method_lower = method_config.get("method", "").lower()
        prompt_to_use = method_config.get("prompt", custom_prompt) # Prioritize prompt from method dict
        translated_text = original_text

        # If original_text is a list, handle each item
        if isinstance(original_text, list):
            logging.info("[apply_translation_method] original_text is a list => applying recursively.")
            return [
                apply_translation_method(
                    text,
                    method,
                    custom_prompt,
                    source_lang,
                    target_lang,
                    product_title=product_title,
                    field_type=field_type,
                    description=description
                )
                for text in original_text
            ]

        method_lower = method.lower()

        # A) ChatGPT
        if method_lower == "chatgpt":
            logging.info("[apply_translation_method] Using ChatGPT => target_lang=%s", target_lang)
            translated_text = chatgpt_translate(original_text, custom_prompt, target_lang, field_type, product_title)

        # B) Google
        elif method_lower == "google":
            logging.info("[apply_translation_method] Using Google => source=%s, target=%s", source_lang, target_lang)
            # If user said "auto" & we have a description => detect
            if source_lang.lower() == "auto" and description:
                logging.info("[apply_translation_method] source_lang='auto' => attempting detection from description.")
                desc = description.strip()
                if desc:
                    from langdetect import detect, LangDetectException
                    try:
                        detected_lang = detect(desc)
                        logging.info("[apply_translation_method] Detected => '%s' from description", detected_lang)
                        if detected_lang != "auto":
                            source_lang = detected_lang
                    except LangDetectException:
                        logging.info("[apply_translation_method] LangDetectException => remain 'auto'")
                else:
                    logging.info("[apply_translation_method] description empty => remain 'auto'")

            # Now call google_translate
            logging.info("[apply_translation_method] final google_translate => source='%s' to '%s'", source_lang, target_lang)
            translated_text = google_translate(original_text, source_lang, target_lang)

        # C) DeepL
        elif method_lower == "deepl":
            logging.info("[apply_translation_method] Using DeepL => source=%s, target=%s", source_lang, target_lang)
            translated_text = deepl_translate(original_text, source_lang, target_lang)

        # ---> ADD THIS ELIF BLOCK <---
        elif method_lower == "deepseek":
             logging.info(f"[apply_translation_method] Dispatching to DeepSeek (Field: {field_type}, Target: {target_lang})")
             # Use descriptive language name if needed, else use code
             descriptive_lang = language_code_to_descriptive(target_lang)
             if field_type == 'title':
                  # Ensure deepseek_translate_title is defined above
                  translated_text = deepseek_translate_title(original_text, custom_prompt=prompt_to_use, target_language=descriptive_lang)
             else:
                  # Ensure deepseek_translate is defined above
                  translated_text = deepseek_translate(original_text, custom_prompt=prompt_to_use, target_language=descriptive_lang, product_title=product_title)
        # ---> END ADDED BLOCK <---    

        # D) Unknown
        else:
            logging.warning("[apply_translation_method] Unknown method='%s' => returning original.", method)

        logging.info("✅ [apply_translation_method] complete: '%s...' => '%s...'",
                     original_text[:50], translated_text[:50])
        return translated_text

    except Exception as e:
        logging.error("❌ [apply_translation_method] Translation failed: %s", e)
        return original_text

    
def parse_ai_description(ai_text, language='en'):
    """
    Parse an AI-generated text (ChatGPT or other) that should contain a structured format:
    - Title: ...
    - Introduction: ...
    - Features: ...
    - CTA: ...

    Args:
        ai_text (str): The full AI response text containing the structured content.
        language (str): Optional language code (not heavily used here, but reserved for future expansions).

    Returns:
        dict: {
          "title": str,
          "introduction": str,
          "features": list of str,
          "cta": str
        }
    """
    # Initialize defaults
    title = intro = cta = ""
    features = []

    # 1. Extract Title
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
        # If not found by label, try the line after the title
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

    # Split the features section into individual bullet points
    for line in features_section.splitlines():
        line = line.strip()
        if not line:
            continue
        # Identify bullet point lines (dash, asterisk, or number)
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
        # If "CTA" label not found, attempt last line if it's not used above
        lines = ai_text.strip().splitlines()
        if lines:
            last_line = lines[-1].strip()
            if last_line and last_line.lower().startswith(('cta', 'call to action')):
                # If the last line has 'CTA' text without colonpython3 a
                cta = last_line.split(':', 1)[-1].strip() if ':' in last_line else last_line
            elif last_line and last_line not in title and last_line not in intro and last_line not in " ".join(features):
                cta = last_line

    return {
        "title": title.strip(),
        "introduction": intro.strip(),
        "features": features,
        "cta": cta.strip()
    }

# ---------------------------------- #
# apply_method
# ---------------------------------- #
def apply_method( 
    text: str,
    method: str,
    custom_prompt: str = "",
    source_language: str = "auto",
    target_language: str = "de",
    field_type: str = "description"
) -> str:
    """
    A simple dispatch function for text translation / rewriting:
        - "google" => calls google_translate(...)
        - "deepl"  => calls deepl_translate(...)
        - "chatgpt" => calls chatgpt_translate(...)
    (No chaining references or auto-detection logic here.)

    Args:
        text (str): The text to translate or rewrite.
        method (str): "google", "deepl", or "chatgpt".
        custom_prompt (str): Additional instructions for ChatGPT usage.
        source_language (str): The source language (default 'auto' for Google).
        target_language (str): The target language code (e.g., 'en', 'de').
        field_type (str): The content type (e.g. 'description', 'title', etc.) – not heavily used here.

    Returns:
        str: The translated or rewritten text. Returns original if unrecognized method.
    """
    method_lower = method.lower()
    logging.info(f"[apply_method] method={method_lower}, source={source_language}, target={target_language}, field_type={field_type}")

    if method_lower == "google":
        # Google tries 'auto' if source_language='auto'. We do NOT do langdetect here.
        return google_translate(text, source_language=source_language, target_language=target_language)

    elif method_lower == "deepl":
        # DeepL typically wants uppercase target_lang
        return deepl_translate(
            text,
            source_language=source_language,
            target_language=target_language.upper()
        )

    elif method_lower == "chatgpt":
        # e.g., 'de' => 'German'
        descriptive_lang = language_code_to_descriptive(target_language)
        return chatgpt_translate(
            text,
            custom_prompt=custom_prompt,
            target_language=descriptive_lang,
            field_type=field_type
        )

    else:
        # Unknown method => return text unmodified
        logging.warning(f"[apply_method] Unrecognized method '{method}'. Returning original text.")
        return text
