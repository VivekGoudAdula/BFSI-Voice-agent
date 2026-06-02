"""Human-like response shaping for natural phone conversations."""

import random
import re


ROBOTIC_PHRASES: dict[str, str] = {
    "Thank you for confirming.": "Okay, got it.",
    "Your EMI payment is pending.": "I can see there is an EMI due.",
    "Please proceed with payment.": "Would you like me to send the payment link?",
}

FILLERS_EN = ["Okay", "Alright", "Got it", "Sure", "I understand", "Let me check"]
FILLERS_HI = ["Ji", "Achha", "Theek hai", "Samajh gaya", "Bilkul", "Zaroor"]


class ConversationBehaviorEngine:
    """Applies short, natural, non-robotic speaking behavior."""

    def shape_response(self, text: str, language: str, sentiment: str = "neutral") -> str:
        cleaned = self._replace_robotic_phrases(text)
        cleaned = self._inject_filler(cleaned, language, sentiment)
        cleaned = self._limit_sentence_count(cleaned, max_sentences=1)
        cleaned = self._limit_word_count(cleaned, max_words=15)
        return cleaned.strip()

    def _replace_robotic_phrases(self, text: str) -> str:
        for old, new in ROBOTIC_PHRASES.items():
            text = text.replace(old, new)
        text = text.replace("As an AI assistant", "").replace(
            "I am an artificial intelligence", ""
        )
        text = text.replace("I am a chatbot", "")
        return re.sub(r"\s{2,}", " ", text).strip()

    def _limit_sentence_count(self, text: str, max_sentences: int = 3) -> str:
        parts = re.split(r"(?<=[.!?])\s+", text.strip())
        parts = [p for p in parts if p]
        if len(parts) <= max_sentences:
            return text
        return " ".join(parts[:max_sentences]).strip()

    def _limit_word_count(self, text: str, max_words: int = 15) -> str:
        words = text.split()
        if len(words) <= max_words:
            return text
        truncated = " ".join(words[:max_words]).strip()
        # Ensure we end with some terminal punctuation for a single utterance.
        if not truncated.endswith((".", "!", "?", "।")):
            truncated += "."
        return truncated

    def _inject_filler(self, text: str, language: str, sentiment: str) -> str:
        if not text:
            return text
        if sentiment == "frustrated":
            return text
        if random.random() > 0.22:
            return text
        lower = text.lower()
        if lower.startswith(("okay", "alright", "got it", "sure", "ji", "achha")):
            return text
        fillers = FILLERS_HI if language == "hi" else FILLERS_EN
        return f"{random.choice(fillers)}, {text[0].lower() + text[1:]}"
