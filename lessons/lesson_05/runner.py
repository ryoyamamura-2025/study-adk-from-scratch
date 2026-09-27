import asyncio

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agent import app


USER_ID = "user_001"
SESSION_ID = "session_001"

session_service = InMemorySessionService()

runner = Runner(
    app=app,
    session_service=session_service,
)


async def main():
    await session_service.create_session(
        app_name=app.name,
        user_id=USER_ID,
        session_id=SESSION_ID,
        state={
            "lesson": 5,
            "purpose": "callback observation",
        },
    )

    message = types.Content(
        role="user",
        parts=[
            types.Part(text="callback test"),
        ],
    )

    print("=== RUNNING ===")

    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=SESSION_ID,
        new_message=message,
    ):
        print("\n[EVENT]")
        print("  author:", event.author)
        print("  final:", event.is_final_response())

        if event.content:
            part_types = []

            for part in event.content.parts or []:
                if part.function_call:
                    part_types.append("function_call")
                elif part.function_response:
                    part_types.append("function_response")
                elif part.text:
                    part_types.append("text")
                else:
                    part_types.append("other")

            print("  part_types:", part_types)
            print("  content:", event.content)


if __name__ == "__main__":
    asyncio.run(main())
