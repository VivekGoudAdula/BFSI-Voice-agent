"""Sentiment-aware post-processing for customer-friendly responses."""

import re


class SentimentAwareResponseEngine:
    """Detects coarse sentiment and adapts response tone."""

    def detect_sentiment(self, text: str) -> str:
        t = text.lower()
        if re.search(r"\b(already paid|payment done|paid already)\b", t):
            return "positive"
        if re.search(r"\b(busy|not a good time|call later|meeting)\b", t):
            return "neutral"
        if re.search(r"\b(angry|upset|annoyed|frustrated|stop calling)\b", t):
            return "frustrated"
        if re.search(r"\b(no|can't|cannot|don't)\b", t):
            return "negative"
        return "neutral"

    def adapt_response(self, customer_text: str, response_text: str) -> tuple[str, str]:
        sentiment = self.detect_sentiment(customer_text)
        t = customer_text.lower()
        if "already paid" in t or "payment done" in t:
            return (
                "Okay, thanks for letting me know. I'll make a note of that.",
                sentiment,
            )
        if "busy" in t or "not a good time" in t:
            return ("No problem. Would you prefer a callback later?", sentiment)
        if sentiment == "frustrated":
            return ("I understand. I will keep this quick. How would you like to proceed?", sentiment)
        return response_text, sentiment
