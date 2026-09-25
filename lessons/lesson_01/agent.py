import os
from dotenv import load_dotenv
load_dotenv()

from google.adk.apps import App
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
# from google.adk.models import Gemini
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StreamableHTTPConnectionParams
)
from google.genai import types

# サンプルTool
def get_weather(city: str) -> dict:
    """
    指定された都市の天気を返します

    Args:
        city: 都市名
    """
    return {
        "city": city,
        "weather": "sunny",
        "temperature": 25
    }

# サンプルMCP
printer_mcp = McpToolset(
    connection_params=StreamableHTTPConnectionParams(
        url=os.environ["PRINTER_MCP_URL"]
    ) 
)

root_agent = LlmAgent(
    name="study_agent",
    # model=Gemini(model="gemini-3.5-flash"),
    model=LiteLlm(
        model="vertex_ai/meta/llama-4-scout-17b-16e-instruct-maas"
    ),
    generate_content_config=types.GenerateContentConfig(
        max_output_tokens=256,
    ),
    instruction="あなたは優秀なアシスタントです",
    tools=[get_weather, printer_mcp]
)

app = App(
    name="study_app",
    root_agent=root_agent
)