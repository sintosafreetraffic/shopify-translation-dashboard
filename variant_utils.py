# File: variant_utils.py
print(f"📁 Loaded: {__name__} from {os.path.abspath(__file__)}")


import logging
import json
import requests
import os
import re
import html # For unescape

# Assume these utility modules will be created and import necessary functions
try:
    import shopify_utils # Needs shopify_graphql_request
    import translation_utils # Needs apply_translation_method
    import text_processing_utils # Needs clean_translated_text
except ImportError as e:
     print(f"WARNING: Could not import all utility modules in variant_utils: {e}")

# --- Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
logger = logging.getLogger(__name__)
logger.info(f"📁 Loaded: variants_utils from {os.path.abspath(__file__)}")

# --- Constants & Mappings (Moved from export_variants_utils.py) ---
COLOR_NAME_MAP = {
    "Black": {"de": "Schwarz", "es": "Negro", "fr": "Noir", "da": "Sort", "nl": "Zwart"},
    "White": {"de": "Weiß", "es": "Blanco", "fr": "Blanc", "da": "Hvid", "nl": "Wit"},
    "Gray": {"de": "Grau", "es": "Gris", "fr": "Gris", "da": "Grå", "nl": "Grijs"},
    "Dark Gray": {"de": "Dunkelgrau", "es": "Gris oscuro", "fr": "Gris foncé", "da": "Mørkegrå", "nl": "Donkergrijs"},
    "Light Gray": {"de": "Hellgrau", "es": "Gris claro", "fr": "Gris clair", "da": "Lysegrå", "nl": "Lichtgrijs"},
    "Beige": {"de": "Beige", "es": "Beige", "fr": "Beige", "da": "Beige", "nl": "Beige"},
    "Dark Beige": {"de": "Dunkelbeige", "es": "Beige oscuro", "fr": "Beige foncé", "da": "Mørk beige", "nl": "Donkerbeige"},
    "Light Beige": {"de": "Hellbeige", "es": "Beige claro", "fr": "Beige clair", "da": "Lys beige", "nl": "Lichtbeige"},
    "Blue": {"de": "Blau", "es": "Azul", "fr": "Bleu", "da": "Blå", "nl": "Blauw"},
    "Dark Blue": {"de": "Dunkelblau", "es": "Azul oscuro", "fr": "Bleu foncé", "da": "Mørkeblå", "nl": "Donkerblauw"},
    "Light Blue": {"de": "Hellblau", "es": "Azul claro", "fr": "Bleu clair", "da": "Lyseblå", "nl": "Lichtblauw"},
    "Navy Blue": {"de": "Marineblau", "es": "Azul marino", "fr": "Bleu marine", "da": "Marineblå", "nl": "Marineblauw"},
    "Green": {"de": "Grün", "es": "Verde", "fr": "Vert", "da": "Grøn", "nl": "Groen"},
    "Dark Green": {"de": "Dunkelgrün", "es": "Verde oscuro", "fr": "Vert foncé", "da": "Mørkegrøn", "nl": "Donkergroen"},
    "Light Green": {"de": "Hellgrün", "es": "Verde claro", "fr": "Vert clair", "da": "Lysegrøn", "nl": "Lichtgroen"},
    "Olive": {"de": "Oliv", "es": "Oliva", "fr": "Olive", "da": "Oliven", "nl": "Olijfgroen"},
    "Red": {"de": "Rot", "es": "Rojo", "fr": "Rouge", "da": "Rød", "nl": "Rood"},
    "Pink": {"de": "Rosa", "es": "Rosa", "fr": "Rose", "da": "Lyserød", "nl": "Roze"},
    "Dark Pink": {"de": "Dunkelrosa", "es": "Rosa oscuro", "fr": "Rose foncé", "da": "Mørk rosa", "nl": "Donkerroze"},
    "Light Pink": {"de": "Hellrosa", "es": "Rosa claro", "fr": "Rose clair", "da": "Lys pink", "nl": "Lichtroze"},
    "Yellow": {"de": "Gelb", "es": "Amarillo", "fr": "Jaune", "da": "Gul", "nl": "Geel"},
    "Dark Yellow": {"de": "Dunkelgelb", "es": "Amarillo oscuro", "fr": "Jaune foncé", "da": "Mørkegul", "nl": "Donkergeel"},
    "Light Yellow": {"de": "Hellgelb", "es": "Amarillo claro", "fr": "Jaune clair", "da": "Lysegul", "nl": "Lichtgeel"},
    "Mustard Yellow": {"de": "Senfgelb", "es": "Amarillo mostaza", "fr": "Jaune moutarde", "da": "Sennepsgul", "nl": "Mosterdgeel"},
    "Orange": {"de": "Orange", "es": "Naranja", "fr": "Orange", "da": "Orange", "nl": "Oranje"},
    "Dark Orange": {"de": "Dunkelorange", "es": "Naranja oscuro", "fr": "Orange foncé", "da": "Mørkeorange", "nl": "Donkeroranje"},
    "Light Orange": {"de": "Hellorange", "es": "Naranja claro", "fr": "Orange clair", "da": "Lys orange", "nl": "Lichtoranje"},
    "Peach Orange": {"de": "Pfirsichorange", "es": "Naranja melocotón", "fr": "Orange pêche", "da": "Fersken orange", "nl": "Perzikoranje"},
    "Purple": {"de": "Lila", "es": "Morado", "fr": "Violet", "da": "Lilla", "nl": "Paars"},
    "Dark Purple": {"de": "Dunkellila", "es": "Púrpura oscuro", "fr": "Violet foncé", "da": "Mørkelilla", "nl": "Donkerpaars"},
    "Light Purple": {"de": "Helllila", "es": "Púrpura claro", "fr": "Violet clair", "da": "Lys lilla", "nl": "Lichtpaars"},
    "Lavender Purple": {"de": "Lavendel", "es": "Lavanda", "fr": "Lavande", "da": "Lavendel", "nl": "Lavendel"},
    "Magenta Pink": {"de": "Magenta", "es": "Rosa magenta", "fr": "Rose magenta", "da": "Magenta", "nl": "Magenta"},
    "Brown": {"de": "Braun", "es": "Marrón", "fr": "Marron", "da": "Brun", "nl": "Bruin"},
    "Dark Brown": {"de": "Dunkelbraun", "es": "Marrón oscuro", "fr": "Marron foncé", "da": "Mørkebrun", "nl": "Donkerbruin"},
    "Light Brown": {"de": "Hellbraun", "es": "Marrón claro", "fr": "Marron clair", "da": "Lys brun", "nl": "Lichtbruin"},
    "Navy": {"de": "Marine", "es": "Marina", "fr": "Marine", "da": "Marine", "nl": "Marine"},
    "Sky blue": {"de": "Himmelblau", "es": "Azul cielo", "fr": "Blue ciel", "da": "Himmelblå", "nl": "Hemelsblauw"},
    "Coffee": {"de": "Kaffee", "es": "Café", "fr": "Café", "da": "Kaffe", "nl": "Koffie"}
}

SIZE_NAME_MAP = {
    "Size": {"de": "Größe", "es": "Tamaño", "fr": "Taille", "da": "Størrelse", "nl": "Maat"},
    "Sizes": {"de": "Größen", "es": "Tamaños", "fr": "Tailles", "da": "Størrelser", "nl": "Maten"},
}

# Universal sizes to skip translation
KNOWN_SIZES = {"XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL", "XXXXL", "2XL", "3XL", "4XL"}

# --- Helper Functions ---

def get_predefined_translation(original_text, target_language):
    """
    Try to translate a string using predefined color or size maps.
    Also handles compound values like 'Pink and Black'.
    Returns translated string or None if no predefined match.
    """
    if not original_text or not target_language: return None

    original_text_clean = original_text.strip()
    original_text_lower = original_text_clean.lower()

    # Helper to check maps
    def _match_predefined_maps(text_lower, english_map):
        for english_name, translations in english_map.items():
            if text_lower == english_name.lower():
                return translations.get(target_language, english_name) # Return target or English original
            for lang, translated_value in translations.items():
                 # Check if input IS already a known translation in ANY language
                 if text_lower == translated_value.strip().lower():
                     # If it matches the target language, return it
                     if lang == target_language: return translated_value
                     # If it matches another language, return the TARGET translation for the English key
                     else: return translations.get(target_language, english_name)
        return None

    # Try single color/size/name direct match
    single_match = _match_predefined_maps(original_text_lower, COLOR_NAME_MAP) \
                or _match_predefined_maps(original_text_lower, SIZE_NAME_MAP)
    if single_match:
        logger.debug(f"Predefined match for '{original_text_clean}' -> '{single_match}'")
        return single_match

    # Try compound color names (e.g., "Pink & Black")
    # More robust separator splitting
    separators = r"\s*(?:and|und|et|y|en|&|\+|\/|,)\s*" # Handle spaces around separators
    parts = re.split(separators, original_text_clean, flags=re.IGNORECASE)

    if len(parts) > 1: # Potential compound name
        translated_parts = []
        all_parts_found = True
        for part in parts:
            part_clean = part.strip()
            if not part_clean: continue

            part_match = _match_predefined_maps(part_clean.lower(), COLOR_NAME_MAP)
            if part_match:
                translated_parts.append(part_match)
            else:
                all_parts_found = False
                break # If one part isn't found, don't consider it a full predefined match

        if all_parts_found and translated_parts:
            # Use a consistent separator like " & "
            compound_translation = " & ".join(translated_parts)
            logger.debug(f"Predefined compound match for '{original_text_clean}' -> '{compound_translation}'")
            return compound_translation

    # No predefined match found
    return None


def get_product_option_values(product_gid, shopify_store_url, shopify_api_key, api_version=shopify_utils.DEFAULT_API_VERSION):
    """
    Fetches product options and their current values using GraphQL.
    Returns the list of option dicts or None on error.
    Relies on shopify_utils.shopify_graphql_request.
    """
    logger.info(f"Fetching options for Product GID: {product_gid}")
    query = """
    query getProductOptions($productId: ID!) {
      product(id: $productId) {
        options {
          id # Option GID (e.g., gid://shopify/ProductOption/123)
          name
          values # List of current string values
          # Removed optionValues field as it seems deprecated/problematic in some versions
          # optionValues { id name } # If needed and works on your version
        }
      }
    }
    """
    variables = {"productId": product_gid}

    # Use the centralized helper
    response = shopify_utils.shopify_graphql_request(
        shopify_store_url, shopify_api_key, query, variables, api_version=api_version
    )

    # Check response structure based on the helper's return format
    if (response and response.get("_success") and response.get("data") and
        response["data"].get("product") and "options" in response["data"]["product"]):
        options = response["data"]["product"]["options"]
        logger.info(f"Successfully fetched {len(options)} options for {product_gid}.")
        logger.debug(f"Fetched options data: {options}")
        return options
    elif response and response.get("_user_errors_exist"):
         logger.error(f"❌ GraphQL fetch for options on {product_gid} returned UserErrors.")
         return None
    else:
        logger.error(f"❌ Error retrieving product options for {product_gid}. Response: {response}")
        return None


def update_product_option_values(product_gid, option_id, option_name, translated_option_name, option_values_data,
                                 target_language, source_language, translation_method,
                                 shopify_store_url, shopify_api_key, api_version=shopify_utils.DEFAULT_API_VERSION):
    """
    Translates a single option's values and updates Shopify via GraphQL productOptionUpdate mutation.
    Handles predefined translations and skipping known sizes.

    Args:
        product_gid (str): The GID of the product.
        option_id (str): The GID of the product option to update.
        option_name (str): The original name of the option.
        translated_option_name (str): The already translated name for the option.
        option_values_data (list): The list of original string values for this option.
        target_language (str): Target language code (e.g., 'de').
        source_language (str): Source language code or 'auto'.
        translation_method (str): Translation method ('google', 'deepl', etc.).
        shopify_store_url (str): Target store URL.
        shopify_api_key (str): Target store API key.
        api_version (str): Shopify API Version.

    Returns:
        bool: True if the update was successful, False otherwise.
    """
    log_prefix = f"[{product_gid} -> Opt:{option_name}]"
    logger.info(f"{log_prefix} Translating values for Option '{option_name}' (ID: {option_id}) to '{target_language}' using '{translation_method}'.")

    # Translate option values
    translated_values_list = [] # List of translated strings
    try:
        for original_value in option_values_data:
            original_value_str = str(original_value).strip()
            if not original_value_str: continue # Skip empty values

            # Skip universal sizes
            if original_value_str.upper() in KNOWN_SIZES:
                logger.info(f"{log_prefix} Skipping known size '{original_value_str}'")
                translated_values_list.append(original_value_str) # Keep original
                continue

            # Check predefined maps (colors, sizes)
            predefined = get_predefined_translation(original_value_str, target_language)
            if predefined:
                logger.info(f"{log_prefix} Using predefined translation: '{original_value_str}' -> '{predefined}'")
                translated_name = predefined
            else:
                # Use AI/API translation
                logger.debug(f"{log_prefix} No predefined match for '{original_value_str}', calling API...")
                # Assumes translation_utils.apply_translation_method exists
                translated_name = translation_utils.apply_translation_method(
                    original_text=original_value_str,
                    method=translation_method,
                    custom_prompt="", # Add prompt if needed for variants
                    source_lang=source_language,
                    target_lang=target_language,
                    field_type="variant_option_value"
                )
                # Clean the result
                # Assumes text_processing_utils.clean_translated_text exists
                translated_name = text_processing_utils.clean_translated_text(translated_name or "") # Ensure clean even if translation returns None
                logger.info(f"{log_prefix} API Translated Value: '{original_value_str}' -> '{translated_name}'")

            translated_values_list.append(translated_name)

        logger.info(f"{log_prefix} Final list of translated values: {translated_values_list}")

    except Exception as trans_err:
        logger.exception(f"{log_prefix} ❌ Error during value translation loop: {trans_err}")
        return False # Fail if translation errors occur

    # Check if anything actually changed (name or values)
    if translated_option_name == option_name and translated_values_list == option_values_data:
         logger.info(f"{log_prefix} No changes detected in option name or values after translation. Skipping Shopify update.")
         return True # Nothing to update, considered success

    # --- Update Shopify via GraphQL ---
    # Note: productOptionUpdate seems to replace ALL values, not just update specific ones.
    # We need to provide the full list of desired values.
    mutation = """
    mutation productOptionUpdate($productId: ID!, $optionUpdateInput: ProductOptionInput!) {
      productOptionUpdate(productId: $productId, productOption: $optionUpdateInput) {
        product {
          id
          options { name values } # Return updated options for verification
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    variables = {
        "productId": product_gid,
        "optionUpdateInput": {
            "id": option_id,                     # GID of the option being updated
            "name": translated_option_name,      # New name
            "values": translated_values_list     # List of NEW values IN ORDER
        }
    }

    logger.info(f"{log_prefix} Sending productOptionUpdate mutation...")
    logger.debug(f"{log_prefix} Variables: {variables}")

    response = shopify_utils.shopify_graphql_request(
         shopify_store_url, shopify_api_key, mutation, variables, api_version=api_version
    )

    # --- Process Response ---
    if (response and response.get("_success") and response.get("data") and
        response["data"].get("productOptionUpdate") and
        not response["data"]["productOptionUpdate"].get("userErrors")):
        logger.info(f"{log_prefix} ✅ Successfully updated option via GraphQL.")
        return True
    elif response and response.get("data", {}).get("productOptionUpdate", {}).get("userErrors"):
        errors = response["data"]["productOptionUpdate"]["userErrors"]
        logger.error(f"{log_prefix} ❌ Failed GraphQL productOptionUpdate. UserErrors: {errors}")
        return False
    else:
        logger.error(f"{log_prefix} ❌ Failed GraphQL productOptionUpdate. Response: {response}")
        return False


def translate_product_options(product_gid: str, target_language: str, source_language: str,
                              translation_method: str, shopify_store_url: str, shopify_api_key: str,
                              api_version: str = shopify_utils.DEFAULT_API_VERSION) -> bool:
    """
    Orchestrates fetching, translating (name & values), and updating all options for a product.

    Returns:
        bool: True if ALL options were processed and updated successfully, False otherwise.
    """
    log_prefix = f"[{product_gid} -> Options]"
    logger.info(f"{log_prefix} === Starting Option Translation Process ===")

    # 1. Fetch current options
    options_data = get_product_option_values(product_gid, shopify_store_url, shopify_api_key, api_version)
    if options_data is None: # Indicates fetch error
        logger.error(f"{log_prefix} Failed to fetch initial options. Aborting.")
        return False
    if not options_data:
        logger.info(f"{log_prefix} Product has no options defined. Skipping variant translation.")
        return True # No options is not an error

    overall_success = True # Track success across all options

    # 2. Translate option names first (store in a temporary map)
    translated_names_map = {} # option_id -> translated_name
    try:
        for option in options_data:
            option_id = option.get("id")
            original_name = option.get("name","").strip()
            if not option_id or not original_name: continue

            # Check predefined maps for option name (e.g., "Size", "Color")
            predefined_name = get_predefined_translation(original_name, target_language)
            if predefined_name:
                translated_name = predefined_name
                logger.info(f"{log_prefix} Using predefined name: '{original_name}' -> '{translated_name}'")
            else:
                # Translate name using API
                translated_name = translation_utils.apply_translation_method(
                    original_text=original_name,
                    method=translation_method,
                    custom_prompt="", # Add prompt if needed
                    source_lang=source_language,
                    target_lang=target_language,
                    field_type="variant_option_name"
                )
                translated_name = text_processing_utils.clean_translated_text(translated_name or "")
                logger.info(f"{log_prefix} API Translated name: '{original_name}' -> '{translated_name}'")

            translated_names_map[option_id] = translated_name

    except Exception as name_trans_err:
        logger.exception(f"{log_prefix} ❌ Error during option NAME translation phase: {name_trans_err}")
        return False # Fail fast if name translation encounters critical error


    # 3. Loop through options again to translate values and update
    for option in options_data:
        option_id = option.get("id")
        original_name = option.get("name","").strip()
        original_values = option.get("values", [])
        if not option_id or not original_name:
            logger.warning(f"{log_prefix} Skipping option due to missing ID or Name: {option}")
            continue

        # Get the translated name from our map
        translated_option_name = translated_names_map.get(option_id, original_name)

        # Call the update function which handles value translation AND the API call
        success = update_product_option_values(
            product_gid=product_gid,
            option_id=option_id,
            option_name=original_name, # Pass original for logging inside update func
            translated_option_name=translated_option_name,
            option_values_data=original_values,
            target_language=target_language,
            source_language=source_language,
            translation_method=translation_method,
            shopify_store_url=shopify_store_url,
            shopify_api_key=shopify_api_key,
            api_version=api_version
        )

        if not success:
            logger.error(f"{log_prefix} Failed to update option '{original_name}' (ID: {option_id}).")
            overall_success = False
            # Decide whether to continue with other options or stop on first failure
            # break # Uncomment to stop on first failure

    logger.info(f"{log_prefix} === Finished Option Translation Process. Overall Success: {overall_success} ===")
    return overall_success


# --- Add other Variant utility functions as needed ---