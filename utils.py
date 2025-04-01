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
