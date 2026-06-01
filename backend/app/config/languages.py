"""Configuration-driven language registry for BFSI voice agents."""

from typing import Any

# ISO 639-1 codes → display names. Add new languages here only.
SUPPORTED_LANGUAGES: dict[str, str] = {
    "en": "English",
    "hi": "Hindi",
    "te": "Telugu",
    "ta": "Tamil",
    "kn": "Kannada",
    "mr": "Marathi",
    "bn": "Bengali",
}

# Unicode script ranges for automatic detection (code-mixed aware).
SCRIPT_RANGES: dict[str, list[tuple[int, int]]] = {
    "hi": [(0x0900, 0x097F)],  # Devanagari (Hindi/Marathi — disambiguate via keywords)
    "mr": [(0x0900, 0x097F)],
    "te": [(0x0C00, 0x0C7F)],  # Telugu
    "ta": [(0x0B80, 0x0BFF)],  # Tamil
    "kn": [(0x0C80, 0x0CFF)],  # Kannada
    "bn": [(0x0980, 0x09FF)],  # Bengali
}

# Explicit customer language-switch phrases (regex, target language code).
LANGUAGE_SWITCH_PATTERNS: list[tuple[str, str]] = [
  # English requests
    (r"(?i)\b(speak|talk|continue|switch)\b.*\b(hindi|हिंदी)\b", "hi"),
    (r"(?i)\b(speak|talk|continue|switch)\b.*\b(telugu|తెలుగు)\b", "te"),
    (r"(?i)\b(speak|talk|continue|switch)\b.*\b(tamil|தமிழ்)\b", "ta"),
    (r"(?i)\b(speak|talk|continue|switch)\b.*\b(kannada|ಕನ್ನಡ)\b", "kn"),
    (r"(?i)\b(speak|talk|continue|switch)\b.*\b(marathi|मराठी)\b", "mr"),
    (r"(?i)\b(speak|talk|continue|switch)\b.*\b(bengali|বাংলা|bangla)\b", "bn"),
    (r"(?i)\b(speak|talk|continue|switch)\b.*\b(english)\b", "en"),
    (r"(?i)\b(prefer|want)\s+english\b", "en"),
    (r"(?i)\bhindi\s+mein\s+baat\b", "hi"),
    (r"(?i)\bhindi\s+me\s+bolo\b", "hi"),
    (r"(?i)\benglish\s+mein\s+baat\b", "en"),
    # Native script requests
    (r"తెలుగులో\s+మాట్లాడ", "te"),
    (r"हिंदी\s+में\s+बात", "hi"),
    (r"தமிழில்\s+பேச", "ta"),
    (r"ಕನ್ನಡದಲ್ಲಿ\s+ಮಾತನಾಡ", "kn"),
    (r"मराठीत\s+बोल", "mr"),
    (r"বাংলায়\s+কথা", "bn"),
]

# Marathi-specific Devanagari keywords (shared script with Hindi).
MARATHI_KEYWORDS = frozenset(
    {"मराठी", "मराठीत", "बोल", "बोला", "बोलू", "कृपया"}
)
HINDI_KEYWORDS = frozenset(
    {"हिंदी", "हिन्दी", "में", "मein", "बात", "करो", "करू", "बोलो", "बोलिए"}
)

DEFAULT_SUPPORTED_LANGUAGES = list(SUPPORTED_LANGUAGES.keys())
DEFAULT_LANGUAGE = "en"


def normalize_language_code(code: str, supported: list[str] | None = None) -> str | None:
    """Return code if supported, else None."""
    if not code:
        return None
    normalized = code.strip().lower()[:2]
    allowed = supported or DEFAULT_SUPPORTED_LANGUAGES
    return normalized if normalized in allowed else None
