import asyncio

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts import InMemoryArtifactService
from google.genai import types

# from agent import app, environment, environment_toolset
from agent import app

from horizon.environment_context import (
    clear_active_environment,
    set_active_environment,
)

from docker_sandbox_provider import DockerSandboxProvider

USER_ID = "user_001"
SESSION_ID = "session_001"

# Runnerに接続するサービス
session_service = InMemorySessionService()
artifact_service = InMemoryArtifactService()

runner = Runner(
    app=app,
    session_service=session_service,
    artifact_service=artifact_service
)

# 確認用
# print(type(runner.session_service).__name__)
# print(type(runner.artifact_service).__name__)

async def run_message(text: str):
    message = types.Content(
        role="user",
        parts=[
            types.Part(text=text),
        ],
    )

    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=SESSION_ID,
        new_message=message,
    ):

        print("Event author:", event.author)
        print(
            "Final:",
            event.is_final_response(),
        )

        if event.content:
            print(
                "Content:",
                event.content,
            )


async def main():
    # -----------------------------
    # ADK Session
    # -----------------------------
    await session_service.create_session(
        app_name=app.name,
        user_id=USER_ID,
        session_id=SESSION_ID,
        state={
            "project_name": "study-adk-from-scratch",
        },
    )

    print("\n=== ROOT AGENT TOOLS ===")

    for tool in app.root_agent.tools:
        name = getattr(
            tool,
            "name",
            getattr(
                tool,
                "__name__",
                type(tool).__name__,
            ),
        )
        print(f"- {name}")

    # -----------------------------
    # Turn 1
    # -----------------------------
    print("\n=== TURN 1 ===")

    await run_message(
        "output/report.txt を作成して、内容を「Lesson7 artifact test」にしてください。"
    )
    

if __name__ == "__main__":
    asyncio.run(main())