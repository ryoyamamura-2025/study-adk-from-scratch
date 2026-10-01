import atexit
import mimetypes
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
_output_snapshots = {}


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


async def _snapshot_output(
    environment,
    output_dir: Path,
) -> dict[str, tuple[int, int]]:
    """Collect lightweight metadata for files under output/."""
    snapshot = {}

    async def walk(directory: Path):
        entries, truncated = await environment.list_directory(
            directory,
            limit=10_000,
        )

        if truncated:
            raise RuntimeError(
                f"too many entries in one directory: {directory}"
            )

        for entry in entries:
            path = directory / entry["name"]

            if entry["kind"] == "dir":
                await walk(path)
                continue

            if entry["kind"] != "file":
                continue

            relative = path.relative_to(
                output_dir
            ).as_posix()

            snapshot[relative] = (
                int(entry["size"]),
                int(entry["mtime"]),
            )

    try:
        await walk(output_dir)
    except FileNotFoundError:
        return {}

    return snapshot


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

    snapshot = await _snapshot_output(
        environment,
        output_dir,
    )

    _output_snapshots[
        callback_context.invocation_id
    ] = snapshot

    print(
        "  output snapshot:",
        f"{len(snapshot)} files",
    )

    return None


async def after_agent(callback_context):
    print("\n[CALLBACK] after_agent")

    environment = active_environment()
    output_dir = environment.working_dir / "output"

    before = _output_snapshots.pop(
        callback_context.invocation_id,
        {},
    )

    try:
        after = await _snapshot_output(
            environment,
            output_dir,
        )

        changed = sorted(
            filename
            for filename, metadata in after.items()
            if before.get(filename) != metadata
        )

        deleted = sorted(
            set(before) - set(after)
        )

        print(
            "  changed outputs:",
            changed,
        )

        if deleted:
            print(
                "  deleted outputs:",
                deleted,
            )

        for filename in changed:
            path = output_dir / filename

            data = await environment.read_file(path)

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
