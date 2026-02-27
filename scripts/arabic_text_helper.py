"""
Helper for Arabic RTL text rendering in matplotlib.
"""
import arabic_reshaper
from bidi.algorithm import get_display

def ar(text):
    """Convert Arabic text to display-ready RTL format for matplotlib."""
    if not text or not any('\u0600' <= c <= '\u06FF' for c in str(text)):
        return str(text)  # Not Arabic, return as-is
    reshaped = arabic_reshaper.reshape(str(text))
    return get_display(reshaped)
