"""Base tool interface for the BFSI agent platform."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolContext:
    """Runtime context passed to every tool execution."""

    customer_id: str
    call_id: str
    call_sid: str
    customer_name: str = ""
    identity_verified: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """Standardized tool execution result."""

    success: bool
    data: dict[str, Any]
    error: str = ""


class Tool(ABC):
    """
    Base class for all BFSI agent tools.

    Subclasses define name, description, parameters schema, and execute().
    """

    name: str
    description: str

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """JSON Schema for tool parameters (OpenAI function calling format)."""

    @abstractmethod
    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        """Execute the tool with validated arguments and session context."""

    def to_openai_schema(self) -> dict[str, Any]:
        """Convert tool to OpenAI/Groq function calling schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
