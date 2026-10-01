import asyncio
from pathlib import Path

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts import InMemoryArtifactService
from google.genai import types

from agent import app

USER_ID = "user_001"
SESSION_ID = "session_001"

# Runnerに接続するサービス
session_service = InMemorySessionService()
artifact_service = InMemoryArtifactService()

runner = Runner(
    app=app,
    session_service=session_service,
    artifact_service=artifact_service,
)


async def run_message(
    text: str,
    attachment=None,
) -> dict[str, int]:
    parts = [types.Part(text=text)]

    if attachment is not None:
        parts.append(attachment)

    message = types.Content(
        role="user",
        parts=parts,
    )

    artifact_versions = {}

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

        delta = getattr(
            event.actions,
            "artifact_delta",
            None,
        )
        if delta:
            artifact_versions.update(delta)

    return artifact_versions


async def export_artifacts(
    artifact_versions: dict[str, int],
):
    export_dir = Path(
        "lessons/lesson_07/host_output"
    )
    export_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    for filename, version in artifact_versions.items():
        artifact = await artifact_service.load_artifact(
            app_name=app.name,
            user_id=USER_ID,
            session_id=SESSION_ID,
            filename=filename,
            version=version,
        )

        if (
            artifact is None
            or artifact.inline_data is None
        ):
            continue

        target = export_dir / filename
        target.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        target.write_bytes(
            artifact.inline_data.data
        )

        print(
            f"[HOST EXPORT] "
            f"{filename} v{version} -> {target}"
        )


async def main():
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

    generated_artifacts = {}

    # -----------------------------
    # Turn 1: input -> output
    # -----------------------------
    print("\n=== TURN 1 ===")

    image_path = Path(
        "lessons/lesson_07/sample.jpg"
    )

    attachment = types.Part(
        inline_data=types.Blob(
            data=image_path.read_bytes(),
            mime_type="image/jpeg",
            display_name=image_path.name,
        )
    )

    versions = await run_message(
        (
            "この画像を確認して、内容の説明を"
            " output/summary.txt に保存してください。"
        ),
        attachment=attachment,
    )
    generated_artifacts.update(versions)

    # -----------------------------
    # Turn 2: existing output update
    # -----------------------------
    print("\n=== TURN 2 ===")

    versions = await run_message(
        (
            "output/summary.txt を読み、"
            "説明をもう少し詳しくしてください。"
        )
    )
    generated_artifacts.update(versions)

    # -----------------------------
    # Turn 3: no output change
    # -----------------------------
    print("\n=== TURN 3 ===")

    versions = await run_message(
        "ありがとう。ファイルは変更しないでください。"
    )
    generated_artifacts.update(versions)

    # InMemoryArtifactServiceはプロセス終了で消えるため、
    # 最後に最新Artifactをホストへ取り出す。
    await export_artifacts(
        generated_artifacts
    )


if __name__ == "__main__":
    asyncio.run(main())
