"""Conversation turn state management for realtime calls."""

from enum import Enum


class TurnState(str, Enum):
    AI_TURN = "ai_turn"
    CUSTOMER_TURN = "customer_turn"
    PROCESSING = "processing"
    INTERRUPTED = "interrupted"


class TurnManager:
    """Tracks turn ownership and interruption events."""

    def set_ai_turn(self, session: object) -> None:
        session.active_turn = TurnState.AI_TURN.value

    def set_customer_turn(self, session: object) -> None:
        session.active_turn = TurnState.CUSTOMER_TURN.value

    def set_processing(self, session: object) -> None:
        session.active_turn = TurnState.PROCESSING.value

    def mark_interruption(self, session: object) -> None:
        session.active_turn = TurnState.INTERRUPTED.value
        session.interruption_count = int(getattr(session, "interruption_count", 0)) + 1
