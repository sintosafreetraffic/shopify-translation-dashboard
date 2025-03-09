import requests
import os

# Shopify API Credentials from config.py
SHOPIFY_STORE_URL = os.getenv("SHOPIFY_STORE_URL")
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")

def fetch_product_by_id(product_id):
    """Fetch a product's details from Shopify by Product ID."""
    url = f"https://{SHOPIFY_STORE_URL}/admin/api/2023-04/products/{product_id}.json"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_API_KEY,
        "Content-Type": "application/json"
    }
    
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json().get("product", {})
    else:
        print(f"Failed to fetch product {product_id}: {response.text}")
        return None

def fetch_products_by_collection(collection_id, limit=50):
    """Fetch products belonging to a specific collection."""
    url = f"https://{SHOPIFY_STORE_URL}/admin/api/2023-04/collections/{collection_id}/products.json?limit={limit}"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_API_KEY,
        "Content-Type": "application/json"
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json().get("products", [])
    else:
        print(f"Failed to fetch products from collection {collection_id}: {response.text}")
        return []

def update_product_translation(product_id, translated_title, translated_description):
    """Update a product in Shopify with the translated title and description."""
    url = f"https://{SHOPIFY_STORE_URL}/admin/api/2023-04/products/{product_id}.json"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "product": {
            "id": product_id,
            "title": translated_title,
            "body_html": translated_description
        }
    }

    response = requests.put(url, json=payload, headers=headers)

    if response.status_code == 200:
        print(f"Successfully updated product {product_id}")
        return response.json().get("product", {})
    else:
        print(f"Failed to update product {product_id}: {response.text}")
        return None

def fetch_product_by_url(product_url):
    """Extract product ID from URL and fetch product details."""
    if "/products/" in product_url:
        product_handle = product_url.split("/products/")[-1].split("?")[0].strip("/")
        url = f"https://{SHOPIFY_STORE_URL}/admin/api/2023-04/products.json?handle={product_handle}"
        
        headers = {
            "X-Shopify-Access-Token": SHOPIFY_API_KEY,
            "Content-Type": "application/json"
        }

        response = requests.get(url, headers=headers)

        if response.status_code == 200 and response.json().get("products"):
            return response.json().get("products")[0]
        else:
            print(f"Failed to fetch product by URL {product_url}: {response.text}")
            return None
    else:
        print("Invalid Shopify product URL format.")
        return None

