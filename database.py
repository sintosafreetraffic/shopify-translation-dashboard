import sqlite3
import os

# Database file location
DATABASE = "../translations.db"

def init_db():
    """Initialize the database and create necessary tables if they don't exist."""
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
        print("✅ Database initialized successfully.")

def add_translation(product_id, product_title, translated_title, product_description, translated_description, batch, status="Pending"):
    """Insert a new translation into the database."""
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO translations (product_id, product_title, translated_title, product_description, translated_description, batch, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (product_id, product_title, translated_title, product_description, translated_description, batch, status))
        conn.commit()

def get_all_translations():
    """Retrieve all translations from the database."""
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM translations")
        return cursor.fetchall()

def get_translation_by_product_id(product_id):
    """Retrieve a single translation by product ID."""
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM translations WHERE product_id=?", (product_id,))
        return cursor.fetchone()

def update_translation_status(product_id, status):
    """Update the status of a translation (e.g., Approved, Rejected, Pending Review)."""
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE translations SET status=? WHERE product_id=?", (status, product_id))
        conn.commit()

def update_translated_description(product_id, translated_description):
    """Update the translated description of a product."""
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE translations SET translated_description=?, status='Pending Review' WHERE product_id=?",
                       (translated_description, product_id))
        conn.commit()

def delete_translation(product_id):
    """Delete a translation from the database."""
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM translations WHERE product_id=?", (product_id,))
        conn.commit()

# Initialize database when script is run
if __name__ == "__main__":
    init_db()
