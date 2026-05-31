"""Escalation detection engine for BFSI voice agents."""

import re
from typing import Iterable

from app.models.agent import AgentConfig, EscalationResult, EscalationRule

# Built-in escalation triggers (applied to all agents)
DEFAULT_ESCALATION_RULES: list[EscalationRule] = [
    EscalationRule(
        trigger="customer_requested_human",
        patterns=[
            r"\b(speak|talk|connect|transfer)\b.*\b(human|person|agent|representative|someone)\b",
            r"\b(real person|live agent|customer service)\b",
            r"\b(manager|supervisor)\b",
        ],
        description="Customer explicitly requested a human agent",
    ),
    EscalationRule(
        trigger="customer_angry",
        patterns=[
            r"\b(angry|furious|frustrated|upset|ridiculous|unacceptable)\b",
            r"\b(this is nonsense|worst service|complaint)\b",
        ],
        description="Customer appears angry or frustrated",
    ),
    EscalationRule(
        trigger="abusive_language",
        patterns=[
            r"\b(idiot|stupid|useless|shut up|damn|hell)\b",
        ],
        description="Customer used abusive language",
    ),
    EscalationRule(
        trigger="account_dispute",
        patterns=[
            r"\b(wrong|incorrect|dispute|not my|never took|didn't take)\b.*\b(loan|emi|payment|account)\b",
            r"\b(this is wrong|that's not correct|dispute this)\b",
        ],
        description="Customer disputes account information",
    ),
    EscalationRule(
        trigger="settlement_request",
        patterns=[
            r"\b(settlement|waive|waiver|discount|reduce|restructure|negotiate)\b",
            r"\b(can't pay|cannot pay full|partial payment plan)\b",
        ],
        description="Customer requested settlement or negotiation",
    ),
    EscalationRule(
        trigger="legal_clarification",
        patterns=[
            r"\b(lawyer|legal|court|sue|lawsuit|legal action|legal notice)\b",
            r"\b(what are my rights|legal advice)\b",
        ],
        description="Customer requested legal clarification",
    ),
    EscalationRule(
        trigger="account_details_unavailable",
        patterns=[
            r"\b(exact balance|full statement|transaction history|account number)\b",
            r"\b(all my loans|other accounts|credit score)\b",
        ],
        description="Customer requested unavailable account-specific details",
    ),
]


class EscalationEngine:
    """Detects when a conversation must be escalated to a human agent."""

    def __init__(self, default_rules: Iterable[EscalationRule] | None = None) -> None:
        self._default_rules = list(default_rules or DEFAULT_ESCALATION_RULES)

    def check(
        self,
        user_message: str,
        agent_config: AgentConfig,
    ) -> EscalationResult:
        """
        Evaluate user message against escalation rules.

        Agent-specific rules are checked first, then defaults.
        """
        text = user_message.lower().strip()
        if not text:
            return EscalationResult(escalate=False)

        all_rules = list(agent_config.escalation_rules) + self._default_rules

        for rule in all_rules:
            if self._matches(text, rule.patterns):
                return EscalationResult(escalate=True, reason=rule.trigger)

        return EscalationResult(escalate=False)

    @staticmethod
    def _matches(text: str, patterns: list[str]) -> bool:
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
