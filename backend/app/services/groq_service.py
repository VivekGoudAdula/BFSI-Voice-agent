"""Groq LLM integration with native tool/function calling."""

import json
import logging
import time
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from app.services.latency_tracker import LatencyTracker

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
        self._fallback_model = settings.groq_fallback_model.strip()
        self._voice_max_tokens = settings.groq_voice_max_tokens

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
        enable_tools: bool = True,
        latency_tracker: Optional["LatencyTracker"] = None,
    ) -> tuple[str, float, list[str], dict[str, int]]:
        """
        Generate a response using Groq tool calling.

        Executes tools when the LLM requests them, feeds results back,
        and returns the final customer-facing response.

        Returns:
            Tuple of (response_text, total_latency_ms, tools_used, token_usage).
        """
        full_system = system_prompt
        api_messages = self._build_messages(full_system, messages)
        tools_used: list[str] = []
        total_latency = 0.0
        prompt_tokens_total = 0
        completion_tokens_total = 0
        total_tokens_total = 0

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

        tool_choice: Any = "auto" if tools and enable_tools else None
        payload_base: dict[str, Any] = {
            "model": self._model,
            "temperature": 0.2,
            "max_tokens": self._voice_max_tokens,
        }
        if tools and enable_tools:
            payload_base["tools"] = tools
            payload_base["tool_choice"] = tool_choice

        if latency_tracker:
            latency_tracker.mark("LLM_REQUEST_START")

        for iteration in range(MAX_TOOL_ITERATIONS):
            payload = {**payload_base, "messages": api_messages}
            data, latency_ms = await self._call_api(payload)
            total_latency += latency_ms

            usage = data.get("usage") or {}
            prompt_tokens_total += int(usage.get("prompt_tokens") or 0)
            completion_tokens_total += int(usage.get("completion_tokens") or 0)
            total_tokens_total += int(usage.get("total_tokens") or 0)

            choice = data["choices"][0]
            message = choice["message"]
            tool_calls = message.get("tool_calls")

            content = (message.get("content") or "").strip()
            if content and latency_tracker and "LLM_FIRST_TOKEN" not in latency_tracker._marks:
                latency_tracker.mark("LLM_FIRST_TOKEN")

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

            if content:
                if latency_tracker:
                    latency_tracker.mark("LLM_COMPLETE")
                log_with_context(
                    logger,
                    logging.INFO,
                    "Groq tool response generated",
                    groq_ms=round(total_latency, 1),
                    tools_used=tools_used,
                    event="groq_tool_response",
                )
                return (
                    content,
                    total_latency,
                    tools_used,
                    {
                        "prompt_tokens": prompt_tokens_total,
                        "response_tokens": completion_tokens_total,
                        "total_tokens": total_tokens_total,
                    },
                )

        return (
            "I apologize, I was unable to complete that request. "
            "Let me connect you with a banking representative.",
            total_latency,
            tools_used,
            {
                "prompt_tokens": prompt_tokens_total,
                "response_tokens": completion_tokens_total,
                "total_tokens": total_tokens_total,
            },
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

        primary_model = payload.get("model") or self._model
        models = [primary_model]
        if self._fallback_model and self._fallback_model not in models:
            models.append(self._fallback_model)

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        last_error: GroqServiceError | None = None
        start = time.perf_counter()

        for idx, model in enumerate(models):
            request_payload = {**payload, "model": model}
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    response = await client.post(
                        GROQ_CHAT_URL,
                        json=request_payload,
                        headers=headers,
                    )
                    response.raise_for_status()
                    data = response.json()
                if idx > 0:
                    log_with_context(
                        logger,
                        logging.INFO,
                        f"Groq request succeeded on fallback model {model}",
                        event="groq_fallback_success",
                    )
                latency_ms = (time.perf_counter() - start) * 1000
                return data, latency_ms
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text[:500] if exc.response else str(exc)
                is_rate_limit = "rate_limit" in detail.lower()
                if is_rate_limit and idx < len(models) - 1:
                    log_with_context(
                        logger,
                        logging.WARNING,
                        f"Groq rate limit on {model}, retrying with {models[idx + 1]}",
                        event="groq_fallback_retry",
                    )
                    last_error = GroqServiceError(detail)
                    continue
                log_with_context(
                    logger, logging.ERROR, f"Groq API HTTP error: {detail}", event="groq_error"
                )
                raise GroqServiceError(detail) from exc
            except httpx.RequestError as exc:
                log_with_context(
                    logger, logging.ERROR, f"Groq request failed: {exc}", event="groq_error"
                )
                raise GroqServiceError(str(exc)) from exc

        if last_error:
            raise last_error
        raise GroqServiceError("Groq request failed")

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
