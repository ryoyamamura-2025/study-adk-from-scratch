import atexit
import mimetypes
from docker_sandbox_provider import DockerSandboxProvider

from google.genai import types

from horizon.environment_context import (
    clear_active_environment,
    set_active_environment,
    active_environment
)

provider = DockerSandboxProvider()

_environment_cache = {}

async def _ensure_environment(
    user_id: str,
    session_id: str,
):
    key = (user_id, session_id)

    environment = _environment_cache.get(key)

    if environment is not None:
        print(
            f"[environment] cache hit: "
            f"{user_id}/{session_id}"
        )
        return environment

    print(
        f"[environment] cache miss: "
        f"{user_id}/{session_id}"
    )

    environment, _ = provider.build_environment(
        user_id,
        session_id,
    )

    await environment.initialize()

    _environment_cache[key] = environment

    return environment

async def before_agent(callback_context):
    print("\n[CALLBACK] before_agent")
    session = callback_context.session

    user_id = session.user_id
    session_id = session.id
    print("  user_id:", user_id)
    print("  session_id:", session_id)

    environment = await _ensure_environment(
        user_id,
        session_id,
    )

    set_active_environment(environment)
    print(
        "  environment:",
        environment.sandbox_name,
    )

    return None

async def after_agent(callback_context):
    print("\n[CALLBACK] after_agent")

    environment = active_environment()
    output_dir = environment.working_dir / "output"

    try:
        entries, truncated = await environment.list_directory(
            output_dir,
            limit=100,
        )
    except FileNotFoundError:
        print("  output directory not found")
        entries = []

    print("  output entries:", entries)

    for entry in entries:
        if entry["kind"] != "file":
            continue

        filename = entry["name"]
        path = output_dir / filename

        data = await environment.read_file(path)

        mime_type, _ = mimetypes.guess_type(filename)
        if mime_type is None:
            mime_type = "application/octet-stream"

        artifact = types.Part.from_bytes(
            data=data,
            mime_type=mime_type,
        )

        version = await callback_context.save_artifact(
            filename=filename,
            artifact=artifact,
        )

        print(
            f"  saved artifact: "
            f"{filename} version={version}"
        )

    clear_active_environment()

    return None

def _close_cached_environments():
    print("\n[environment] process cleanup")

    for key, environment in _environment_cache.items():
        print(
            f"  close: {key} "
            f"-> {environment.sandbox_name}"
        )

        close_sync = getattr(
            environment,
            "close_sync",
            None,
        )

        if close_sync is not None:
            close_sync()

    _environment_cache.clear()


atexit.register(_close_cached_environments)

# Tool output pruning のための処理
PRUNE_MARKER = "[output pruned to reclaim context]"

def prune_old_tool_outputs(llm_request):
    contents = llm_request.contents

    # 最新の本物のUserインプットを探す
    latest_user_index = None

    for i in range(len(contents) - 1, -1, -1):
        content = contents[i]

        # Userのインプット以外は飛ばす
        if content.role != "user":
            continue

        parts = content.parts or []

        has_text = any(part.text for part in parts)
        has_function = any(
            part.function_call or part.function_response
            for part in parts
        )

        # 関数実行を含まずテキストを持つのが最後のUserメッセージ
        if has_text and not has_function:
            latest_user_index = i
            break

    if latest_user_index is None:
        return

    # 最新ユーザー発話より前 = 過去Turnだけを見る
    for content in contents[:latest_user_index]:
        for part in content.parts or []:
            fr = part.function_response

            if fr is None:
                continue

            size = len(str(fr.response))

            if size < 1000:
                continue

            print(
                f"[PRUNE] {fr.name}: "
                f"{size} chars -> marker"
            )

            fr.response = {
                "pruned": PRUNE_MARKER,
            }
    

async def before_model(callback_context, llm_request):
    # 過去の長いTool OutputのPrune
    # prune_old_tool_outputs(llm_request)

    print("\n[CALLBACK] before_model")

    # print("\n--- system_instruction ---")
    # print(llm_request.config.system_instruction)

    # print("\n--- contents ---")
    # print("count:", len(llm_request.contents))

    for i, content in enumerate(llm_request.contents):
        print(f"[{i}] role={content.role}")

        for part in content.parts or []:
            if part.text:
                print("  text:", part.text)

            if part.function_call:
                print("  function_call:", part.function_call)

            if part.function_response:
                print("  function_response:", part.function_response)

    # print("\n--- tools ---")
    # tools = llm_request.config.tools or []
    # print("count:", len(tools))

    # for tool in tools:
    #     for declaration in tool.function_declarations or []:
    #         print(" ", declaration.name)

    return None