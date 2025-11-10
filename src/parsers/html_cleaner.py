import re
from html import unescape
from typing import Optional

def clean_text(value: Optional[str]) -> Optional[str]:
    """Normalize whitespace, decode HTML entities, and strip control chars."""
    if value is None:
        return None
    txt = unescape(value)
    txt = re.sub(r"\s+", " ", txt).strip()
    # Remove zero-width spaces and control characters
    txt = re.sub(r"[\u200B-\u200D\uFEFF]", "", txt)
    return txt or None