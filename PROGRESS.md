# Progress

## 現在地

- **Lesson 0: 完了**
- **Lesson 1: 完了**
- **Lesson 2: 完了**
- **Lesson 3: 完了**
- **Lesson 4: 完了**
- **Lesson 5: 完了**
- **Lesson 6: 完了**
- **Lesson 7: 完了**
- **Lesson 8: 完了**
- Lesson 7 の App を `agents_dir` 配下の package に整理し、ADK 標準 `adk api_server` から読み込める構成にした。自前 FastAPI routing は追加していない。
- OpenAPI から Session / `/run` / `/run_sse` / Artifact API を確認し、client から Session 作成・text chat・streaming・attachment 送信・output Artifact 取得までを HTTP 経由で実行済み。
- `WorkspaceIOPlugin` を変更せずに、API 経由の attachment が Artifact → `workspace/input/` へ流れることを確認済み。Lesson 7 の Host export は Artifact API からの取得に置き換えた。
- Skill を Environment 作成時に Sandbox の `skills/` へコピーし、LHA の `HorizonSkillToolset` で ADK 標準の Skill 前置きを短い1文に差し替えた。`scripts/` 付き Skill を `bash` で実行できることを確認済み。
- LHA の system prompt を元にした英語の `static_instruction` に置き換えた。
- `read` に offset / limit と画像 / PDF 対応、一意一致の `edit` を追加した。media は ADK の multimodal function response で Tool result として履歴に残る方式（Strands harness と同じ）を採用した。
- 複数 Session で会話履歴・Workspace・Artifact が分離されることを E2E client（`client.py`）で確認済み。

## 次に始めるセクション

**なし — 学習プロジェクト完了**

Lesson 0〜8 で、Agent / Tool / MCP / Skill / Artifact / Workspace / Sandbox / Callback / Plugin / Context Management / File I/O を ADK 標準 API server に載せ、外部 client から利用できる Agent backend までつないだ。

これをもって `study-adk-from-scratch` の学習プロジェクトを完了とする。
