"""Objection detection and approved response library."""

import re
from typing import Optional

from app.models.agent import AgentConfig, ObjectionRule

# Default objection library (merged with agent-specific rules)
DEFAULT_OBJECTION_RULES: list[ObjectionRule] = [
    ObjectionRule(
        scenario="Customer is busy",
        trigger_patterns=[
            r"\b(busy|in a meeting|driving|not a good time|call later|can't talk)\b",
        ],
        response=(
            "I understand. Would you like me to schedule a callback at a more convenient time?"
        ),
    ),
    ObjectionRule(
        scenario="Customer already paid",
        trigger_patterns=[
            r"\b(already paid|payment done|paid already|made the payment|transferred)\b",
        ],
        response=(
            "Thank you for letting me know. I can note that and arrange for verification by the bank."
        ),
    ),
    ObjectionRule(
        scenario="Customer has no money",
        trigger_patterns=[
            r"\b(don't have money|no money|can't afford|financial difficulty|no funds)\b",
            r"\b(unemployed|lost my job|hard time paying)\b",
        ],
        response=(
            "I understand. A banking representative may be able to discuss available options with you."
        ),
    ),
    ObjectionRule(
        scenario="Customer wants to stop calls",
        trigger_patterns=[
            r"\b(stop calling|don't call|remove my number|do not call|never call)\b",
        ],
        response=(
            "I understand. I will record your request and arrange for appropriate follow-up."
        ),
    ),
    ObjectionRule(
        scenario="Customer denies loan",
        trigger_patterns=[
            r"\b(don't have a loan|no loan|never took|wrong person|not my loan)\b",
        ],
        response=(
            "I apologize for any confusion. Let me connect you with a banking representative "
            "who can verify your account details."
        ),
    ),
    ObjectionRule(
        scenario="Customer asks why calling",
        trigger_patterns=[
            r"\b(why are you calling|why calling|what is this about|who is this)\b",
        ],
        response=(
            "I'm calling from ABC Bank regarding your loan EMI payment. "
            "May I confirm I'm speaking with the account holder?"
        ),
    ),
]


class ObjectionHandler:
    """Matches customer objections to approved banking responses."""

    def __init__(
        self,
        default_rules: list[ObjectionRule] | None = None,
    ) -> None:
        self._default_rules = default_rules or DEFAULT_OBJECTION_RULES

    def detect(
        self,
        user_message: str,
        agent_config: AgentConfig,
    ) -> Optional[tuple[str, str]]:
        """
        Detect an objection in the user message.

        Returns:
            Tuple of (scenario, approved_response) or None.
        """
        text = user_message.lower().strip()
        if not text:
            return None

        all_rules = list(agent_config.objection_rules) + self._default_rules

        for rule in all_rules:
            for pattern in rule.trigger_patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    return rule.scenario, rule.response

        return None
