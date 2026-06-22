from html import unescape


def clean_media_url(value):
    """Normalize media URLs captured from HTML/JS snippets."""
    text = str(value or "").strip()
    if not text:
        return ""

    text = unescape(text)
    replacements = {
        r"\/": "/",
        r"\u0026": "&",
        r"\u002F": "/",
        r"\u003F": "?",
        r"\u003D": "=",
        r"\u003A": ":",
        r"\u0025": "%",
    }
    for escaped, plain in replacements.items():
        text = text.replace(escaped, plain)
        text = text.replace(escaped.lower(), plain)

    text = text.strip().strip("\ufeff")
    while text and text[-1] in "\\'\"`,;)]}":
        text = text[:-1].strip()
    while text and text[0] in "'\"`([{":
        text = text[1:].strip()
    return text
