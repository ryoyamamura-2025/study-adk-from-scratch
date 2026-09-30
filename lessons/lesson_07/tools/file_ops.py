from pathlib import Path

from horizon.environment_context import active_environment


def _resolve_path(path: str) -> Path:
    env = active_environment()

    target = Path(path)

    if target.is_absolute():
        return target

    return env.working_dir / target


async def read(path: str) -> dict:
    """
    Workspace内のテキストファイルを読み込みます。

    Args:
        path: 読み込むファイルのパス
    """
    env = active_environment()
    target = _resolve_path(path)

    try:
        data = await env.read_file(target)
    except FileNotFoundError:
        return {
            "success": False,
            "error": f"File not found: {path}",
        }

    return {
        "success": True,
        "path": str(target),
        "content": data.decode("utf-8", errors="replace"),
    }


async def write(path: str, content: str) -> dict:
    """
    Workspace内のテキストファイルを書き込みます。

    Args:
        path: 書き込むファイルのパス
        content: 書き込む内容
    """
    env = active_environment()
    target = _resolve_path(path)

    await env.write_file(target, content)

    return {
        "success": True,
        "path": str(target),
    }