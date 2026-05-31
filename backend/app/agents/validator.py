"""Response validator for compliance, length, and tone."""

import re

from app.models.agent import AgentConfig, ValidationResult

# Phrases that must never appear in agent responses
FORBIDDEN_PHRASES: list[str] = [
    r"\b(i guarantee|we guarantee|guaranteed approval)\b",
    r"\b(waiver approved|fee waived|penalty waived)\b",
    r"\b(settlement offer|we can settle for)\b",
    r"\b(loan approved|pre-approved|instant approval)\b",
    r"\b(legal advice|you should sue|file a case)\b",
    r"\b(your balance is|your account number is|your password)\b",
    r"\b(other customer|another customer)\b",
    r"\b(internal policy|our internal)\b",
    r"\b(you must pay|pay immediately or|legal action will|we will sue)\b",
    r"\b(threaten|harass|seize|confiscate)\b",
]

# Patterns suggesting invented account data
HALLUCINATION_PATTERNS: list[str] = [
    r"\b(your emi is|your due date is|your outstanding is)\s*(rs\.?\s*)?\d",
    r"\b(your loan amount is|your account balance is)\s*(rs\.?\s*)?\d",
]

MAX_SENTENCES = 4
MAX_CHARS = 350


class ResponseValidator:
    """Validates AI responses before they are spoken to the customer."""

    def validate(
        self,
        response: str,
        agent_config: AgentConfig,
        *,
        has_account_context: bool = False,
    ) -> ValidationResult:
        """Check response against compliance, length, and tone rules."""
        violations: list[str] = []
        text = response.strip()

        if not text:
            violations.append("empty_response")
            return ValidationResult(is_valid=False, violations=violations)

        if len(text) > MAX_CHARS:
            violations.append("response_too_long")

        sentence_count = len(re.split(r"[.!?]+", text))
        if sentence_count > MAX_SENTENCES:
            violations.append("too_many_sentences")

        lower = text.lower()
        for pattern in FORBIDDEN_PHRASES:
            if re.search(pattern, lower, re.IGNORECASE):
                violations.append(f"forbidden_phrase:{pattern}")

        if not has_account_context:
            for pattern in HALLUCINATION_PATTERNS:
                if re.search(pattern, lower, re.IGNORECASE):
                    violations.append(f"potential_hallucination:{pattern}")

        aggressive_patterns = [
            r"\b(you have to|you must|mandatory|final warning)\b",
            r"\b(pay now or else|immediately or else|pay right now or)\b",
        ]
        for pattern in aggressive_patterns:
            if re.search(pattern, lower, re.IGNORECASE):
                violations.append(f"aggressive_tone:{pattern}")

        return ValidationResult(is_valid=len(violations) == 0, violations=violations)

    def build_regeneration_hint(self, violations: list[str]) -> str:
        """Build a hint appended to the system prompt on regeneration."""
        hints = [
            "Your previous response was rejected. Regenerate following these fixes:",
        ]
        for v in violations:
            if v == "response_too_long" or v == "too_many_sentences":
                hints.append("- Keep response to 2-3 short sentences maximum.")
            elif v.startswith("forbidden_phrase"):
                hints.append("- Remove any promises, legal advice, or internal policy references.")
            elif v.startswith("potential_hallucination"):
                hints.append(
                    "- Do NOT invent EMI amounts, due dates, or account balances. "
                    "Use only provided context or say you don't have that information."
                )
            elif v.startswith("aggressive_tone"):
                hints.append("- Use a calm, respectful tone. Do not pressure the customer.")
        return "\n".join(hints)
