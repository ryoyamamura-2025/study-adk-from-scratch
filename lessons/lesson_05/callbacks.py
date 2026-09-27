from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext


def _print_context(context: CallbackContext | ToolContext) -> None:
    print("  agent_name:", context.agent_name)
    print("  invocation_id:", context.invocation_id)
    print("  session_id:", context.session.id)
    print("  state:", dict(context.state))


# -----------------------------
# Agent lifecycle callbacks
# -----------------------------
def before_agent_callback(
    callback_context: CallbackContext,
):
    print("\n[CALLBACK] before_agent")
    _print_context(callback_context)
    return None


def after_agent_callback(
    callback_context: CallbackContext,
):
    print("\n[CALLBACK] after_agent")
    _print_context(callback_context)
    return None


# -----------------------------
# Model lifecycle callbacks
# -----------------------------
def before_model_callback(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> LlmResponse | None:
    print("\n[CALLBACK] before_model")
    _print_context(callback_context)
    print("  contents_count:", len(llm_request.contents or []))

    if llm_request.contents:
        last_content = llm_request.contents[-1]
        print("  last_content_role:", last_content.role)

    return None


def after_model_callback(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> LlmResponse | None:
    print("\n[CALLBACK] after_model")
    _print_context(callback_context)

    if llm_response.content:
        print("  response_role:", llm_response.content.role)

        part_types = []
        for part in llm_response.content.parts or []:
            if part.function_call:
                part_types.append("function_call")
            elif part.function_response:
                part_types.append("function_response")
            elif part.text:
                part_types.append("text")
            else:
                part_types.append("other")

        print("  response_part_types:", part_types)

    return None


# -----------------------------
# Tool lifecycle callbacks
# -----------------------------
def before_tool_callback(
    tool: BaseTool,
    args: dict,
    tool_context: ToolContext,
) -> dict | None:
    print("\n[CALLBACK] before_tool")
    _print_context(tool_context)
    print("  tool:", tool.name)
    print("  args:", args)
    return None


def after_tool_callback(
    tool: BaseTool,
    args: dict,
    tool_context: ToolContext,
    tool_response: dict,
) -> dict | None:
    print("\n[CALLBACK] after_tool")
    _print_context(tool_context)
    print("  tool:", tool.name)
    print("  args:", args)
    print("  tool_response:", tool_response)
    return None
