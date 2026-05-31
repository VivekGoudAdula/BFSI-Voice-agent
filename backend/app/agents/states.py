"""Conversation state machine for BFSI voice agents."""

from enum import Enum


class ConversationState(str, Enum):
    """Tracked states during a banking voice call."""

    GREETING = "GREETING"
    IDENTITY_VERIFICATION = "IDENTITY_VERIFICATION"
    EMI_DISCUSSION = "EMI_DISCUSSION"
    OBJECTION_HANDLING = "OBJECTION_HANDLING"
    CALLBACK_SCHEDULING = "CALLBACK_SCHEDULING"
    ESCALATION = "ESCALATION"
    CALL_COMPLETION = "CALL_COMPLETION"


# Valid transitions keyed by current state
STATE_TRANSITIONS: dict[ConversationState, set[ConversationState]] = {
    ConversationState.GREETING: {
        ConversationState.IDENTITY_VERIFICATION,
        ConversationState.ESCALATION,
        ConversationState.CALL_COMPLETION,
    },
    ConversationState.IDENTITY_VERIFICATION: {
        ConversationState.EMI_DISCUSSION,
        ConversationState.ESCALATION,
        ConversationState.CALL_COMPLETION,
    },
    ConversationState.EMI_DISCUSSION: {
        ConversationState.OBJECTION_HANDLING,
        ConversationState.CALLBACK_SCHEDULING,
        ConversationState.ESCALATION,
        ConversationState.CALL_COMPLETION,
    },
    ConversationState.OBJECTION_HANDLING: {
        ConversationState.EMI_DISCUSSION,
        ConversationState.CALLBACK_SCHEDULING,
        ConversationState.ESCALATION,
        ConversationState.CALL_COMPLETION,
    },
    ConversationState.CALLBACK_SCHEDULING: {
        ConversationState.CALL_COMPLETION,
        ConversationState.ESCALATION,
    },
    ConversationState.ESCALATION: {
        ConversationState.CALL_COMPLETION,
    },
    ConversationState.CALL_COMPLETION: set(),
}


def can_transition(
    current: ConversationState,
    target: ConversationState,
) -> bool:
    """Return True if the state machine allows the transition."""
    return target in STATE_TRANSITIONS.get(current, set())


def infer_next_state(
    current: ConversationState,
    *,
    identity_verified: bool = False,
    objection_detected: bool = False,
    callback_requested: bool = False,
    escalated: bool = False,
    call_ending: bool = False,
) -> ConversationState:
    """Infer the next conversation state from turn signals."""
    if escalated:
        return ConversationState.ESCALATION
    if call_ending:
        return ConversationState.CALL_COMPLETION
    if current == ConversationState.GREETING:
        return ConversationState.IDENTITY_VERIFICATION
    if current == ConversationState.IDENTITY_VERIFICATION and identity_verified:
        return ConversationState.EMI_DISCUSSION
    if objection_detected:
        return ConversationState.OBJECTION_HANDLING
    if callback_requested:
        return ConversationState.CALLBACK_SCHEDULING
    return current
