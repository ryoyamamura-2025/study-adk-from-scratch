from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from google.adk.apps import App
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.models import Gemini
# from google.adk.environment import LocalEnvironment
# from docker_environment import DockerEnvironment
# from google.adk.tools.environment import EnvironmentToolset

# LHAではSandbox用の独自ツールセットを作っているので、ADKのEnvironmentToolsetを使わない
from tools import (
    bash,
    process,
    read,
    write,
)

from google.adk.skills import load_skills_from_dir
from google.adk.tools.skill_toolset import SkillToolset

from callback import before_agent, before_model, after_agent

from google.genai import types

# # -----------------------------
# # Environment
# # -----------------------------
# # environment = LocalEnvironment()
# environment = DockerEnvironment()
# environment_toolset = EnvironmentToolset(
#     environment=environment
# )

skills_dir = Path(__file__).parent / "skills"
skills = load_skills_from_dir(skills_dir)

# list_skillのツールを除外 --> Skillのプロンプトがシステム指示に入る
skill_toolset = SkillToolset(
    skills=skills,
    tool_filter=[
        "load_skill",
        "load_skill_resource",
    ],
)

root_agent = LlmAgent(
    name="study_agent",
    model=Gemini(model="gemini-3.5-flash"),
    # model=LiteLlm(
    #     model="vertex_ai/meta/llama-4-scout-17b-16e-instruct-maas"
    # ),
    # generate_content_config=types.GenerateContentConfig(
    #     max_output_tokens=256,
    # ),
    instruction="あなたは優秀なアシスタントです",
    tools=[
        # environment_toolset
        read,
        write,
        bash,
        process,
        skill_toolset
    ],
    before_agent_callback=before_agent,
    after_agent_callback=after_agent,
    before_model_callback=before_model
)

app = App(
    name="study_app",
    root_agent=root_agent
)