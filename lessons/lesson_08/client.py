"""Lesson 8 end-to-end client for `adk api_server lessons/lesson_08/agents`."""

import base64
import json
import time
from pathlib import Path
from urllib.parse import quote

import httpx

BASE_URL = "http://127.0.0.1:8000"
APP = "general_agent"
USER_ID = "user_001"

HERE = Path(__file__).parent
IMAGE = HERE / "sample.png"
OUTPUT_DIR = HERE / "client_output"

client = httpx.Client(base_url=BASE_URL, timeout=300.0)


def session_path(session_id: str) -> str:
    return f"/apps/{APP}/users/{USER_ID}/sessions/{session_id}"


def create_session(session_id: str) -> None:
    r = client.post(
        f"/apps/{APP}/users/{USER_ID}/sessions",
        json={"sessionId": session_id},
    )
    r.raise_for_status()
    print(f"[client] session created: {session_id}")


def image_part(path: Path) -> dict:
    return {
        "inlineData": {
            "mimeType": "image/png",
            "displayName": path.name,
            "data": base64.b64encode(path.read_bytes()).decode(),
        }
    }


def run(
    session_id: str,
    text: str,
    attachment: dict | None = None,
) -> dict[str, int]:
    """Send one message via /run_sse and return the artifact version"""
    parts = [{"text": text}]
    if attachment is not None:
        parts.append(attachment)

    print(f"\n[client] {session_id} <- {text}")

    artifact_delta = {}

    with client.stream(
        "POST",
        "/run_sse",
        json={
            "appName": APP,
            "userId": USER_ID,
            "sessionId": session_id,
            "newMessage": {"role": "user", "parts": parts},
        },
    ) as r:
        r.raise_for_status()

        for line in r.iter_lines():
            if not line.startswith("data:"):
                continue

            event = json.loads(line.removeprefix("data:"))

            if "error" in event:
                print(f"  [error] {event['error']}")
                continue

            for part in (event.get("content") or {}).get("parts", []):
                if "functionCall" in part:
                    call = part["functionCall"]
                    args = json.dumps(call.get("args"), ensure_ascii=False)
                    print(f"  [tool call] {call['name']} {args}")
                elif "functionResponse" in part:
                    print(f"  [tool result] {part['functionResponse']['name']}")
                elif part.get("text") and not part.get("thought"):
                    print(f"  [{event['author']}] {part['text']}")

            delta = (event.get("actions") or {}).get("artifactDelta")
            if delta:
                artifact_delta.update(delta)

    print(f"  [artifact delta] {artifact_delta}")
    return artifact_delta


def download_outputs(session_id: str, artifact_delta: dict[str, int]) -> None:
    for name, version in sorted(artifact_delta.items()):
        # 入力Artifactは取り出さない
        if not name.startswith("output/"):
            continue

        r = client.get(
            f"{session_path(session_id)}/artifacts/"
            f"{quote(name, safe='')}/versions/{version}"
        )
        r.raise_for_status()

        data = base64.b64decode(r.json()["inlineData"]["data"])

        target = OUTPUT_DIR / session_id / name.removeprefix("output/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

        print(f"  [download] {name} v{version} -> {target}")


def main() -> None:
    # Session は残り続けるので、実行ごとに新しい ID を使う
    suffix = time.strftime("%H%M%S")
    session_a = f"e2e_a_{suffix}"
    session_b = f"e2e_b_{suffix}"

    create_session(session_a)
    create_session(session_b)

    # A-1: attachment -> input/ -> Agent -> output/ -> Artifact -> client
    delta = run(
        session_a,
        "私の名前は山村です。添付画像の内容を京都弁で説明して、"
        "output/summary.md に保存して。",
        attachment=image_part(IMAGE),
    )
    download_outputs(session_a, delta)

    # A-2: Skill script が既存の output を更新する
    delta = run(session_a, "京都弁で別れの挨拶をして。")
    download_outputs(session_a, delta)

    # B: 会話履歴と Workspace が A と分離されている
    run(
        session_b,
        "私の名前を知ってる？あと input/ と output/ に何があるか bash の ls で確認して。",
    )

    for session_id in (session_a, session_b):
        r = client.get(f"{session_path(session_id)}/artifacts")
        r.raise_for_status()
        print(f"\n[client] artifacts in {session_id}: {r.json()}")


if __name__ == "__main__":
    main()