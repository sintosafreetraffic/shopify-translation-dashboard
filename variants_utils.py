# variants_utils.py (corrected with global ID handling and translation)
import logging
from translation import google_translate
from translation import deepl_translate
from translation import apply_translation_method
import json
import requests
import os
from langdetect import detect
from deep_translator import GoogleTranslator
from deep_translator import DeeplTranslator

SHOPIFY_STORE_URL = os.getenv("SHOPIFY_STORE_URL")
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")

GRAPHQL_URL = f"https://{SHOPIFY_STORE_URL}/admin/api/2023-04/graphql.json"
HEADERS = {
    "X-Shopify-Access-Token": SHOPIFY_API_KEY,
    "Content-Type": "application/json",
}

logger = logging.getLogger(__name__)

def get_product_option_values(product_gid):
    query = """
    query getProductOptions($productId: ID!) {
      product(id: $productId) {
        options {
          id
          name
          optionValues { id name }
        }
      }
    }
    """

    variables = {"productId": product_gid}  # ✅ Ensure it's a global ID format

    response = requests.post(GRAPHQL_URL, headers=HEADERS, json={
        "query": query,
        "variables": variables
    })
    data = response.json()

    if "errors" in data or not data.get("data", {}).get("product"):
        logger.error(f"❌ Error retrieving product options for {product_gid}: {data}")
        return None

    return data["data"]["product"]["options"]


COLOR_NAME_MAP = {
    "Black": {"de": "Schwarz", "es": "Negro", "fr": "Noir", "da": "Sort"},
    "White": {"de": "Weiß", "es": "Blanco", "fr": "Blanc", "da": "Hvid"},
    "Gray": {"de": "Grau", "es": "Gris", "fr": "Gris", "da": "Grå"},
    "Dark Gray": {"de": "Dunkelgrau", "es": "Gris oscuro", "fr": "Gris foncé", "da": "Mørkegrå"},
    "Light Gray": {"de": "Hellgrau", "es": "Gris claro", "fr": "Gris clair", "da": "Lysegrå"},
    "Beige": {"de": "Beige", "es": "Beige", "fr": "Beige", "da": "Beige"},
    "Dark Beige": {"de": "Dunkelbeige", "es": "Beige oscuro", "fr": "Beige foncé", "da": "Mørk beige"},
    "Light Beige": {"de": "Hellbeige", "es": "Beige claro", "fr": "Beige clair", "da": "Lys beige"},
    "Blue": {"de": "Blau", "es": "Azul", "fr": "Bleu", "da": "Blå"},
    "Dark Blue": {"de": "Dunkelblau", "es": "Azul oscuro", "fr": "Bleu foncé", "da": "Mørkeblå"},
    "Light Blue": {"de": "Hellblau", "es": "Azul claro", "fr": "Bleu clair", "da": "Lyseblå"},
    "Navy Blue": {"de": "Marineblau", "es": "Azul marino", "fr": "Bleu marine", "da": "Marineblå"},
    "Green": {"de": "Grün", "es": "Verde", "fr": "Vert", "da": "Grøn"},
    "Dark Green": {"de": "Dunkelgrün", "es": "Verde oscuro", "fr": "Vert foncé", "da": "Mørkegrøn"},
    "Light Green": {"de": "Hellgrün", "es": "Verde claro", "fr": "Vert clair", "da": "Lysegrøn"},
    "Olive": {"de": "Oliv", "es": "Oliva", "fr": "Olive", "da": "Oliven"},
    "Red": {"de": "Rot", "es": "Rojo", "fr": "Rouge", "da": "Rød"},
    "Pink": {"de": "Rosa", "es": "Rosa", "fr": "Rose", "da": "Lyserød"},
    "Dark Pink": {"de": "Dunkelrosa", "es": "Rosa oscuro", "fr": "Rose foncé", "da": "Mørk rosa"},
    "Light Pink": {"de": "Hellrosa", "es": "Rosa claro", "fr": "Rose clair", "da": "Lys pink"},
    "Yellow": {"de": "Gelb", "es": "Amarillo", "fr": "Jaune", "da": "Gul"},
    "Dark Yellow": {"de": "Dunkelgelb", "es": "Amarillo oscuro", "fr": "Jaune foncé", "da": "Mørkegul"},
    "Light Yellow": {"de": "Hellgelb", "es": "Amarillo claro", "fr": "Jaune clair", "da": "Lysegul"},
    "Mustard Yellow": {"de": "Senfgelb", "es": "Amarillo mostaza", "fr": "Jaune moutarde", "da": "Sennepsgul"},
    "Orange": {"de": "Orange", "es": "Naranja", "fr": "Orange", "da": "Orange"},
    "Dark Orange": {"de": "Dunkelorange", "es": "Naranja oscuro", "fr": "Orange foncé", "da": "Mørkeorange"},
    "Light Orange": {"de": "Hellorange", "es": "Naranja claro", "fr": "Orange clair", "da": "Lys orange"},
    "Peach Orange": {"de": "Pfirsichorange", "es": "Naranja melocotón", "fr": "Orange pêche", "da": "Fersken orange"},
    "Purple": {"de": "Lila", "es": "Morado", "fr": "Violet", "da": "Lilla"},
    "Dark Purple": {"de": "Dunkellila", "es": "Púrpura oscuro", "fr": "Violet foncé", "da": "Mørkelilla"},
    "Light Purple": {"de": "Helllila", "es": "Púrpura claro", "fr": "Violet clair", "da": "Lys lilla"},
    "Lavender Purple": {"de": "Lavendel", "es": "Lavanda", "fr": "Lavande", "da": "Lavendel"},
    "Purple": {"de": "Lila", "es": "Morado", "fr": "Violet", "da": "Lilla"},
    "Magenta Pink": {"de": "Magenta", "es": "Rosa magenta", "fr": "Rose magenta", "da": "Magenta"},
    "Brown": {"de": "Braun", "es": "Marrón", "fr": "Marron", "da": "Brun"},
    "Dark Brown": {"de": "Dunkelbraun", "es": "Marrón oscuro", "fr": "Marron foncé", "da": "Mørkebrun"},
    "Light Brown": {"de": "Hellbraun", "es": "Marrón claro", "fr": "Marron clair", "da": "Lys brun"},
    "Lavender Purple": {"de": "Lavendel", "es": "Lavanda", "fr": "Lavande", "da": "Lavendel"},
    "Navy": {"de": "Marine", "es": "Marina", "fr": "Marine", "da": "Marine"},
    "Sky blue": {"de": "Himmelblau", "es": "Azul cielo", "fr": "Blue ciel", "da": "Himmelblå"},
    "Coffee": {"de": "Kaffee", "es": "Café", "fr": "Café", "da": "Kaffe"}
}

def get_predefined_translation(original_text, target_language):
    """
    Check if the original text is a known color and return the predefined translation.
    Works for bidirectional lookup (any language → target language).
    Ensures that translation is different before returning.
    """
    original_text_lower = original_text.strip().lower()

    for english_name, translations in COLOR_NAME_MAP.items():
        # Check if the input matches any known translation (across all languages)
        if original_text_lower in [val.lower() for val in translations.values()]:
            mapped_translation = translations.get(target_language)  # Get mapped translation
            
            if mapped_translation and mapped_translation.lower() != original_text_lower:
                return mapped_translation  # ✅ Return only if different from input
            
    return None  # No valid predefined translation found


def detect_language(text):
    """Detect the language of a given text using langdetect."""
    try:
        detected_lang = detect(text)
        print(f"🔍 Detected language: {detected_lang}")
        return detected_lang
    except Exception as e:
        print(f"⚠️ Language detection failed: {e}")
        return "en"  # Default to English if detection fails


# Update product option values with translations
def update_product_option_values(product_gid, option, target_language, source_language="auto", translation_method="None"):
    translated_values = []

    # ✅ Known sizes that should NOT be translated
    KNOWN_SIZES = {"XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL", "XXXXL"}

    original_option_name = option["name"].strip()

    # ✅ 1️⃣ Ensure Option Name is Translated Properly
    logging.info(f"🌍 Translating option title '{original_option_name}' from '{source_language}' to '{target_language}'")

    translated_option_name = apply_translation_method(
        original_text=original_option_name,
        method=translation_method,
        custom_prompt="",
        source_lang=source_language,  # ✅ Explicitly pass source language (auto if not chosen)
        target_lang=target_language
    )

    translated_values = []

    for value in option["optionValues"]:
        original_text = value["name"].strip()

        # 🔒 Skip known sizes (S, M, L, etc.)
        if original_text.upper() in KNOWN_SIZES:
            logging.info(f"🔒 Skipping translation for universal size '{original_text}'")
            translated_values.append({"id": value["id"], "name": original_text})
            continue

        # ✅ Use predefined color translations if available
        predefined_translation = get_predefined_translation(original_text, target_language)
        if predefined_translation:
            logging.info(f"🔄 '{original_text}' → '{predefined_translation}' (via predefined color map)")
            translated_values.append({"id": value["id"], "name": predefined_translation})
            continue  # 🚀 Skip API translation since we already mapped it!
        else:
            logging.warning(f"⚠️ Predefined translation did not change '{original_text}', retrying API translation...")
        # 🌍 Perform API translation (Google or DeepL)
        logging.info(f"🌍 Translating '{original_text}' from '{source_language}' to '{target_language}' using {translation_method}")

        # ✅ DeepL does NOT support "auto", so detect language first if needed
        if translation_method == "deepl":
            if source_language == "auto":
                detected_lang = detect_language(original_text)  # ✅ Function to detect language
                logging.info(f"🔍 Auto-detected source language: '{detected_lang}'")
                source_language = detected_lang  # Use detected language

            translated_name = deepl_translate(original_text, source_language, target_language)
        else:
            translated_name = google_translate(original_text, source_language, target_language)

        # 🚨 Retry translation if unchanged (but only for API translations, NOT predefined ones!)
        if translated_name.lower() == original_text.lower():
            logging.warning(f"⚠️ Translation unchanged for '{original_text}', retrying with slight modification...")

            # 🔄 Check predefined color map again before retrying
            retry_predefined_translation = get_predefined_translation(original_text, target_language)
            if retry_predefined_translation and retry_predefined_translation != original_text:
                logging.info(f"✅ Retried translation skipped: '{original_text}' already mapped to '{retry_predefined_translation}'")
                translated_name = retry_predefined_translation  # **Force use of predefined translation**
            else:
                logging.warning(f"⚠️ Translation unchanged for '{original_text}', retrying with slight modification...")
                retry_text = original_text + " "  # **Force retranslation**
                if translation_method == "deepl":
                    translated_name = deepl_translate(retry_text, source_language, target_language)
                else:
                    translated_name = google_translate(retry_text, source_language, target_language)

        logging.info(f"🔄 '{original_text}' → '{translated_name}'")
        translated_values.append({"id": value["id"], "name": translated_name})

    # ✅ Shopify GraphQL mutation
    mutation = """
    mutation updateProductOption($productId: ID!, $option: OptionUpdateInput!, $optionValuesToUpdate: [OptionValueUpdateInput!]!) {
      productOptionUpdate(productId: $productId, option: $option, optionValuesToUpdate: $optionValuesToUpdate) {
        userErrors { field message }
      }
    }
    """

    variables = {
        "productId": product_gid,
        "option": {"id": option["id"], "name": translated_option_name},  # ✅ Use the translated option name
        "optionValuesToUpdate": translated_values,
    }

    response = requests.post(GRAPHQL_URL, headers=HEADERS, json={"query": mutation, "variables": variables})
    data = response.json()

    if "errors" in data or data["data"]["productOptionUpdate"]["userErrors"]:
        logging.error(f"❌ Error updating options: {data}")
        return False
    else:
        logging.info(f"✅ Successfully updated options for {product_gid}")
        return True