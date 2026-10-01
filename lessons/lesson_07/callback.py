import asyncio
import atexit
import mimetypes
import shlex
import time
from pathlib import Path

from docker_sandbox_provider import DockerSandboxProvider

from google.genai import types

from horizon.environment_context import (
    clear_active_environment,
    set_active_environment,
    active_environment,
)

provider = DockerSandboxProvider()

_environment_cache = {}
_output_watchers = {}


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


async def _wait_for_watcher_ready(
    watcher,
    timeout: float = 5.0,
) -> int:
    """Wait until inotifywait has finished installing its watches."""
    offset = 0
    text = ""
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        data, offset, exit_code = await watcher.read(
            offset=offset,
        )

        if data:
            text += data.decode(
                "utf-8",
                errors="replace",
            )

        if "Watches established." in text:
            return offset

        if exit_code is not None:
            raise RuntimeError(
                "output watcher exited before becoming ready:\n"
                f"{text.strip()}"
            )

        await asyncio.sleep(0.05)

    await watcher.kill()
    raise TimeoutError(
        "output watcher did not become ready"
    )


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

    output_dir = environment.working_dir / "output"
    await environment.make_dir(output_dir)

    watcher = await environment.spawn_process(
        (
            "exec inotifywait -m -r "
            "-e close_write "
            "-e moved_to "
            "--format '%w%f' "
            f"{shlex.quote(str(output_dir))}"
        )
    )

    event_offset = await _wait_for_watcher_ready(
        watcher
    )

    _output_watchers[
        callback_context.invocation_id
    ] = (watcher, event_offset)

    print("  output watcher: ready")

    return None


async def after_agent(callback_context):
    print("\n[CALLBACK] after_agent")

    environment = active_environment()
    output_dir = environment.working_dir / "output"

    watcher_info = _output_watchers.pop(
        callback_context.invocation_id,
        None,
    )

    try:
        if watcher_info is None:
            print("  output watcher: not found")
            return None

        watcher, event_offset = watcher_info

        # Stop the watcher first so all pending output is flushed.
        await watcher.kill()

        raw, _, _ = await watcher.read(
            offset=event_offset,
        )

        changed_paths = {
            line.strip()
            for line in raw.decode(
                "utf-8",
                errors="replace",
            ).splitlines()
            if line.strip()
        }

        print(
            "  changed outputs:",
            sorted(changed_paths),
        )

        for raw_path in sorted(changed_paths):
            path = Path(raw_path)

            try:
                relative = path.relative_to(
                    output_dir
                )
            except ValueError:
                continue

            if not relative.parts:
                continue

            try:
                data = await environment.read_file(path)
            except (
                FileNotFoundError,
                IsADirectoryError,
            ):
                continue

            filename = relative.as_posix()

            mime_type, _ = mimetypes.guess_type(
                filename
            )
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

        return None

    finally:
        clear_active_environment()


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

    return None
