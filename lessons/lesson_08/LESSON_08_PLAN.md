# Lesson 8 Plan — ADK API Server / Final Integration

## Goal

Lesson 8 はこの学習プロジェクトの最終 Lesson とする。

Lesson 0〜7 で作ってきた Agent / Tool / MCP / Skill / Artifact / Workspace / Sandbox / Callback / Plugin / Context Management / File I/O を、**ADK 標準の API serving 境界に載せて、外部アプリから利用できる Agent backend として成立させる**。

自前の FastAPI API を新規設計することは主目的にしない。

基本方針は、

```text
Lesson 0〜7 の App
        ↓
ADK standard API server
        ↓
REST / streaming API
        ↓
Client
```

とする。

---

## Scope

### やること

- Lesson 7 までの App を API server から読み込める構成に整理する。
- ADK 標準 API server を起動する。
- OpenAPI / Swagger UI で公開 API を確認する。
- API 経由で Session を作る。
- API 経由で通常の chat interaction を実行する。
- streaming interaction を確認する。
- attachment 付き interaction を API 経由で実行する。
- Artifact → Workspace input → Agent → Workspace output → Artifact の経路が API serving 下でも動くことを確認する。
- 複数 Session が分離されることを確認する。
- 最終的に、この repo を「Agent の内部構造を学ぶ教材」から「外部アプリから利用可能な backend」までつなげる。

### やらないこと

- 自前 FastAPI routing の設計。
- frontend / Web UI の作成。
- authentication / authorization。
- production deployment。
- persistent database。
- production 用 durable ArtifactService。
- Guardrail / HITL / Sub-agent / Memory などの新しい Agent 機能追加。

Lesson 8 は新機能追加ではなく、**これまで作ったものの統合確認**に集中する。

---

## Target architecture

```text
Client
  │
  │ HTTP / streaming
  ▼
ADK API Server
  │
  ▼
App
  │
  ├─ WorkspaceIOPlugin
  ├─ Agent callbacks
  ├─ Context management
  ├─ Tools / MCP
  └─ Agent
        │
        ▼
SessionService
ArtifactService
Sandbox / Workspace
  ├─ input/
  ├─ work/
  └─ output/
```

責務は次のように見る。

```text
ADK API Server
= external serving boundary

Runner / ADK Runtime
= Agent execution

SessionService
= conversation state

ArtifactService
= external file boundary

Workspace / Sandbox
= Agent execution filesystem

Agent
= reasoning + tool use
```

---

## Step-by-step plan

### Step 1 — API server で App を起動する

Lesson 7 の App を ADK 標準 API server から読み込める状態にする。

まずは既存コードを大きく変えず、

```text
API server
→ App discovery / load
→ root_agent
```

まで確認する。

---

### Step 2 — OpenAPI / Swagger を見る

起動した API server の OpenAPI / Swagger UI を確認する。

ここで、

- Session API
- interaction / run API
- streaming API
- Artifact 関連 API

がどのように公開されているかを、**その時点のインストール済み ADK の実際の API 定義を正として確認する**。

endpoint 名を教材側で決め打ちしない。

---

### Step 3 — API から Session を作る

これまで Python から、

```python
session_service.create_session(...)
```

としていた処理を、外部 client から API 経由で行う。

Session ID を変えた場合に会話履歴が分離されることも確認する。

---

### Step 4 — API から chat interaction を実行する

text-only message を API server に送る。

```text
Client
→ API Server
→ Runner
→ Agent
→ Event
→ API response
```

という流れを確認する。

---

### Step 5 — streaming を確認する

通常 response だけでなく streaming interaction も確認する。

ここでは frontend は作らず、curl / HTTP client などから Event が順番に返ることだけ確認する。

---

### Step 6 — attachment を API 経由で渡す

Lesson 7 で runner から直接作っていた attachment input を、API serving 境界から渡す。

期待する流れは、

```text
Client attachment
→ ADK API Server
→ user message
→ WorkspaceIOPlugin
→ ArtifactService
→ workspace/input/
→ Agent
```

となること。

---

### Step 7 — output Artifact を確認する

Agent に output file を生成させる。

```text
Agent
→ workspace/output/
→ changed output detection
→ ArtifactService
```

が API server 経由でも動くことを確認する。

必要に応じて Artifact API から生成物を取得し、外部 client から成果物を受け取れることを確認する。

---

### Step 8 — End-to-end verification

最終的に次を一気通貫で確認する。

```text
Client
→ Session creation
→ text + attachment
→ ADK API Server
→ WorkspaceIOPlugin
→ Artifact
→ workspace/input/
→ Agent / Tool / Sandbox
→ workspace/output/
→ Artifact
→ Client
```

加えて、

```text
Session A
Session B
```

で会話履歴と Workspace / runtime state が意図通り分離されることも確認する。

---

## Definition of Done

Lesson 8 完了条件は次の通り。

- ADK 標準 API server で App が起動する。
- API 経由で Session を作れる。
- API 経由で text chat ができる。
- streaming response を確認できる。
- attachment を送れる。
- attachment が Artifact → workspace/input/ に流れる。
- Agent が Sandbox / Workspace で処理できる。
- output file が Artifact として外へ戻る。
- Session を分けた場合に conversation / runtime が分離される。
- 自前 FastAPI routing を追加せず、ADK 標準 serving boundary で一連の構成を確認できる。

これをもって `study-adk-from-scratch` の学習プロジェクトを完了とする。
