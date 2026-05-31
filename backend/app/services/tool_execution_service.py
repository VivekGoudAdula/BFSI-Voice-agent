"""Tool execution logging service."""

import logging
import time
from datetime import datetime, timezone
from typing import Any

from pymongo.errors import PyMongoError

from app.database.mongodb import MongoDB
from app.models.tool import ToolExecutionLogResponse
from app.tools.base import ToolContext, ToolResult
from app.utils.mongo_query import find_sorted

logger = logging.getLogger(__name__)


class ToolExecutionService:
    """Executes tools with audit logging to MongoDB."""

    def __init__(self, registry: Any, audit_service: Any = None) -> None:
        self._registry = registry
        self._audit = audit_service

    async def execute_and_log(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> tuple[ToolResult, float]:
        """
        Execute a tool and persist an audit log entry.

        Returns:
            Tuple of (ToolResult, execution_time_ms).
        """
        start = time.perf_counter()
        result = await self._registry.execute(tool_name, arguments, context)
        elapsed_ms = (time.perf_counter() - start) * 1000

        self._log_execution(
            call_id=context.call_id,
            call_sid=context.call_sid,
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            execution_time_ms=elapsed_ms,
        )

        return result, elapsed_ms

    def _log_execution(
        self,
        call_id: str,
        call_sid: str,
        tool_name: str,
        arguments: dict[str, Any],
        result: ToolResult,
        execution_time_ms: float,
    ) -> None:
        doc: dict[str, Any] = {
            "call_id": call_id,
            "call_sid": call_sid,
            "tool_name": tool_name,
            "arguments": arguments,
            "result": result.data if result.success else {"error": result.error},
            "success": result.success,
            "execution_time_ms": round(execution_time_ms, 2),
            "executed_at": datetime.now(timezone.utc),
        }

        try:
            MongoDB.tool_execution_logs().insert_one(doc)
        except PyMongoError as exc:
            logger.error("Failed to log tool execution: %s", exc)

        if self._audit:
            self._audit.on_tool_executed(
                call_sid=call_sid,
                call_id=call_id,
                tool_name=tool_name,
                arguments=arguments,
                result=doc["result"],
                execution_time_ms=execution_time_ms,
            )

        logger.info(
            "Tool executed | tool=%s success=%s ms=%.1f call_id=%s",
            tool_name,
            result.success,
            execution_time_ms,
            call_id,
        )

    def get_logs_by_call(self, call_id: str) -> list[ToolExecutionLogResponse]:
        """Retrieve tool execution logs for a call."""
        try:
            docs = find_sorted(
                MongoDB.tool_execution_logs(),
                {"call_id": call_id},
                sort_field="executed_at",
                sort_direction=1,
            )
            return [self._serialize(doc) for doc in docs]
        except PyMongoError as exc:
            logger.error("Failed to fetch tool logs: %s", exc)
            return []

    def get_recent_logs(self, limit: int = 50) -> list[ToolExecutionLogResponse]:
        """Retrieve recent tool execution logs."""
        try:
            docs = find_sorted(
                MongoDB.tool_execution_logs(),
                sort_field="executed_at",
                sort_direction=-1,
                limit=limit,
            )
            return [self._serialize(doc) for doc in docs]
        except PyMongoError as exc:
            logger.error("Failed to fetch tool logs: %s", exc)
            return []

    @staticmethod
    def _serialize(doc: dict[str, Any]) -> ToolExecutionLogResponse:
        return ToolExecutionLogResponse(
            id=str(doc["_id"]),
            call_id=doc.get("call_id", ""),
            call_sid=doc.get("call_sid", ""),
            tool_name=doc["tool_name"],
            arguments=doc.get("arguments", {}),
            result=doc.get("result", {}),
            success=doc.get("success", False),
            execution_time_ms=doc.get("execution_time_ms", 0),
            executed_at=doc["executed_at"],
        )
