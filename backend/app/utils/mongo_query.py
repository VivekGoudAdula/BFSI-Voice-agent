"""MongoDB query helpers compatible with Azure Cosmos DB (MongoDB API)."""

import logging
from datetime import datetime
from typing import Any, Optional

from pymongo.collection import Collection
from pymongo.errors import PyMongoError

logger = logging.getLogger(__name__)


def is_cosmos_sort_error(exc: PyMongoError) -> bool:
    """True when Cosmos DB rejects sort because the field is not indexed."""
    msg = str(exc).lower()
    return "order-by item is excluded" in msg or "index path corresponding" in msg


def _sort_key(doc: dict[str, Any], field: str, reverse: bool) -> Any:
    value = doc.get(field)
    if value is None:
        return datetime.min if reverse else datetime.max
    return value


def find_sorted(
    collection: Collection,
    query: Optional[dict[str, Any]] = None,
    *,
    sort_field: str,
    sort_direction: int = -1,
    limit: int = 0,
    skip: int = 0,
) -> list[dict[str, Any]]:
    """
    Find documents with server-side sort.

    Falls back to in-memory sort when Azure Cosmos DB excludes the
    sort field from its indexing policy (common on default Cosmos accounts).
    """
    query = query or {}
    reverse = sort_direction < 0

    try:
        cursor = collection.find(query).sort(sort_field, sort_direction)
        if skip:
            cursor = cursor.skip(skip)
        if limit > 0:
            cursor = cursor.limit(limit)
        return list(cursor)
    except PyMongoError as exc:
        if not is_cosmos_sort_error(exc):
            raise

        logger.debug(
            "Server-side sort on '%s' unavailable; sorting in memory",
            sort_field,
        )
        docs = list(collection.find(query))
        docs.sort(key=lambda d: _sort_key(d, sort_field, reverse), reverse=reverse)
        if skip:
            docs = docs[skip:]
        if limit > 0:
            docs = docs[:limit]
        return docs
