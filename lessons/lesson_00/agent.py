from dotenv import load_dotenv

load_dotenv()

from google.adk.apps import App
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
# from google.adk.models import Gemini
from google.genai import types

root_agent = LlmAgent(
    name="study_agent",
    # model=Gemini(model="gemini-3.5-flash"),
    model=LiteLlm(
        model="vertex_ai/meta/llama-4-scout-17b-16e-instruct-maas"
    ),
    generate_content_config=types.GenerateContentConfig(
        max_output_tokens=256,
    ),
    instruction="あなたは優秀なアシスタントです"
)

app = App(
    name="study_app",
    root_agent=root_agent
)