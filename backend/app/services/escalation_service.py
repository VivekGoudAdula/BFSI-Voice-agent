"""Escalation detection engine — analyzes messages, sentiment, and agent rules."""

import re
from typing import Any, Optional

from app.agents.escalation import DEFAULT_ESCALATION_RULES, EscalationEngine
from app.agents.states import ConversationState
from app.models.agent import AgentConfig, EscalationRule
from app.models.handoff import EscalationAnalysisResult, EscalationCategory, SentimentLevel
from app.services.sentiment_service import SentimentService

# Maps legacy trigger IDs and patterns to standardized categories
_TRIGGER_TO_CATEGORY: dict[str, EscalationCategory] = {
    "customer_requested_human": EscalationCategory.CUSTOMER_REQUESTED_HUMAN,
    "customer_angry": EscalationCategory.NEGATIVE_SENTIMENT,
    "abusive_language": EscalationCategory.NEGATIVE_SENTIMENT,
    "account_dispute": EscalationCategory.ACCOUNT_DISPUTE,
    "legal_clarification": EscalationCategory.LEGAL_QUERY,
    "settlement_request": EscalationCategory.HIGH_RISK_QUERY,
    "account_details_unavailable": EscalationCategory.CUSTOMER_REQUESTED_HUMAN,
}

_CATEGORY_RULES: list[tuple[EscalationCategory, list[str], str]] = [
    (
        EscalationCategory.CUSTOMER_REQUESTED_HUMAN,
        [
            r"\b(speak|talk|connect|transfer)\b.*\b(human|person|agent|representative|someone)\b",
            r"\b(real person|live agent|customer service|executive)\b",
            r"\b(manager|supervisor|banking representative)\b",
        ],
        "Customer requested to speak with a human representative",
    ),
    (
        EscalationCategory.COMPLAINT,
        [
            r"\b(file a complaint|register a complaint|raise a complaint)\b",
            r"\b(want to complain|making a complaint|official complaint)\b",
            r"\b(this service is terrible|worst service|raise an issue)\b",
        ],
        "Customer wants to file or escalate a complaint",
    ),
    (
        EscalationCategory.LEGAL_QUERY,
        [
            r"\b(legal clarification|legal details|legal department)\b",
            r"\b(lawyer|legal team|legal advice|legal notice)\b",
            r"\b(sue|lawsuit|court|legal action)\b",
        ],
        "Customer requested legal clarification or legal department",
    ),
    (
        EscalationCategory.ACCOUNT_DISPUTE,
        [
            r"\b(emi amount is wrong|emi is wrong|wrong emi)\b",
            r"\b(loan information is wrong|wrong loan|incorrect loan)\b",
            r"\b(disagree with these charges|dispute.*charges)\b",
            r"\b(wrong|incorrect|dispute)\b.*\b(emi|loan|payment|account|charges)\b",
        ],
        "Customer disputes account or EMI information",
    ),
    (
        EscalationCategory.HIGH_RISK_QUERY,
        [
            r"\b(fraud|fraudulent|scam|unauthorized transaction)\b",
            r"\b(identity theft|stolen identity|account hacked)\b",
            r"\b(unauthorized|suspicious activity|unrecognized charge)\b",
            r"\b(sensitive banking|security breach)\b",
        ],
        "Customer raised fraud or high-risk banking concern",
    ),
    (
        EscalationCategory.NEGATIVE_SENTIMENT,
        [
            r"\b(refuse|won't listen|stop talking|not helping)\b",
            r"\b(angry|furious|frustrated|upset|ridiculous)\b",
            r"\b(idiot|stupid|useless|shut up)\b",
        ],
        "Customer shows strong negative sentiment or aggression",
    ),
]

_TRANSFER_MESSAGES: dict[EscalationCategory, str] = {
    EscalationCategory.CUSTOMER_REQUESTED_HUMAN: (
        "Certainly. I will connect you with a banking representative who can assist you further."
    ),
    EscalationCategory.COMPLAINT: (
        "I understand your concern. Let me connect you with a specialist who can assist further."
    ),
    EscalationCategory.LEGAL_QUERY: (
        "For legal matters, I will connect you with the appropriate banking team."
    ),
    EscalationCategory.ACCOUNT_DISPUTE: (
        "I would like a banking representative to review that information. Let me arrange a transfer."
    ),
    EscalationCategory.NEGATIVE_SENTIMENT: (
        "I understand this is frustrating. Let me connect you with a specialist who can help."
    ),
    EscalationCategory.HIGH_RISK_QUERY: (
        "This requires immediate attention from our banking team. I am connecting you now."
    ),
}


class EscalationService:
    """
    Analyzes user messages, sentiment, conversation state, and agent rules
    to determine if the AI should escalate to a human.
    """

    def __init__(
        self,
        sentiment_service: Optional[SentimentService] = None,
        legacy_engine: Optional[EscalationEngine] = None,
    ) -> None:
        self._sentiment = sentiment_service or SentimentService()
        self._legacy = legacy_engine or EscalationEngine()

    def analyze(
        self,
        user_message: str,
        agent_config: AgentConfig,
        *,
        current_state: ConversationState = ConversationState.GREETING,
        sentiment_history: Optional[list[SentimentLevel]] = None,
    ) -> EscalationAnalysisResult:
        """
        Evaluate whether the conversation should be escalated.

        Returns structured result with category and reason.
        """
        text = user_message.strip()
        if not text:
            return EscalationAnalysisResult(should_escalate=False)

        history = list(sentiment_history or [])
        current_sentiment = self._sentiment.analyze(text)
        history.append(current_sentiment)

        category_result = self._match_category_rules(text, agent_config)
        if category_result:
            category, reason = category_result
            return EscalationAnalysisResult(
                should_escalate=True,
                category=category,
                reason=reason,
                sentiment=current_sentiment,
            )

        if self._sentiment.should_escalate_for_sentiment(current_sentiment, history[:-1]):
            return EscalationAnalysisResult(
                should_escalate=True,
                category=EscalationCategory.NEGATIVE_SENTIMENT,
                reason="Repeated negative customer sentiment detected",
                sentiment=current_sentiment,
            )

        if current_state == ConversationState.OBJECTION_HANDLING:
            refusal_patterns = [
                r"\b(no|not interested|don't call|stop calling|leave me alone)\b",
            ]
            if any(re.search(p, text, re.IGNORECASE) for p in refusal_patterns):
                negative_in_objection = sum(
                    1 for s in history if s in (SentimentLevel.NEGATIVE, SentimentLevel.VERY_NEGATIVE)
                )
                if negative_in_objection >= 1:
                    return EscalationAnalysisResult(
                        should_escalate=True,
                        category=EscalationCategory.NEGATIVE_SENTIMENT,
                        reason="Customer repeatedly refused assistance during objection handling",
                        sentiment=current_sentiment,
                    )

        legacy = self._legacy.check(text, agent_config)
        if legacy.escalate:
            category = _TRIGGER_TO_CATEGORY.get(
                legacy.reason,
                EscalationCategory.CUSTOMER_REQUESTED_HUMAN,
            )
            return EscalationAnalysisResult(
                should_escalate=True,
                category=category,
                reason=self._reason_for_trigger(legacy.reason),
                sentiment=current_sentiment,
            )

        return EscalationAnalysisResult(
            should_escalate=False,
            sentiment=current_sentiment,
        )

    def get_transfer_message(self, category: EscalationCategory) -> str:
        """Natural AI messaging before transfer."""
        return _TRANSFER_MESSAGES.get(
            category,
            "Let me connect you with a banking representative who can assist you further.",
        )

    def map_category_to_legacy_reason(self, category: EscalationCategory) -> str:
        """Map standardized category to legacy trigger id for tool compatibility."""
        mapping = {
            EscalationCategory.CUSTOMER_REQUESTED_HUMAN: "customer_requested_human",
            EscalationCategory.COMPLAINT: "complaint",
            EscalationCategory.LEGAL_QUERY: "legal_clarification",
            EscalationCategory.ACCOUNT_DISPUTE: "account_dispute",
            EscalationCategory.NEGATIVE_SENTIMENT: "customer_angry",
            EscalationCategory.HIGH_RISK_QUERY: "high_risk_query",
        }
        return mapping.get(category, "customer_requested_human")

    def _match_category_rules(
        self,
        text: str,
        agent_config: AgentConfig,
    ) -> Optional[tuple[EscalationCategory, str]]:
        normalized = text.lower()

        agent_rules = self._agent_rules_to_categories(agent_config.escalation_rules)
        for category, patterns, reason in agent_rules + _CATEGORY_RULES:
            if any(re.search(p, normalized, re.IGNORECASE) for p in patterns):
                return category, reason

        return None

    @staticmethod
    def _agent_rules_to_categories(
        rules: list[EscalationRule],
    ) -> list[tuple[EscalationCategory, list[str], str]]:
        result: list[tuple[EscalationCategory, list[str], str]] = []
        for rule in rules:
            category = _TRIGGER_TO_CATEGORY.get(
                rule.trigger,
                EscalationCategory.CUSTOMER_REQUESTED_HUMAN,
            )
            result.append((category, rule.patterns, rule.description or rule.trigger))
        return result

    @staticmethod
    def _reason_for_trigger(trigger: str) -> str:
        reasons = {
            "customer_requested_human": "Customer requested human assistance",
            "customer_angry": "Customer appears angry or frustrated",
            "abusive_language": "Customer used aggressive language",
            "account_dispute": "Customer disputes account information",
            "legal_clarification": "Customer requested legal clarification",
            "settlement_request": "Customer requested settlement or negotiation",
            "account_details_unavailable": "Customer requested unavailable account details",
            "complaint": "Customer requested complaint handling",
            "high_risk_query": "Customer raised a high-risk banking concern",
        }
        return reasons.get(trigger, "Escalation required per agent rules")
