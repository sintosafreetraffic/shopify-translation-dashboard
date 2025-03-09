import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Shopify API Credentials
SHOPIFY_STORE_URL = os.getenv("SHOPIFY_STORE_URL")  # Example: 'your-store.myshopify.com'
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")  # Shopify Access Token

# Google Sheets API Credentials
GOOGLE_SHEETS_CREDENTIALS = "credentials.json"
GOOGLE_SHEET_NAME = "Translation Performance Tracking"

# OpenAI API Key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # Required for AI-powered translations

# DeepL API Key (if using DeepL translations)
DEEPL_API_KEY = os.getenv("DEEPL_API_KEY")

# Google Translate API Key (if using Google Translate)
GOOGLE_TRANSLATE_API_KEY = os.getenv("GOOGLE_TRANSLATE_API_KEY")

# Translation Settings (Enable/Disable Components)
TRANSLATE_TITLE = True  # Enable/Disable Title Translation
TRANSLATE_DESCRIPTION = True  # Enable/Disable Description Translation
TRANSLATE_VARIANTS = True  # Enable/Disable Variant Translation
TRANSLATE_SEO = True  # Enable/Disable SEO Fields Translation

# Target Translation Language
TARGET_LANGUAGE = "de"  # Example: "de" for German, "fr" for French

# Default Tone for AI-Generated Translations
DEFAULT_TONE = "Neutral"

# Email Notification Settings
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")  # Default SMTP Server
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))  # Port for SMTP Server
EMAIL_USERNAME = os.getenv("EMAIL_USERNAME")  # Sender Email
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")  # Email Password (Use App Password)
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")  # Admin Email for notifications

# Logging Configuration
LOG_FILE = "logs/translation.log"

