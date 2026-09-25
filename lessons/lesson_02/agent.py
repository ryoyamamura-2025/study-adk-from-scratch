import os
from pathlib import Path

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
from google.adk.skills import load_skills_from_dir
from google.adk.tools.skill_toolset import SkillToolset
from google.genai import types

# -----------------------------
# 通常Tool
# -----------------------------
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

# -----------------------------
# Printer MCP
# -----------------------------
printer_mcp = McpToolset(
    connection_params=StreamableHTTPConnectionParams(
        url=os.environ["PRINTER_MCP_URL"]
    ) 
)

# -----------------------------
# Skills
# -----------------------------
skills_dir = Path(__file__).parent / "skills"
skills = load_skills_from_dir(skills_dir)
skill_toolset = SkillToolset(
    skills=skills,
    additional_tools=[printer_mcp]
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
    tools=[get_weather, skill_toolset]
)

app = App(
    name="study_app",
    root_agent=root_agent
)