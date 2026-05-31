"""Tool registry for dynamic tool discovery and execution."""

import logging
from typing import Any

from app.services.banking_service import BankingService
from app.services.callback_service import CallbackService
from app.services.customer_service import CustomerService
from app.services.human_handoff_service import HumanHandoffService
from app.services.sms_service import SMSService
from app.tools.base import Tool, ToolContext, ToolResult
from app.tools.banking_tools import (
    CheckEmiDueTool,
    CreateSupportTicketTool,
    GetLoanDetailsTool,
    ScheduleCallbackTool,
    SendPaymentLinkTool,
    TransferToHumanTool,
    VerifyCustomerTool,
)

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Central registry for all BFSI agent tools.

    Tools are registered by name and discoverable by the LLM at runtime.
    """

    def __init__(
        self,
        banking_service: BankingService,
        callback_service: CallbackService,
        customer_service: CustomerService,
        human_handoff_service: HumanHandoffService,
        sms_service: SMSService,
    ) -> None:
        self._tools: dict[str, Tool] = {}
        self._register_defaults(
            banking_service,
            callback_service,
            customer_service,
            human_handoff_service,
            sms_service,
        )

    def _register_defaults(
        self,
        banking_service: BankingService,
        callback_service: CallbackService,
        customer_service: CustomerService,
        human_handoff_service: HumanHandoffService,
        sms_service: SMSService,
    ) -> None:
        """Register all BFSI agent tools."""
        defaults: list[Tool] = [
            GetLoanDetailsTool(banking_service),
            CheckEmiDueTool(banking_service),
            ScheduleCallbackTool(callback_service),
            SendPaymentLinkTool(banking_service, customer_service, sms_service),
            TransferToHumanTool(human_handoff_service),
            VerifyCustomerTool(customer_service),
            CreateSupportTicketTool(),
        ]
        for tool in defaults:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        """Add a tool to the registry."""
        self._tools[tool.name] = tool
        logger.debug("Registered tool: %s", tool.name)

    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        """Return all registered tools."""
        return list(self._tools.values())

    def get_openai_schemas(
        self, tool_names: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Return OpenAI/Groq-compatible tool schemas, optionally filtered by name."""
        if tool_names is None:
            return [tool.to_openai_schema() for tool in self._tools.values()]
        return [
            self._tools[name].to_openai_schema()
            for name in tool_names
            if name in self._tools
        ]

    def validate_tool_names(self, tool_names: list[str]) -> list[str]:
        """Return list of unknown tool names."""
        registered = set(self._tools.keys())
        return [name for name in tool_names if name not in registered]

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        """Execute a tool by name with arguments and session context."""
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(success=False, data={}, error=f"Unknown tool: {name}")

        # Inject session context defaults into arguments
        enriched = dict(arguments)
        session_customer_id = (context.customer_id or "").strip()
        llm_customer_id = str(enriched.get("customer_id") or "").strip()
        if session_customer_id:
            if llm_customer_id and llm_customer_id != session_customer_id:
                logger.info(
                    "Tool %s: using session customer_id=%s (LLM provided %r)",
                    name,
                    session_customer_id,
                    llm_customer_id,
                )
            enriched["customer_id"] = session_customer_id
        elif not llm_customer_id:
            enriched["customer_id"] = session_customer_id
        if name == "transfer_to_human":
            if not enriched.get("call_sid"):
                enriched["call_sid"] = context.call_sid
            if not enriched.get("category") and context.extra.get("escalation_category"):
                enriched["category"] = context.extra["escalation_category"]
            if not enriched.get("reason") and context.extra.get("escalation_reason"):
                enriched["reason"] = context.extra["escalation_reason"]

        return await tool.execute(enriched, context)
