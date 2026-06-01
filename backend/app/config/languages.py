"""Configuration-driven language registry for BFSI voice agents."""

from typing import Any

# ISO 639-1 codes → display names. Add new languages here only.
SUPPORTED_LANGUAGES: dict[str, str] = {
    "en": "English",
    "hi": "Hindi",
}

# Unicode script ranges for automatic detection (code-mixed aware).
SCRIPT_RANGES: dict[str, list[tuple[int, int]]] = {
    "hi": [(0x0900, 0x097F)],  # Devanagari (Hindi/Marathi — disambiguate via keywords)
}

# Explicit customer language-switch phrases (regex, target language code).
LANGUAGE_SWITCH_PATTERNS: list[tuple[str, str]] = [
    # English / romanized requests
    (r"(?i)\b(speak|talk|continue|switch)\b.*\b(hindi|हिंदी)\b", "hi"),
    (r"(?i)\b(speak|talk|continue|switch)\b.*\b(english)\b", "en"),
    (r"(?i)\b(prefer|want)\s+english\b", "en"),
    (r"(?i)\bhindi\s+mein\s+baat", "hi"),
    (r"(?i)\bhindi\s+me\s+bolo", "hi"),
    (r"(?i)\bhindi\s+me\s+baat", "hi"),
    (r"(?i)\bhindi\s+me\b", "hi"),
    (r"(?i)\bmein\s+baat", "hi"),
    (r"(?i)\bbaath?\s+kar", "hi"),
    (r"(?i)\bkar\s+sak(th|t)e", "hi"),
    (r"(?i)\bkya\s+aap.*hindi", "hi"),
    (r"(?i)\bcan\s+you.*hindi", "hi"),
    (r"(?i)\benglish\s+mein\s+baat", "en"),
    # Devanagari requests
    (r"हिंदी\s+में\s+बात", "hi"),
    (r"क्या\s+आप.*हिंदी", "hi"),
    (r"हिंदी\s+में\s+बात\s+कर", "hi"),
    (r"हिंदी\s+में\s+बोल", "hi"),
    (r"आप\s+कौन", "hi"),
    (r"कौन\s+है", "hi"),
    (r"कौन\s+हो", "hi"),
]

# Marathi-specific Devanagari keywords (shared script with Hindi).
MARATHI_KEYWORDS = frozenset(
    {"मराठी", "मराठीत", "बोल", "बोला", "बोलू", "कृपया"}
)
HINGLISH_KEYWORDS = frozenset(
    {
        "aap",
        "aapka",
        "aapki",
        "haan",
        "ji",
        "theek",
        "samjha",
        "samjha",
        "boliye",
        "baat",
        "karo",
        "karna",
        "kal",
        "aaj",
        "abhi",
        "emi",
    }
)
HINDI_KEYWORDS = frozenset(
    {"हिंदी", "हिन्दी", "में", "मein", "बात", "करो", "करू", "बोलो", "बोलिए"}
)

DEFAULT_SUPPORTED_LANGUAGES = ["en", "hi"]
DEFAULT_LANGUAGE = "en"


def normalize_language_code(code: str, supported: list[str] | None = None) -> str | None:
    """Return code if supported, else None."""
    if not code:
        return None
    normalized = code.strip().lower()[:2]
    allowed = supported or DEFAULT_SUPPORTED_LANGUAGES
    return normalized if normalized in allowed else None
