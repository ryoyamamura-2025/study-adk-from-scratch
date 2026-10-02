# Lesson 8 — ADK API Server / Final Integration

## Lesson 8 の目的

Lesson 8 では、Lesson 0〜7 で作ってきた Agent を ADK 標準の API server に載せ、外部 client から HTTP で利用できる Agent backend として成立させた。

中心となる考え方は、**自前の FastAPI routing を書かず、ADK 標準の serving boundary をそのまま使う**ことである。

Lesson 7 までは `runner.py` が Runner を直接呼んでいた。Lesson 8 ではその役割が次のように分かれた。

```text
Lesson 7
runner.py
  ├─ Session 作成
  ├─ runner.run_async()
  └─ Artifact を host_output/ へ export

Lesson 8
Client（curl / client.py）
  │  HTTP / SSE
  ▼
ADK API Server（adk api_server）
  ├─ SessionService   … .adk/session.db
  ├─ ArtifactService  … .adk/artifacts/
  └─ Runner
        │
        ▼
App（general_agent）
  ├─ WorkspaceIOPlugin
  ├─ Agent callbacks（Sandbox lifecycle / Skill copy / output snapshot）
  └─ Agent
        ├─ read / write / edit / bash / process
        └─ HorizonSkillToolset（load_skill）
              │
              ▼
        Sandbox / Workspace
        ├─ input/
        ├─ work/
        ├─ output/
        └─ skills/
```

最終的なディレクトリ構成は次の通り。

```text
lessons/lesson_08/
├─ LESSON_08.md
├─ LESSON_08_PLAN.md
├─ client.py          # runner.py を置き換える HTTP client
├─ sample.png
└─ agents/            # adk api_server に渡す agents_dir
   └─ general_agent/
      ├─ __init__.py
      ├─ agent.py
      ├─ system_prompt.py
      ├─ callback.py / plugin.py
      ├─ docker_sandbox_provider.py
      ├─ skills/kyoto-ben-master/{SKILL.md, scripts/merge_words.py}
      ├─ tools/{file_ops.py, processes/}
      └─ horizon/     # LHA 由来の実装（原本に近いまま保つ）
         ├─ environment/ / environment_context.py / sandbox/
         └─ tools/skill_toolset.py
```

---

## 1. API server に載せるには package にする必要がある

まず Lesson 7 のコードを `general_agent/` にほぼそのままコピーし、

```bash
uv run adk api_server lessons/lesson_08/agents
```

で起動した。

最初のエラーは次の通り。

```text
ModuleNotFoundError: Fail to load 'general_agent.agent' module. No module named 'tools'
```

原因は、ADK の AgentLoader が `sys.path` に追加するのが `agents_dir`（`lessons/lesson_08/agents`）だけだったことである。

```text
Lesson 7
cd lessons/lesson_07 && python runner.py
→ カレントディレクトリが sys.path の先頭
→ import tools が解決できた

Lesson 8
general_agent は package として import される
→ tools はトップレベルに存在しない
→ general_agent.tools として参照する必要がある
```

そのため、

- `general_agent/__init__.py` に `from . import agent` を置く
- `from tools import ...` / `from horizon.xxx import ...` を相対 import に直す

という変更を入れた。

関数内の遅延 import（`horizon/environment/sandbox.py` の `from .sandbox_process import ...`）も直す必要があった。これは `process` Tool を初めて使うときにだけ実行されるため、起動時には気づけない。

一方、`horizon/sandbox/runtime/server.py` は Docker コンテナ内で動くコードであり、ホスト側の Python からは import されないので変更していない。

---

## 2. Agent は request 時に遅延ロードされる

起動直後に Session を作っても、上のエラーは出なかった。

```text
POST /apps/general_agent/users/u1/sessions
→ 成功
```

Session 作成は SessionService だけを使い、Agent を import しないためである。

Agent の import が走るのは、Runner が必要になったとき（`/run` / `/run_sse` / `/apps/{app}/app-info` など）である。

```text
API server 起動
  ↓
Session 作成      … Agent はまだロードされない
  ↓
app-info / run    … ここで agent_loader.load_agent()
```

import エラーの確認には `GET /apps/{app_name}/app-info` が便利だった。

---

## 3. App 名はディレクトリ名で決まる

API server は Runner を作るとき、URL の app 名（= ディレクトリ名）を `app_name` として明示的に渡している。

```python
# google/adk/cli/api_server.py
Runner(
    app=agentic_app,
    app_name=app_name,  # URL のディレクトリ名
    ...
)
```

そのため `App(name="study_app")` のままでも Session の検索は動く。

ただし App 名と実際の app 名がずれていると、ログや Artifact の保存先を読むときに混乱するので、

```python
app = App(
    name="general_agent",
    ...
)
```

とディレクトリ名に揃えた。

---

## 4. 公開されている API

Swagger UI（`/docs`）の元データである `/openapi.json` から、method と path だけを抜き出して確認した。

```text
Session
POST   /apps/{app}/users/{user}/sessions
POST   /apps/{app}/users/{user}/sessions/{session_id}
GET    /apps/{app}/users/{user}/sessions
GET    /apps/{app}/users/{user}/sessions/{session_id}
PATCH  /apps/{app}/users/{user}/sessions/{session_id}
DELETE /apps/{app}/users/{user}/sessions/{session_id}

Run
POST   /run       … 実行完了まで待ち、Event のリストを返す
POST   /run_sse   … Event を SSE で1つずつ流す

Artifact
GET    .../sessions/{session_id}/artifacts
GET    .../artifacts/{artifact_name}
GET    .../artifacts/{artifact_name}/versions
GET    .../artifacts/{artifact_name}/versions/{version_id}
POST   .../sessions/{session_id}/artifacts
DELETE .../artifacts/{artifact_name}
```

URL の階層 `app → user → session → artifact` は、Lesson 3 で学んだ Artifact の scope そのものである。

`/run` の body（`RunAgentRequest`）は、Lesson 7 の `runner.run_async()` とほぼ1対1で対応する。

```text
runner.run_async(          POST /run
  user_id=...,       →       "userId": ...
  session_id=...,    →       "sessionId": ...
  new_message=...,   →       "newMessage": {"role": "user", "parts": [...]}
)                            "appName": ...   ← 1 server に複数 App を載せられるため
```

フィールド名は camelCase でも snake_case でも受け付ける（`populate_by_name=True`）。

---

## 5. Session は client が作り、SQLite に残る

`auto_create_session` の既定値は False なので、client が事前に Session を作る。

```bash
curl -X POST http://127.0.0.1:8000/apps/general_agent/users/user_001/sessions \
  -H "Content-Type: application/json" \
  -d '{"sessionId": "session_a"}'
```

確認できたことは次の通り。

- Session 一覧は user 単位で返る。`user_id=u1` で作った Session は `user_001` の一覧に出ない。
- 保存先は `general_agent/.adk/session.db`（SQLite）。Lesson 7 の `InMemorySessionService` と違い、server を再起動しても Session が残る。
- `session_a` で名前を教えると、`session_b` では知らないと答える。会話履歴は Session ごとに分離される。
- `session_a` / `session_b` で別々のコンテナが作られる。Lesson 5 の 1 Session = 1 Sandbox が API 経由でもそのまま機能する。

`user_id` / `session_id` は Docker のコンテナ名に入るため、英数字と `_` だけにした。

---

## 6. `/run` と `/run_sse`

`/run` は、その invocation で生まれた Event だけをリストで返す。User の発話 Event は含まれない。

```text
[
  {
    "author": "general_agent",
    "invocationId": "e-...",
    "content": {"role": "model", "parts": [{"text": "..."}]},
    "actions": {"artifactDelta": {}, "stateDelta": {}, ...}
  }
]
```

`/run_sse` は同じ Event を SSE の `data: {...}` として1つずつ流す。body の `streaming` で粒度が変わる。

```text
streaming: false
→ 完成した Event 単位
→ functionCall → functionResponse → text の順に届く

streaming: true
→ Model の出力をトークン断片単位で流す
→ "partial": true の Event が続き、最後に完成した Event が来る
```

curl では `-N` を付けてバッファを無効にすると、Event が届いた瞬間に表示される。

---

## 7. attachment は base64 にして送るだけ

Lesson 7 の runner では、

```python
types.Part(
    inline_data=types.Blob(
        data=image_path.read_bytes(),
        mime_type="image/png",
        display_name=image_path.name,
    )
)
```

として attachment を作っていた。

HTTP では bytes をそのまま送れないので、JSON の中で base64 文字列にする。

```json
{"inlineData": {"mimeType": "image/png", "displayName": "sample.png", "data": "<base64>"}}
```

server 側で `types.Content` に変換するときに、base64 は bytes に戻る。

その後は Lesson 7 と同じ経路を通った。

```text
Client attachment（base64）
→ ADK API Server
→ user message の inline_data
→ WorkspaceIOPlugin.on_user_message_callback
→ ArtifactService（input/sample.png）
→ before_model_callback で workspace/input/ へ materialize
→ Agent
```

**`WorkspaceIOPlugin` は1行も変更していない。**

Plugin は「誰が user message を作ったか」に依存しない設計だったので、Runner 直呼びから HTTP に変わっても、そのまま動いた。

---

## 8. Host export を Artifact API に置き換えた

Lesson 7 では Runner が `artifact_service.load_artifact()` を呼び、`host_output/` へ書き出していた。

Lesson 8 では client が Artifact API で取りに行く。

```bash
A=http://127.0.0.1:8000/apps/general_agent/users/user_001/sessions/session_a/artifacts

curl "$A"                                   # 一覧
curl "$A/output%2Fsummary.txt/versions"     # version 一覧
curl "$A/output%2Fsummary.txt"              # 最新
```

注意点は2つあった。

- Lesson 7 で Artifact 名を `input/` / `output/` で namespace 化したため、名前に `/` が含まれる。URL では `%2F` にしないと path の区切りと解釈されて 404 になる。
- 取得結果は `types.Part` の JSON なので、`inlineData.data` を base64 decode して保存する。

```text
Agent
→ output/ に成果物を書く

Agent callback（after_agent）
→ 変更された output だけ Artifact 化

Client
→ Artifact API から取得
```

Host export という学習用の処理が、外部 client の責務に置き換わった。

---

## 9. Skill を Sandbox にコピーした

Lesson 6 の Skill を Lesson 8 に持ち込むにあたり、`scripts/` を持つ実用的な Skill を `bash` で実行できるようにしたかった。

しかし、ホストの `general_agent/skills/` は Docker コンテナから見えない。

```text
load_skill
→ ADK がホスト側メモリから SKILL.md を返す
→ 動く

bash python3 skills/<name>/scripts/x.py
→ コンテナ内にファイルがない
→ 動かない
```

そこで `callback.py` の `_ensure_environment` で、Environment を新しく作ったとき（cache miss 時）に Skill ディレクトリを Sandbox の `skills/` へコピーするようにした。

```python
async def _copy_skills(environment):
    skills_root = environment.working_dir / "skills"

    for path in sorted(SKILLS_DIR.rglob("*")):
        if not path.is_file():
            continue

        relative = path.relative_to(SKILLS_DIR)

        await environment.write_file(
            skills_root / relative,
            path.read_bytes(),
        )
```

`SKILLS_DIR` を `.parent.parent` にしてしまい、何もコピーされないミスがあった。`rglob` は存在しないディレクトリでもエラーにならず空を返すため、無言で何も起きなかった。

### LHA とは向きが逆

LHA にはこの処理自体が存在しない。

```text
LHA
builtin skills
  horizon/builtin_skills/<name>/SKILL.md
  → scripts を持たない
  → ホスト側の load_skill だけで完結

user skills
  Sandbox 内の .agents/skills/<name>/
  → npx skills add や Agent 自身の write で置かれる
  → Sandbox → ホストへミラーしてカタログにする

Lesson 8
general_agent/skills/
  → ホストが正
  → ホスト → Sandbox へコピー
```

LHA は「Skill は Sandbox 側が正、ホストはミラー」という設計である。Skill の追加経路（レジストリ / Skills CLI）が Sandbox 内にあるため、こうなっている。

Lesson 8 は開発者が同梱する Skill だけを扱うので、逆向きのコピーにした。

---

## 10. Skill 前置きを LHA の方式で差し替えた

`before_model` で `llm_request.config.system_instruction` を表示すると、ADK 標準の `SkillToolset` が約2KBの前置きを追記していた。

その中には、Lesson 8 の方針と矛盾する文があった。

```text
- **scripts/** (Optional): Scripts bundled with the skill. You cannot run them; ...

Do NOT use other tools to access skill files.
```

そこで LHA の `horizon/tools/skill_toolset.py` を `general_agent/horizon/tools/` にコピーし、`HorizonSkillToolset` を使うようにした。

仕組みは、`super().process_llm_request()` が追記した**差分だけ**を書き換えることである。

```python
before = llm_request.config.system_instruction or ""
await super().process_llm_request(...)
after = llm_request.config.system_instruction or ""
delta = after[len(before):]

index_start = delta.find("<available_skills>")

llm_request.config.system_instruction = (
    before + _SHORT_SKILLS_PREAMBLE + delta[index_start:]
)
```

system instruction 全体を `<available_skills>` で split しないのは、`before` に `static_instruction` が入っているためである。全体を split すると、巻き添えで消えてしまう。

結果として前置きは次の1文になった。

```text
Skills below extend your capabilities via SKILL.md instructions you load with load_skill before following them.

<available_skills>
...
</available_skills>
```

LHA のファイルには、Lesson 8 では使わない `LoadSkillTool`（`load_skill` / `load_skill_resource` / `reload` を統合した Tool）も入っている。定義されるだけで使われず無害なので、`horizon/` は原本に近いまま残した。

---

## 11. `load_skill_resource` は外した

Skill を Sandbox にコピーした時点で、同じ補助ファイルを読む経路が2つになった。

```text
load_skill_resource
→ ホスト側メモリから返す

read skills/<name>/references/x.md
→ Sandbox 内のコピーを読む
```

LHA が `load_skill_resource` 相当を持っているのは、builtin skills が Sandbox に存在しないからである。Lesson 8 ではその理由がないため、`tool_filter=["load_skill"]` にした。

```text
SKILL.md 本文     → load_skill
補助ファイル      → read
scripts           → bash
```

`load_skill` は SKILL.md 本文の取得と Skill の有効化の役割があるため、`read` で代替せず残した。

---

## 12. System prompt を `static_instruction` に置いた

Lesson 7 の `WORKSPACE_PROTOCOL`（日本語、`instruction`）を、LHA の `horizon/conversation/system_prompt.py` を元にした英語の system prompt に置き換えた。

Lesson 8 用に取捨選択・改変するため、`horizon/` の外に `general_agent/system_prompt.py` として作った。

```python
root_agent = LlmAgent(
    ...
    static_instruction=SYSTEM_PROMPT,
    instruction="",
)
```

構成と、LHA からの変更点は次の通り。

```text
1. Identity        DEFAULT_AGENT_IDENTITY から "saved memory/" を削除
2. Skills          skills/ への Sandbox コピー前提に書き直し。自己拡張は削除
3. # Acting        "the hard guard halts at three identical failures" を削除
4. # Safety        DATA として扱う、の1文だけ
5. # Style         web_research の引用の段落を削除
6. Workspace       Lesson 7 の Workspace File Protocol をベースに書き直し
7. Execution       POSIX /bin/sh の1文だけ
8. Tool routing    read / edit の使い分け
```

Model に渡る system instruction の順序は次のようになった。

```text
static_instruction（SYSTEM_PROMPT）
↓
You are an agent. Your internal name is "general_agent".   … ADK が自動で追加
↓
Skills below extend ...                                     … HorizonSkillToolset
<available_skills> ... </available_skills>
```

`static_instruction` は毎ターン変わらない部分なので、system instruction の先頭に置かれ、context cache が効きやすい。

Lesson 7 の添付通知も `<system-reminder>` で囲っているため、Safety の「DATA として扱う」の対象になる。ただし中身は「ファイルが置かれた」という事実だけなので、矛盾しない。

---

## 13. scripts 付き Skill で Sandbox コピーを検証した

Skill を京都弁で話す `kyoto-ben-master` に差し替え、使った京都弁を JSONL に記録する script を持たせた。

```text
skills/kyoto-ben-master/
├─ SKILL.md
└─ scripts/merge_words.py
```

`SKILL.md` の手順は次の通り。

```text
1. work/new_words.jsonl に1行1語で書く
2. bash で python3 skills/kyoto-ben-master/scripts/merge_words.py work/new_words.jsonl を実行する
```

`merge_words.py` は既存の `output/kyoto_words.jsonl` と新しい語をマージして書き戻す。

「既存を更新する」処理を Model に任せず script に寄せることで、確実に同じ結果になる。`scripts/` 付き Skill の典型的な使い道である。

`write_file` では実行権限（+x）が付かないため、system prompt では `python3 ...` / `sh ...` の形で実行するように書いた。

---

## 14. `read` の offset / limit と `edit` を自作した

最後に、LHA の `file_ops.py` と比べて足りない機能を追加した。

LHA の実装は、欲しい機能に対して周辺機能が大半だった。

```text
read の offset / limit
  本質   … splitlines → スライス → 行番号
  付属物 … 50KB 超の退避、1行2000字の切り詰め、protected paths、binary 拡張子拒否

edit
  本質   … old_text が1回だけ出現するか確認して置換
  付属物 … fuzzy match（_replacers.py）、複数 edit の一括適用、ruff 診断

全体
  workspace window（focus）
```

特に workspace window は、最初に `output/summary.md` を書くと focus が `output/` になり、以降の `input/sample.png` が `output/input/sample.png` として解決される。Lesson 8 の `input/` / `output/` protocol を壊すため、持ち込まなかった。

そのため LHA のファイルはコピーせず、Lesson 4 の `tools/file_ops.py` を拡張した。

`read` は LHA の `_format_numbered_lines` と同じ形式で返す。

```text
1: ...
2: ...

Showing lines 1-500 of 1200. Use offset=501 to continue.
```

`edit` は一意一致のときだけ置換する。

```text
0 回一致   → old_text not found. Read the file again and copy the exact text.
2 回以上   → old_text matched N times. Include more surrounding lines to make it unique.
1 回だけ   → 置換して書き戻す
```

error 文に「次にどうすればよいか」を書くことで、Model の自己修正を誘導する。

`edit` は書き戻すため、`decode("utf-8", errors="replace")` にはしていない。置換文字のまま保存されてファイルが壊れるのを防ぐためである。

---

## 15. `read` の画像 / PDF は Tool result に入れて履歴に残す

function tool の戻り値は JSON の `functionResponse` になるため、そのままでは画像の bytes を Model に見せられない。

これには2つの方式があった。

```text
LHA（horizon/tools/read.py の ReadTool）
run_async
→ bytes を退避して {"success": True, ...} だけ返す
process_llm_request
→ 次の LLM 呼び出しの contents に画像 Part を追加
→ Session には保存されない
→ 画像が見えるのは直後の1回の LLM 呼び出しだけ

Strands harness（file_tools.py の read）
→ 画像 / PDF を Tool result の中に image / document block として返す
→ 普通の Tool result として履歴に残る
→ 以降の Model Call で毎回送られる
→ context が溢れたら後段の context manager が要約・削除する
```

LHA の方式は token が安いが、同じターン内でも次の LLM 呼び出しでは画像が消えている。画像を見ながら何度も作業するにはつらい。

調べると、ADK 2.9.2 でも Strands と同じことができた。

```python
# google/adk/flows/llm_flows/_tool_caller.py
def _extract_multimodal_parts(function_result, depth=0):
  """Moves media in a tool result into function response parts.
  ...
```

function tool が戻り値の dict に `types.Part` を入れて返すと、ADK がそれを抜き出して `FunctionResponse.parts`（Gemini の multimodal function response）に移す。

```python
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
```

```text
read の戻り値
{"success": True, "mime_type": "image/png", "media": Part(bytes)}
        ↓ ADK
FunctionResponse(
    response={"success": True, "mime_type": "image/png", ...},
    parts=[FunctionResponsePart(inline_data=画像)],
)
        ↓
Event として Session に保存
```

これなら `BaseTool` の継承も `process_llm_request` も不要で、今の function tool に分岐を足すだけで済んだ。

画像を `read` した次のターンで、`read` し直さずに画像の内容を答えられることを確認した。PDF も同じ方式で読めた。

判定は Strands と同じく拡張子だけで行い、対象は画像4種（PNG / JPEG / WebP / GIF）と PDF に絞った。

添付と比べると次のようになる。

```text
User attachment
→ user Event の inline_data として履歴に残る

read した media
→ function response の parts として履歴に残る

どちらも以降の Model Call で毎回送られる
```

古い media を placeholder に置き換える処理は入れていない。必要になれば、Lesson 6 の `prune_old_tool_outputs` と同じ形で `before_model` に書ける。

---

## 16. 最終 E2E scenario

`client.py` は、Lesson 7 の `runner.py` を HTTP client に置き換えたものである。

```text
runner.py                         client.py
session_service.create_session    POST .../sessions
runner.run_async の async for     POST /run_sse を1行ずつ読む
event.actions.artifact_delta      SSE の Event の actions.artifactDelta
export_artifacts（Host export）   GET .../artifacts/{name}/versions/{version}
```

scenario は次の通り。

```text
Session A / Turn 1
名前を伝える + 画像 attachment + 京都弁で説明して output/summary.md に保存
↓
input/sample.png（Artifact → workspace/input/）
↓
load_skill（kyoto-ben-master）
↓
write output/summary.md / work/new_words.jsonl
↓
bash python3 skills/kyoto-ben-master/scripts/merge_words.py
↓
output/summary.md / output/kyoto_words.jsonl → Artifact
↓
client_output/ に download

Session A / Turn 2
京都弁で別れの挨拶
↓
merge_words.py が既存の kyoto_words.jsonl を更新
↓
kyoto_words.jsonl の新しい version だけ Artifact 化

Session B
名前を知っているか / input/ と output/ の中身
↓
名前を知らない
input/ / output/ は空
Artifact 一覧も空
```

Session ID は実行ごとに時刻から作っている。Session もコンテナも残り続けるため、同じ ID を使い回すと前回の Workspace が見えてしまう。

これにより、

```text
Client
→ Session creation
→ text + attachment
→ ADK API Server
→ WorkspaceIOPlugin
→ Artifact
→ workspace/input/
→ Agent / Skill / Tool / Sandbox
→ workspace/output/
→ Artifact
→ Client
```

が一気通貫でつながり、Session ごとに会話履歴・Workspace・Artifact が分離されることを確認した。

---

## 17. Lesson 8 で分かった責務分離

最終的には次のように整理できる。

```text
Client
= Session を作る
= message と attachment を送る
= SSE で Event を受け取る
= Artifact API から成果物を取得する

ADK API Server
= external serving boundary
= SessionService / ArtifactService / Runner を接続する

SessionService
= conversation state（.adk/session.db）

ArtifactService
= external file boundary（.adk/artifacts/）

WorkspaceIOPlugin
= attachment → Artifact → workspace/input/

Agent callback / Harness
= Sandbox lifecycle（1 Session = 1 Sandbox）
= Skill の Sandbox コピー
= 変更された output だけ Artifact 化

HorizonSkillToolset
= Skill catalog の注入と前置きの差し替え

Agent
= reasoning + tool use
= Workspace 上のファイルだけを扱う
```

Lesson 7 の `runner.py` が担っていた「Session を作る」「Event を観察する」「成果物を取り出す」は、すべて Agent の外側の client に移った。

Agent 側のコードは、API server に載せるための import の修正以外、Lesson 7 から構造を変えていない。

---

## 18. 現時点の制約・割り切り

Lesson 8 の最終実装では次を割り切っている。

- 同じ Session に並行してリクエストを送らない。Sandbox の作成が競合する。
- `user_id` / `session_id` は英数字と `_` だけ。Docker のコンテナ名に使われる。
- コンテナが停止すると次のリクエストで作り直しになり、Workspace は消える。
- コンテナが途中で消えても検知しないため、server を再起動するまで回復しない。
- Session を削除してもコンテナは残る。手動で `docker rm` する。
- Skill の更新は server 再起動まで反映されない。
- `read` した画像 / PDF は履歴に残り、以降の Model Call で毎回送られる。間引きは未実装。
- media の bytes は `.adk/session.db` に保存されるため、大きい画像を何度も `read` すると DB が大きくなる。
- authentication / authorization、frontend、production deployment、durable ArtifactService は扱わない。

これらは今回の目的である「ADK 標準の serving boundary で全体がつながること」の確認とは別の運用課題として残した。

---

## 参照

### Google ADK

- `api_server.py`（`RunAgentRequest` / `/run` / `/run_sse` / Runner 作成）  
  https://github.com/google/adk-python/blob/main/src/google/adk/cli/api_server.py

- `agent_loader.py`（`agents_dir` の `sys.path` 追加と App / root_agent の探索）  
  https://github.com/google/adk-python/blob/main/src/google/adk/cli/utils/agent_loader.py

- `skill_toolset.py`（ADK 標準の Skill 前置き）  
  https://github.com/google/adk-python/blob/main/src/google/adk/tools/skill_toolset.py

- `_tool_caller.py`（`_extract_multimodal_parts`）  
  https://github.com/google/adk-python/blob/main/src/google/adk/flows/llm_flows/_tool_caller.py

### Long Horizon Harness

- Long Horizon Harness  
  https://github.com/google/adk-recipes/tree/main/core/python/long-horizon-harness

- `HorizonSkillToolset`  
  https://github.com/google/adk-recipes/blob/main/core/python/long-horizon-harness/horizon/tools/skill_toolset.py

- Skill loader（user skills の Sandbox → ホストのミラー）  
  https://github.com/google/adk-recipes/blob/main/core/python/long-horizon-harness/horizon/tools/skill_loader.py

- System prompt  
  https://github.com/google/adk-recipes/blob/main/core/python/long-horizon-harness/horizon/conversation/system_prompt.py

- File operations / `ReadTool`  
  https://github.com/google/adk-recipes/blob/main/core/python/long-horizon-harness/horizon/tools/file_ops.py  
  https://github.com/google/adk-recipes/blob/main/core/python/long-horizon-harness/horizon/tools/read.py

### Strands Agents

- Harness  
  https://strandsagents.com/docs/user-guide/harness/

- `read`（画像 / PDF を Tool result の block として返す）  
  https://github.com/strands-agents/harness-sdk/blob/main/harness-py/src/strands_harness/tools/file_tools.py
