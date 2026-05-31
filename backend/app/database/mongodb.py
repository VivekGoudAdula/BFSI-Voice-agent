"""MongoDB client and database lifecycle management."""

import logging
from typing import Optional

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from app.core.config import Settings, get_settings
from app.core.exceptions import DatabaseError

logger = logging.getLogger(__name__)


class MongoDB:
    """Singleton-style MongoDB connection manager."""

    client: Optional[MongoClient] = None
    db: Optional[Database] = None

    @classmethod
    def connect(cls, settings: Optional[Settings] = None) -> None:
        """Establish connection to MongoDB."""
        settings = settings or get_settings()
        try:
            cls.client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=5000)
            cls.client.admin.command("ping")
            cls.db = cls.client[settings.database_name]
            logger.info("Connected to MongoDB database=%s", settings.database_name)
        except Exception as exc:
            logger.error("MongoDB connection failed: %s", exc)
            raise DatabaseError(f"Unable to connect to MongoDB: {exc}") from exc

    @classmethod
    def disconnect(cls) -> None:
        """Close MongoDB connection."""
        if cls.client:
            cls.client.close()
            cls.client = None
            cls.db = None
            logger.info("Disconnected from MongoDB")

    @classmethod
    def get_db(cls) -> Database:
        """Return active database instance."""
        if cls.db is None:
            raise DatabaseError("Database is not connected")
        return cls.db

    @classmethod
    def customers(cls) -> Collection:
        return cls.get_db()["customers"]

    @classmethod
    def calls(cls) -> Collection:
        return cls.get_db()["calls"]

    @classmethod
    def conversation_sessions(cls) -> Collection:
        return cls.get_db()["conversation_sessions"]

    @classmethod
    def transcripts(cls) -> Collection:
        return cls.get_db()["transcripts"]

    @classmethod
    def agent_configs(cls) -> Collection:
        return cls.get_db()["agent_configs"]

    @classmethod
    def conversation_analytics(cls) -> Collection:
        return cls.get_db()["conversation_analytics"]

    @classmethod
    def callbacks(cls) -> Collection:
        return cls.get_db()["callbacks"]

    @classmethod
    def tool_execution_logs(cls) -> Collection:
        return cls.get_db()["tool_execution_logs"]

    @classmethod
    def conversation_summaries(cls) -> Collection:
        return cls.get_db()["conversation_summaries"]

    @classmethod
    def lead_status_updates(cls) -> Collection:
        return cls.get_db()["lead_status_updates"]

    @classmethod
    def call_outcomes(cls) -> Collection:
        return cls.get_db()["call_outcomes"]

    @classmethod
    def campaigns(cls) -> Collection:
        return cls.get_db()["campaigns"]

    @classmethod
    def campaign_customers(cls) -> Collection:
        return cls.get_db()["campaign_customers"]

    @classmethod
    def campaign_runs(cls) -> Collection:
        return cls.get_db()["campaign_runs"]

    @classmethod
    def campaign_analytics(cls) -> Collection:
        return cls.get_db()["campaign_analytics"]

    @classmethod
    def escalations(cls) -> Collection:
        return cls.get_db()["escalations"]

    @classmethod
    def human_handoff_logs(cls) -> Collection:
        return cls.get_db()["human_handoff_logs"]

    @classmethod
    def transfer_queue(cls) -> Collection:
        return cls.get_db()["transfer_queue"]

    @classmethod
    def handoff_context(cls) -> Collection:
        return cls.get_db()["handoff_context"]
