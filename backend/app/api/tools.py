"""Tool and callback management endpoints."""

from fastapi import APIRouter, Depends

from app.core.dependencies import (
    get_callback_service,
    get_tool_execution_service,
    get_tool_registry,
)
from app.models.tool import (
    CallbackResponse,
    ToolCallRequest,
    ToolCallResponse,
    ToolExecutionLogResponse,
)
from app.services.callback_service import CallbackService
from app.services.tool_execution_service import ToolExecutionService
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry

router = APIRouter(prefix="/tools", tags=["Tools"])


@router.get(
    "",
    summary="List available tools",
)
def list_tools(
    registry: ToolRegistry = Depends(get_tool_registry),
) -> list[dict]:
    return [
        {"name": t.name, "description": t.description}
        for t in registry.list_tools()
    ]


@router.post(
    "/execute",
    response_model=ToolCallResponse,
    summary="Manually execute a tool (testing/debug)",
)
async def execute_tool(
    payload: ToolCallRequest,
    executor: ToolExecutionService = Depends(get_tool_execution_service),
) -> ToolCallResponse:
    context = ToolContext(
        customer_id=payload.customer_id,
        call_id=payload.call_id,
        call_sid=payload.call_sid,
        identity_verified=True,
    )
    result, elapsed = await executor.execute_and_log(
        payload.tool_name,
        payload.arguments,
        context,
    )
    return ToolCallResponse(
        tool_name=payload.tool_name,
        success=result.success,
        result=result.data if result.success else {"error": result.error},
        execution_time_ms=elapsed,
    )


@router.get(
    "/logs",
    response_model=list[ToolExecutionLogResponse],
    summary="Recent tool execution logs",
)
def get_tool_logs(
    limit: int = 50,
    service: ToolExecutionService = Depends(get_tool_execution_service),
) -> list[ToolExecutionLogResponse]:
    return service.get_recent_logs(limit=limit)


@router.get(
    "/logs/call/{call_id}",
    response_model=list[ToolExecutionLogResponse],
    summary="Tool execution logs for a call",
)
def get_call_tool_logs(
    call_id: str,
    service: ToolExecutionService = Depends(get_tool_execution_service),
) -> list[ToolExecutionLogResponse]:
    return service.get_logs_by_call(call_id)


@router.get(
    "/callbacks",
    response_model=list[CallbackResponse],
    summary="List all scheduled callbacks",
)
def list_callbacks(
    service: CallbackService = Depends(get_callback_service),
) -> list[CallbackResponse]:
    return service.list_all()


@router.get(
    "/callbacks/customer/{customer_id}",
    response_model=list[CallbackResponse],
    summary="List callbacks for a customer",
)
def list_customer_callbacks(
    customer_id: str,
    service: CallbackService = Depends(get_callback_service),
) -> list[CallbackResponse]:
    return service.list_by_customer(customer_id)
