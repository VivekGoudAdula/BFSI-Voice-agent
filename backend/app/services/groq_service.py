"""Groq LLM integration with native tool/function calling."""

import json
import logging
import time
from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import GroqServiceError
from app.core.logging_config import log_with_context
from app.tools.base import ToolContext

logger = logging.getLogger(__name__)

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
MAX_TOOL_ITERATIONS = 3


class GroqService:
    """Generates assistant responses using Groq with optional tool calling."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._api_key = settings.groq_api_key
        self._model = settings.groq_model

    async def generate_response(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
        *,
        regeneration_hint: str = "",
    ) -> tuple[str, float]:
        """Generate a plain text response (no tools)."""
        full_system = system_prompt
        if regeneration_hint:
            full_system = f"{system_prompt}\n\n{regeneration_hint}"

        api_messages = self._build_messages(full_system, messages)
        data, latency_ms = await self._call_api({"messages": api_messages})
        content = self._extract_content(data)
        return content, latency_ms

    async def generate_with_tools(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
        tools: list[dict[str, Any]],
        tool_executor: Any,
        context: ToolContext,
        *,
        forced_tool: str | None = None,
        forced_tool_args: dict[str, Any] | None = None,
    ) -> tuple[str, float, list[str]]:
        """
        Generate a response using Groq tool calling.

        Executes tools when the LLM requests them, feeds results back,
        and returns the final customer-facing response.

        Returns:
            Tuple of (response_text, total_latency_ms, tools_used).
        """
        full_system = system_prompt
        api_messages = self._build_messages(full_system, messages)
        tools_used: list[str] = []
        total_latency = 0.0

        # Handle pre-triggered tool (e.g. escalation → transfer_to_human)
        if forced_tool:
            args = forced_tool_args or {}
            result, exec_ms = await tool_executor.execute_and_log(
                forced_tool, args, context
            )
            tools_used.append(forced_tool)
            api_messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": f"forced_{forced_tool}",
                    "type": "function",
                    "function": {
                        "name": forced_tool,
                        "arguments": json.dumps(args),
                    },
                }],
            })
            api_messages.append({
                "role": "tool",
                "tool_call_id": f"forced_{forced_tool}",
                "content": json.dumps(result.data if result.success else {"error": result.error}),
            })

        tool_choice: Any = "auto" if tools else None
        payload_base: dict[str, Any] = {
            "model": self._model,
            "temperature": 0.3,
            "max_tokens": 200,
        }
        if tools:
            payload_base["tools"] = tools
            payload_base["tool_choice"] = tool_choice

        for iteration in range(MAX_TOOL_ITERATIONS):
            payload = {**payload_base, "messages": api_messages}
            data, latency_ms = await self._call_api(payload)
            total_latency += latency_ms

            choice = data["choices"][0]
            message = choice["message"]
            tool_calls = message.get("tool_calls")

            if tool_calls:
                api_messages.append(message)
                for tc in tool_calls:
                    fn = tc["function"]
                    tool_name = fn["name"]
                    try:
                        args = json.loads(fn["arguments"])
                    except json.JSONDecodeError:
                        args = {}

                    result, _ = await tool_executor.execute_and_log(
                        tool_name, args, context
                    )
                    tools_used.append(tool_name)

                    api_messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(
                            result.data if result.success else {"error": result.error}
                        ),
                    })
                continue

            content = (message.get("content") or "").strip()
            if content:
                log_with_context(
                    logger,
                    logging.INFO,
                    "Groq tool response generated",
                    groq_ms=round(total_latency, 1),
                    tools_used=tools_used,
                    event="groq_tool_response",
                )
                return content, total_latency, tools_used

        return (
            "I apologize, I was unable to complete that request. "
            "Let me connect you with a banking representative.",
            total_latency,
            tools_used,
        )

    def _build_messages(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        api_messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]
        for msg in messages:
            if msg["role"] in ("user", "assistant"):
                api_messages.append({"role": msg["role"], "content": msg["content"]})
        return api_messages

    async def _call_api(self, payload: dict[str, Any]) -> tuple[dict[str, Any], float]:
        if not self._api_key:
            raise GroqServiceError("GROQ_API_KEY must be configured")

        payload.setdefault("model", self._model)
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    GROQ_CHAT_URL,
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500] if exc.response else str(exc)
            log_with_context(logger, logging.ERROR, f"Groq API HTTP error: {detail}", event="groq_error")
            raise GroqServiceError(detail) from exc
        except httpx.RequestError as exc:
            log_with_context(logger, logging.ERROR, f"Groq request failed: {exc}", event="groq_error")
            raise GroqServiceError(str(exc)) from exc

        latency_ms = (time.perf_counter() - start) * 1000
        return data, latency_ms

    @staticmethod
    def _extract_content(data: dict[str, Any]) -> str:
        try:
            content = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, AttributeError) as exc:
            raise GroqServiceError("Invalid response from Groq API") from exc

        if not content:
            content = (
                "I apologize, I did not catch that. "
                "Could you please repeat your question?"
            )
        return content
