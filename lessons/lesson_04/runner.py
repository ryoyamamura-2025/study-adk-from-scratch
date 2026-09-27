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
    # Sandbox
    # -----------------------------
    provider = DockerSandboxProvider()

    environment, _ = (
        provider.build_environment(USER_ID)
    )

    await environment.initialize()

    print("=== ENVIRONMENT ===")
    print(
        "Type:",
        type(environment).__name__,
    )
    print(
        "Working dir:",
        environment.working_dir,
    )

    # Lesson4では固定Sandbox。
    # Callbackによる動的bindは後のLesson。
    set_active_environment(environment)

    try:
        # -----------------------------
        # ADK Session
        # -----------------------------
        await session_service.create_session(
            app_name=app.name,
            user_id=USER_ID,
            session_id=SESSION_ID,
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
            "workspaceにhello.txtを作成し、"
            "内容を「hello from sandbox」にしてください。"
            "そのあとreadで読み込んで確認してください。"
        )

        # -----------------------------
        # Turn 2
        # -----------------------------
        print("\n=== TURN 2 ===")

        await run_message(
            "bashでpwdとls -laを実行して、"
            "実行場所とファイル一覧を確認してください。"
        )

        # -----------------------------
        # Turn 3
        # -----------------------------
        print("\n=== TURN 3 ===")

        await run_message(
            "processのspawnを使って"
            "「python -u -c "
            "\"import time; "
            "print('start', flush=True); "
            "time.sleep(10); "
            "print('done', flush=True)\"」"
            "をバックグラウンド実行してください。"
            "起動できたら終了を待たずに答えてください。"
        )

        # -----------------------------
        # Turn 4
        # -----------------------------
        print("\n=== TURN 4 ===")

        await run_message(
            "さっき起動したbackground processを"
            "processのlistで探して、"
            "まだ動いていればpollしてください。"
        )

    finally:
        clear_active_environment()
        await environment.close()


if __name__ == "__main__":
    asyncio.run(main())