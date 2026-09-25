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
    session_service=session_service
)

async def main():
    # sessionを作る
    session = await session_service.create_session(
        app_name=app.name,
        user_id=USER_ID,
        session_id=SESSION_ID
    )

    print("=== BEFORE RUN ===")
    print("Events:", len(session.events))

    # messageの作成
    message = types.Content(
        role="user",
        parts=[
            types.Part(text="今繋がっているプリンターって何がある？")
        ]
    )

    # Runnerで実行
    print("\n=== RUNNING ===")

    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=SESSION_ID,
        new_message=message
    ):
        print("Event author:", event.author)
        print("Final:", event.is_final_response())

        if event.content:
            print("Content:", event.content)


    # second_message = types.Content(
    #     role="user",
    #     parts=[
    #         types.Part(text="What did I ask you just before?")
    #     ],
    # )

    # print("\n=== SECOND RUN ===")

    # async for event in runner.run_async(
    #     user_id=USER_ID,
    #     session_id=SESSION_ID,
    #     new_message=second_message,
    # ):
    #     if event.is_final_response() and event.content:
    #         print("Response:", event.content)
    #         print("---")


    # 実行後のセッションを取り出す
    updated_session = await session_service.get_session(
        app_name=app.name,
        user_id=USER_ID,
        session_id=SESSION_ID,
    )

    print("\n=== AFTER SECOND RUN ===")
    print("Events:", len(updated_session.events))

    for i, event in enumerate(updated_session.events):
        print(f"\n--- Session Event {i} ---")
        print("Author:", event.author)
        print("Content:", event.content)


if __name__ == "__main__":
    asyncio.run(main())