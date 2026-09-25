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
from google.adk.tools.tool_context import ToolContext
from google.genai import types

# -----------------------------
# Artifactの保存と読み込み
# -----------------------------
async def save_text_file(filename: str, content: str, tool_context: ToolContext) -> dict:
    """
    テキストをArtifactとしてファイル名を指定して保存します。

    Args:
        filename: 保存するファイル名
        content: 保存するテキスト内容
    """
    artifact = types.Part.from_text(text=content)
    version = await tool_context.save_artifact(
        filename=filename,
        artifact=artifact
    )

    return {
        "filename": filename,
        "version": version,
        "note": f"{filename} was saved successfully. If you load this file, use `load_text_file` tool"
    }

async def list_text_files(tool_context: ToolContext) -> dict:
    """
    保存されているArtifactの一覧を取得します。
    """
    artifacts = await tool_context.list_artifacts()

    return {
        "artifacts": artifacts
    }

async def load_text_file(filename: str, tool_context: ToolContext) -> dict:
    """
    ファイル名を指定してテキストをArtifactから読み込みます。

    Args:
        filename: 読み込むファイル名
    """
    artifact = await tool_context.load_artifact(
        filename=filename,
    )

    return {
        "filename": filename,
        "content": artifact.text if artifact else None,
    }

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
# skills_dir = Path(__file__).parent / "skills"
# skills = load_skills_from_dir(skills_dir)
# skill_toolset = SkillToolset(
#     skills=skills,
#     additional_tools=[printer_mcp]
# )

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
    tools=[
        get_weather, 
        # skill_toolset, 
        save_text_file,
        list_text_files,
        load_text_file
    ]
)

app = App(
    name="study_app",
    root_agent=root_agent
)