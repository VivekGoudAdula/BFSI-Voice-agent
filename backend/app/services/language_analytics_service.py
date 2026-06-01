"""Multilingual call analytics aggregation."""

import logging
from typing import Any

from pymongo.errors import PyMongoError

from app.core.exceptions import DatabaseError
from app.database.mongodb import MongoDB
from app.models.language import LanguageAnalyticsSummary

logger = logging.getLogger(__name__)


class LanguageAnalyticsService:
    """Track calls by language, distribution, switches, and success rates."""

    def get_summary(self, agent_id: str | None = None) -> LanguageAnalyticsSummary:
        try:
            match: dict[str, Any] = {}
            if agent_id:
                match["agent_id"] = agent_id

            pipeline = [
                *([{"$match": match}] if match else []),
                {
                    "$group": {
                        "_id": None,
                        "calls_by_language": {"$mergeObjects": "$calls_by_language"},
                        "success_by_language": {
                            "$mergeObjects": {"$ifNull": ["$success_by_language", {}]}
                        },
                        "language_switch_events": {"$sum": "$language_switch_events"},
                    }
                },
            ]
            # Aggregate across all agent language_analytics docs
            docs = list(MongoDB.language_analytics().find(match if match else {}))
        except PyMongoError as exc:
            raise DatabaseError(str(exc)) from exc

        calls_by_language: dict[str, int] = {}
        success_by_language: dict[str, int] = {}
        switch_events = 0

        for doc in docs:
            for lang, count in (doc.get("calls_by_language") or {}).items():
                calls_by_language[lang] = calls_by_language.get(lang, 0) + count
            for lang, count in (doc.get("success_by_language") or {}).items():
                success_by_language[lang] = success_by_language.get(lang, 0) + count
            switch_events += doc.get("language_switch_events", 0)

        # Also count from conversation_analytics with language field
        try:
            conv_match: dict[str, Any] = {"language": {"$exists": True, "$ne": ""}}
            if agent_id:
                conv_match["agent_id"] = agent_id
            conv_pipeline = [
                {"$match": conv_match},
                {"$group": {"_id": "$language", "count": {"$sum": 1}}},
            ]
            for row in MongoDB.conversation_analytics().aggregate(conv_pipeline):
                lang = row["_id"]
                calls_by_language[lang] = calls_by_language.get(lang, 0) + row["count"]
        except PyMongoError:
            pass

        total = sum(calls_by_language.values()) or 0
        distribution = {
            lang: round((count / total) * 100, 1) if total else 0.0
            for lang, count in calls_by_language.items()
        }
        success_rate = {
            lang: round(
                (success_by_language.get(lang, 0) / calls_by_language[lang]) * 100, 1
            )
            if calls_by_language.get(lang, 0) > 0
            else 0.0
            for lang in calls_by_language
        }

        return LanguageAnalyticsSummary(
            calls_by_language=calls_by_language,
            language_distribution=distribution,
            language_switch_events=switch_events,
            language_success_rate=success_rate,
            total_calls=total,
        )

    def record_call_language(
        self,
        agent_id: str,
        language: str,
        *,
        successful: bool = False,
    ) -> None:
        from app.repositories.language_repository import LanguageRepository

        LanguageRepository().increment_language_call_stats(
            agent_id, language, successful=successful
        )
