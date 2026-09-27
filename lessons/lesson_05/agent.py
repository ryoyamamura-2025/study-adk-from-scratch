from dotenv import load_dotenv

load_dotenv()

from google.adk.apps import App
from google.adk.agents import LlmAgent
from google.adk.models import Gemini

from callbacks import (
    after_agent_callback,
    after_model_callback,
    after_tool_callback,
    before_agent_callback,
    before_model_callback,
    before_tool_callback,
)


# -----------------------------
# Tool
# -----------------------------
def echo_text(text: str) -> dict:
    """
    入力された文字列をそのまま返します。

    Args:
        text: そのまま返す文字列
    """
    print("\n[TOOL BODY] echo_text")
    print("  text:", text)

    return {
        "echo": text,
    }


root_agent = LlmAgent(
    name="study_agent",
    model=Gemini(model="gemini-3.5-flash"),
    instruction=(
        "あなたはCallbackの学習用Agentです。"
        "ユーザーから受け取った文字列を回答する前に、"
        "必ずecho_text Toolをちょうど1回呼び出してください。"
        "Toolの結果を確認してから、短く最終回答してください。"
    ),
    tools=[echo_text],
    before_agent_callback=before_agent_callback,
    after_agent_callback=after_agent_callback,
    before_model_callback=before_model_callback,
    after_model_callback=after_model_callback,
    before_tool_callback=before_tool_callback,
    after_tool_callback=after_tool_callback,
)

app = App(
    name="study_app",
    root_agent=root_agent,
)
