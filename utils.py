import re

def slugify(text): 
    """
    Convert text to a URL-friendly slug.
    """
    return (
        text.lower()
            .strip()
            .replace(" ", "-")
            .replace("ä", "ae")
            .replace("ö", "oe")
            .replace("ü", "ue")
            .replace("ß", "ss")
            .replace("/", "-")
            .replace("|", "-")
    )

def extract_name_from_title(title: str) -> str:
    """
    Extracts the human name from a product title like 'Daisy | 3-Piece Lingerie Set'.
    Returns the part before the pipe character.
    """
    if "|" in title:
        return title.split("|")[0].strip()
    return title.strip()
