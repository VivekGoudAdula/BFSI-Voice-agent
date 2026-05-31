"""Detect when a customer explicitly wants a payment link SMS."""

import re

_EXPLICIT_LINK_REQUEST = re.compile(
    r"\b("
    r"send(\s+me)?(\s+the)?(\s+payment)?\s*link"
    r"|text\s+me(\s+the)?(\s+payment)?\s*link"
    r"|sms\s+me(\s+the)?(\s+payment)?\s*link"
    r"|payment\s+link"
    r"|link\s+please"
    r")\b",
    re.IGNORECASE,
)

_SHORT_AFFIRMATIVE = re.compile(
    r"^(yes|yeah|yep|yup|sure|ok|okay|please|go ahead)[.!,\s]*$",
    re.IGNORECASE,
)

_ASSISTANT_LINK_OFFER = re.compile(
    r"\b(send(\s+you)?(\s+a)?\s+link|payment\s+link|link\s+to\s+pay)\b",
    re.IGNORECASE,
)


def user_requested_payment_link(messages: list[dict[str, str]]) -> bool:
    """
    Return True only when the customer has asked for or accepted a payment link SMS.

    Requires either an explicit link request in the latest user message, or a short
    affirmative (yes/yep) after the assistant offered to send a link.
    """
    if not messages:
        return False

    last_user_idx = None
    for idx in range(len(messages) - 1, -1, -1):
        if messages[idx].get("role") == "user":
            last_user_idx = idx
            break

    if last_user_idx is None:
        return False

    last_user = messages[last_user_idx].get("content", "").strip()
    if not last_user:
        return False

    if _EXPLICIT_LINK_REQUEST.search(last_user):
        return True

    if not _SHORT_AFFIRMATIVE.match(last_user):
        return False

    for msg in reversed(messages[:last_user_idx]):
        if msg.get("role") == "assistant":
            return bool(_ASSISTANT_LINK_OFFER.search(msg.get("content", "")))

    return False
