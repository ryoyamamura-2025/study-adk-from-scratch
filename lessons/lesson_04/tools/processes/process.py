from typing import Any, Literal

from google.adk.tools.tool_context import ToolContext

from horizon.environment.registry import resolve_registry
from horizon.environment_context import active_environment


def _decode(data: bytes) -> str:
    return data.decode(
        "utf-8",
        errors="replace",
    )


def _summary(handle) -> dict[str, Any]:
    return {
        "session_id": handle.session_id,
        "pid": handle.pid,
        "command": handle.command,
        "status": (
            "running"
            if handle.is_running
            else "exited"
        ),
        "exit_code": handle.exit_code,
    }


async def process(
    action: Literal[
        "spawn",
        "list",
        "poll",
        "log",
        "wait",
        "kill",
        "write",
    ],
    session_id: str | None = None,
    command: str | None = None,
    timeout_s: float | None = None,
    data: str | None = None,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """
    Background processを起動・確認・操作します。

    Args:
        action:
            spawn / list / poll / log /
            wait / kill / write
        session_id:
            操作対象processのsession id
        command:
            spawn時に実行するコマンド
        timeout_s:
            wait時の最大待機秒数
        data:
            write時にstdinへ送る文字列
    """
    registry = resolve_registry(tool_context)

    if action == "list":
        return {
            "running": [
                _summary(handle)
                for handle in registry.list_running()
            ],
            "finished": [
                _summary(handle)
                for handle in registry.list_finished()
            ],
        }

    if action == "spawn":
        if not command:
            return {
                "error": "spawn requires command"
            }

        env = active_environment()

        handle = await env.spawn_process(
            command,
            cwd=env.working_dir,
        )

        registry.register(handle)

        return {
            "session_id": handle.session_id,
            "pid": handle.pid,
            "status": "running",
            "command": command,
        }

    if not session_id:
        return {
            "error": f"{action} requires session_id"
        }

    handle = registry.get(session_id)

    if handle is None:
        return {
            "error": f"no such session: {session_id}"
        }

    if action == "poll":
        chunk, _, exit_code = await handle.read()

        return {
            "session_id": session_id,
            "status": (
                "running"
                if handle.is_running
                else "exited"
            ),
            "exit_code": exit_code,
            "output": _decode(chunk),
        }

    if action == "log":
        chunk, next_offset, exit_code = await handle.read()

        return {
            "session_id": session_id,
            "data": _decode(chunk),
            "next_offset": next_offset,
            "exit_code": exit_code,
        }

    if action == "wait":
        exit_code = await handle.wait(
            timeout=timeout_s
        )

        return {
            "session_id": session_id,
            "status": (
                "running"
                if handle.is_running
                else "exited"
            ),
            "exit_code": exit_code,
            "timed_out": handle.is_running,
        }

    if action == "kill":
        await handle.kill()

        return {
            "session_id": session_id,
            "status": "killed",
        }

    if action == "write":
        if data is None:
            return {
                "error": "write requires data"
            }

        payload = data.encode("utf-8")

        if not payload.endswith(b"\n"):
            payload += b"\n"

        await handle.write(payload)

        return {
            "session_id": session_id,
            "status": "written",
            "bytes": len(payload),
        }

    return {
        "error": f"unknown action: {action}"
    }