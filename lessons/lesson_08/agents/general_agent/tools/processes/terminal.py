from typing import Any

from google.adk.tools.tool_context import ToolContext

from ...horizon.environment.registry import resolve_registry
from ...horizon.environment_context import active_environment


async def bash(
    command: str,
    timeout_s: int = 30,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """
    Workspace内でシェルコマンドを実行します。

    timeoutまでに終了しなかった場合はbackground processとして残り、
    process toolから続きを操作できます。

    Args:
        command: 実行するシェルコマンド
        timeout_s: foregroundで待つ最大秒数
    """
    env = active_environment()

    handle = await env.spawn_process(
        command,
        cwd=env.working_dir,
    )

    exit_code = await handle.wait(
        timeout=float(timeout_s)
    )

    data, _, current_exit_code = await handle.read()

    output = data.decode(
        "utf-8",
        errors="replace",
    )

    if exit_code is not None:
        return {
            "stdout": output,
            "exit_code": current_exit_code,
            "timed_out": False,
        }

    # LHAと同じ考え方：
    # timeoutしたprocessは殺さずregistryへ登録する
    resolve_registry(tool_context).register(handle)

    return {
        "session_id": handle.session_id,
        "pid": handle.pid,
        "status": "running",
        "timed_out": True,
        "partial_output": output,
        "command": command,
    }