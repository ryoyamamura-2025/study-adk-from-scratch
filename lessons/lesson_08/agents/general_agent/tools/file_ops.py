import mimetypes
from pathlib import Path

from google.genai import types

from ..horizon.environment_context import active_environment

# Strands harness の read と同じく拡張子で判定。画像とPDFだけ
_MEDIA_MIME_TYPES = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/gif",
        "application/pdf",
    }
)


def _resolve_path(path: str) -> Path:
    env = active_environment()

    target = Path(path)

    if target.is_absolute():
        return target

    return env.working_dir / target


async def read(path: str, offset: int = 1, limit: int = 500) -> dict:
    """
    Workspace内のファイルを読み込みます。
    テキストは行番号付きで返し、長いファイルは offset と limit で分割して読みます。
    画像（PNG/JPEG/WebP/GIF）とPDFは、そのまま見られる形で返します。

    Args:
        path: 読み込むファイルのパス
        offset: 読み始める行番号（1始まり、テキストのみ）
        limit: 読み込む最大行数（テキストのみ）
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

    mime_type, _ = mimetypes.guess_type(path)

    if mime_type in _MEDIA_MIME_TYPES:
        # Part を戻り値に入れると、ADK が FunctionResponse.parts に移す
        return {
            "success": True,
            "path": str(target),
            "mime_type": mime_type,
            "size_bytes": len(data),
            "media": types.Part.from_bytes(
                data=data,
                mime_type=mime_type,
            ),
        }

    lines =data.decode("utf-8", errors="replace").splitlines()
    total = len(lines)

    start = max(offset, 1) - 1
    window = lines[start:start + max(limit, 0)]

    numbered = "\n".join(
        f"{start + i + 1}: {line}"
        for i, line in enumerate(window)
    )

    last = start + len(window)

    # LHA の _format_numbered_lines と同じ案内文
    if last >= total:
        trailer = f"End of file - total {total} lines."
    else:
        trailer = (
            f"Showing lines {start + 1}-{last} of {total}. "
            f"Use offset={last + 1} to continue."
        )

    return {
        "success": True,
        "path": str(target),
        "content": f"{numbered}\n\n{trailer}",
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

async def edit(path: str, old_text: str, new_text: str) -> dict:
    """
    Workspace内のテキストファイルの一部を置き換えます。
    old_text はファイル内でちょうど1回だけ出現する必要があります。
    read が付ける行番号（"12: "）は old_text に含めないでください。

    Args:
        path: 編集するファイルのパス
        old_text: 置き換え前の文字列。一意になるよう前後の行も含める
        new_text: 置き換え後の文字列
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

    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError:
        return {
            "success": False,
            "error": f"Not a UTF-8 text file: {path}",
        }

    count = content.count(old_text)

    if count == 0:
        return {
            "success": False,
            "error": "old_text not found. Read the file again and copy the exact text.",
        }

    if count > 1:
        return {
            "success": False,
            "error": (
                f"old_text matched {count} times. "
                "Include more surrounding lines to make it unique."
            ),
        }

    await env.write_file(
        target,
        content.replace(old_text, new_text, 1),
    )

    return {
        "success": True,
        "path": str(target),
    }