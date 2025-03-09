from flask import Flask, request, jsonify
from shopify_api import fetch_product_by_id, update_product_translation
from translation import google_translate, deepl_translate, chatgpt_translate
from google_sheets import log_translation
import os
import sqlite3

app = Flask(__name__)

DATABASE = "translations.db"

# Ensure database exists
def init_db():
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS translations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT UNIQUE,
                product_title TEXT,
                translated_title TEXT,
                product_description TEXT,
                translated_description TEXT,
                batch TEXT,
                status TEXT
            )
        """)
        conn.commit()

init_db()

@app.route("/translate_product", methods=["POST"])
def translate_product():
    """Translate a product description using AI and store in the database."""
    data = request.json
    product_id = data.get("product_id")
    custom_prompt = data.get("custom_prompt", "")
    selected_tone = data.get("selected_tone", "Neutral")

    # Fetch product details from Shopify
    product = fetch_product_by_id(product_id)
    if not product:
        return jsonify({"success": False, "message": "Product not found in Shopify."})

    title = product.get("title", "")
    description = product.get("body_html", "")

    # AI Translation Prompt with Tone Customization
    ai_prompt = f"""
    Translate the following product description into the target language.
    Use a **{selected_tone}** tone that matches the product's branding.

    Product Title: {title}
    Description: {description}

    Ensure the translation maintains a natural, high-converting style.
    """

    translated_title = google_translate(title)
    translated_description = chatgpt_translate(ai_prompt, custom_prompt)

    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO translations (product_id, product_title, translated_title, product_description, translated_description, batch, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (product_id, title, translated_title, description, translated_description, "API Batch", "Pending"))
        conn.commit()

    return jsonify({"success": True, "message": "Translation completed.", "translated_title": translated_title, "translated_description": translated_description})

@app.route("/approve_translation", methods=["POST"])
def approve_translation():
    """Approve and update the translation in Shopify."""
    data = request.json
    product_id = data.get("product_id")

    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT translated_title, translated_description FROM translations WHERE product_id=?", (product_id,))
        product = cursor.fetchone()

        if product:
            translated_title, translated_description = product
            update_product_translation(product_id, translated_title, translated_description)
            cursor.execute("UPDATE translations SET status='Approved' WHERE product_id=?", (product_id,))
            conn.commit()
            log_translation(product_id, translated_title, translated_description, "Approved")
            return jsonify({"success": True, "message": "Translation approved and updated in Shopify."})

    return jsonify({"success": False, "message": "Product not found."})

@app.route("/reject_translation", methods=["POST"])
def reject_translation():
    """Reject a translation and allow the user to modify the prompt before reprocessing."""
    data = request.json
    product_id = data.get("product_id")
    new_prompt = data.get("new_prompt", "")

    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT product_title, product_description FROM translations WHERE product_id=?", (product_id,))
        product = cursor.fetchone()

        if product:
            product_title, product_description = product

            new_ai_prompt = f"""
            Translate the following product description into the target language with the user's modifications.
            Product Title: {product_title}
            Description: {product_description}
            User's Custom Instruction: {new_prompt}
            """

            new_translated_description = chatgpt_translate(new_ai_prompt, new_prompt)

            cursor.execute("UPDATE translations SET translated_description=?, status='Pending Review' WHERE product_id=?",
                           (new_translated_description, product_id))
            conn.commit()
            return jsonify({"success": True, "message": "Translation rejected and reprocessed with new prompt."})

    return jsonify({"success": False, "message": "Product not found."})

@app.route("/optimize_future_translations", methods=["POST"])
def optimize_future_translations():
    """Analyze past translation performance and create optimized future prompts."""
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT product_id, translated_description FROM translations WHERE status='Approved'")
        records = cursor.fetchall()

    if not records:
        return jsonify({"success": False, "message": "No past translation data found."})

    optimization_prompt = "Analyze the past translation performance data and optimize future translation prompts:\n\n"
    for record in records:
        optimization_prompt += f"""
        Product ID: {record[0]}
        Translated Description: {record[1]}
        """

    optimization_prompt += """
    Based on this data, refine and suggest an optimized translation prompt that improves future translations.
    The goal is to generate high-converting descriptions based on proven best practices from past performance.
    """

    optimized_prompt = chatgpt_translate(optimization_prompt, system_role="assistant")

    return jsonify({"success": True, "optimized_prompt": optimized_prompt})

@app.route("/routes", methods=["GET"])
def list_routes():
    """List all available routes in the Flask app."""
    output = []
    for rule in app.url_map.iter_rules():
        methods = ",".join(rule.methods)
        output.append(f"{rule.rule} ({methods})")
    return "<br>".join(output)


if __name__ == "__main__":
    app.run(debug=True, port=5001)
