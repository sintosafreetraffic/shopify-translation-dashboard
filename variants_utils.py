# variants_utils.py (corrected with global ID handling and translation)
import logging
from translation import google_translate
from translation import deepl_translate
from translation import apply_translation_method
import json
import html
import requests
import os
from langdetect import detect
from deep_translator import GoogleTranslator
from deep_translator import DeeplTranslator

logging.basicConfig(level=logging.INFO)


SHOPIFY_STORE_URL = os.getenv("SHOPIFY_STORE_URL")
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")

GRAPHQL_URL = f"https://{SHOPIFY_STORE_URL}/admin/api/2023-04/graphql.json"
HEADERS = {
    "X-Shopify-Access-Token": SHOPIFY_API_KEY,
    "Content-Type": "application/json",
}

logger = logging.getLogger(__name__)

def clean_translated_text(text: str) -> str:
    """
    Clean up HTML-escaped characters from a translated string.

    Args:
        text (str): The translated string (possibly with HTML entities)

    Returns:
        str: Unescaped, cleaned string
    """
    if not text:
        return text

    text = html.unescape(text)       # Handles &amp;, &lt;, &gt;, etc.
    text = text.strip()              # Remove leading/trailing whitespace
    return text

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

    payload = {
    "query": query,
    "variables": variables
}

    logging.info("📦 Final Payload Sent to Shopify:")
    logging.info(json.dumps(payload, indent=2, ensure_ascii=False))  # just for log output
    response = requests.post(
    GRAPHQL_URL,
    headers=HEADERS,
    data=json.dumps(payload, ensure_ascii=False),  # ✅ key change here
)



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
    Ensure predefined translations work properly before falling back to API translations.
    """
    original_text_lower = original_text.strip().lower()

    for english_name, translations in COLOR_NAME_MAP.items():
        # ✅ First, check if original text matches the English name directly
        if original_text_lower == english_name.lower():
            return translations.get(target_language, english_name)  # Return mapped or default to English name

        # ✅ Second, check if the original text matches any known translations in other languages
        if original_text_lower in [val.lower() for val in translations.values()]:
            mapped_translation = translations.get(target_language, english_name)  # Default to English name if missing
            return mapped_translation if mapped_translation.lower() != original_text_lower else english_name

    return None  # No predefined translation found


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
def update_product_option_values(product_gid, option, target_language, source_language="auto", translation_method="google"):
    translated_values = []
    
    logging.info(f"🔄 [START] Translating Option: {option['name']} for Product ID: {product_gid}")
    logging.debug(f"📦 Raw Option JSON: {json.dumps(option, indent=2, ensure_ascii=False)}")

    logging.info(f"🔄 Translating Option: {option['name']} for Product ID: {product_gid}")

    # ✅ Skip known sizes (S, M, L) from translation
    KNOWN_SIZES = {"XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL", "XXXXL"}

    original_option_name = option["name"].strip()

    # ✅ Translate Option Name
    translated_option_name = clean_translated_text(apply_translation_method(
        original_text=original_option_name,
        method=translation_method,
        custom_prompt="",
        source_lang=source_language,
        target_lang=target_language
    ))
    translated_option_name = clean_translated_text(translated_option_name)  # SECOND cleanup!


    logger.info(f"🔍 [DEBUG] Translated Option Name (before second cleaning): '{translated_option_name}'")

    logging.info(f"🌍 Final Option Name: '{original_option_name}' → '{translated_option_name}'")
        # 🔧 Fix for HTML entities in the option name too (e.g. "Pink &amp; White")
    logging.info(f"🌍 Translated Option Name: '{original_option_name}' → '{translated_option_name}'")

    for value in option["optionValues"]:
        original_text = value["name"].strip()
        logging.info(f"🛠️ Processing Option Value: '{original_text}'")

        # ✅ Skip universal sizes (e.g. "S", "M", "L")
        if original_text.upper() in KNOWN_SIZES:
            logging.info(f"🔒 Skipping known size '{original_text}'")
            translated_values.append({"id": value["id"], "name": original_text})
            continue

        # ✅ Check predefined color translations
        predefined_translation = get_predefined_translation(original_text, target_language)
        if predefined_translation:
            logging.info(f"✅ Predefined translation found: '{original_text}' → '{predefined_translation}'")
            translated_name = predefined_translation
        else:
            # 🚀 No predefined match, use AI translation
            logging.info(f"🚀 No predefined match for '{original_text}', using {translation_method} translation...")

            translated_name = clean_translated_text(apply_translation_method(
                original_text=original_text,
                method=translation_method,
                custom_prompt="",
                source_lang=source_language,
                target_lang=target_language
            ))
            logger.info(f"🔍 [DEBUG] Translated (before cleaning again): '{translated_name}'")
            translated_name = clean_translated_text(translated_option_name)  # SECOND cleanup!



            logging.info(f"🌍 AI Translated '{original_text}' → '{translated_name}'")

        # ✅ Append final translation to list
        clean_name = clean_translated_text(translated_name)
        if clean_name != translated_name:
            logging.warning(f"🧼 HTML entity cleanup: '{translated_name}' → '{clean_name}'")

        logging.info(f"✅ Final Value: '{original_text}' → '{clean_name}'")    
        translated_values.append({"id": value["id"], "name": clean_name})

    # ✅ Final debug log to verify translations
    logging.info(f"📦 Final Translated Option Name: {translated_option_name}")
    logging.info(f"📦 Final Translated Values: {translated_values}")

    # ✅ Shopify GraphQL mutation to update product options
    mutation = """
    mutation updateProductOption($productId: ID!, $option: OptionUpdateInput!, $optionValuesToUpdate: [OptionValueUpdateInput!]!) {
      productOptionUpdate(productId: $productId, option: $option, optionValuesToUpdate: $optionValuesToUpdate) {
        userErrors { field message }
      }
    }
    """

    variables = {
        "productId": product_gid,
        "option": {"id": option["id"], "name": translated_option_name},
        "optionValuesToUpdate": translated_values,
    }

    payload = {
        "query": mutation,
        "variables": variables
    }
    logging.info("📦 Final Payload Sent to Shopify:")
    logging.info(json.dumps(payload, indent=2, ensure_ascii=False))  # just for log output
    response = requests.post(
    GRAPHQL_URL,
    headers=HEADERS,
    data=json.dumps(payload, ensure_ascii=False),  # ✅ key change here
)



    data = response.json()

        # 🔍 Log the full Shopify response
    logging.info(f"📤 Shopify GraphQL Mutation Sent: {json.dumps(variables, indent=2)}")
    logging.info(f"📥 Shopify Response: {json.dumps(data, indent=2)}")


    if "errors" in data or data["data"]["productOptionUpdate"]["userErrors"]:
        logging.error(f"❌ Error updating options: {data}")
        return False
    else:
        logging.info(f"✅ Successfully updated options for {product_gid}")
        return True
