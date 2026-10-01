# Lesson 7 Plan — Artifact ↔ Workspace I/O Pipeline

> **Status: 完了（2026-10-02）**  
> このファイルは Lesson 7 開始時の設計・実装計画を残すためのもの。最終的な学びと実装結果は [LESSON_07.md](./LESSON_07.md) を参照。
>
> 最終実装では、当初案から以下を変更した。
>
> - Step 8 の Skill based processing は意図的にスキップ。
> - volatile reminder は「新規 input のみ」ではなく、現在の `input/` の file list を各 Model Call の末尾に追加。
> - output は `before_agent / after_agent` の `filename + size + mtime` metadata snapshot を比較し、変更された file のみ Artifact 化。
> - filesystem watcher / inotify は検討したが採用しなかった。
> - host export は最終 output Artifact を対象とし、Agent の外側の Runner で実施。
> - Sandbox runtime の `server.py` は変更しない。

## Goal

Lesson 7 では、ユーザーが添付したファイルを Agent が Workspace 上で処理し、最終成果物をユーザーへ返すまでの **入力 → 処理 → 出力** パイプラインを一気通貫で接続する。

Agent 自身には Artifact API を直接扱わせず、**ユーザーとのファイル境界は `workspace/input/` と `workspace/output/` に限定する**。

最終的に確認したい流れは以下。

```text
Browser / User
    │
    │ text + attachments[]
    ▼
Backend / ADK
    │
    │ attachment handling
    ▼
InMemoryArtifactService
    │
    │ materialize
    ▼
Sandbox Workspace
├─ input/    User → Agent
├─ work/     Agent internal working files
└─ output/   Agent → User
    │
    │ promote output files
    ▼
InMemoryArtifactService
    │
    ├─ Browser / User へ返却
    └─ Host filesystem へ export（学習・確認用）
```

---

## Core Design

### 1. Agent が見るファイル境界

System Instruction で以下を明示する。

- `workspace/input/` はユーザーから渡された入力ファイル。
- `workspace/output/` はユーザーへ返す最終成果物。
- `workspace/work/` は Agent 内部の中間生成物・作業領域。
- Agent とユーザーの間でやり取りするファイルは、原則として `input/` と `output/` のみ。
- Artifact API は Agent の Tool として公開しない。

責務は次のように分離する。

```text
Agent
    Workspace 上のファイルを読む・処理する・書く

Harness / Plugin
    User attachment ↔ Artifact ↔ Workspace の橋渡しを行う

ArtifactService
    外部ファイル・成果物の永続化レイヤー
```

---

### 2. Attachment protocol

画像、PDF、動画、音声などを別プロトコルにせず、共通の `attachments[]` として扱う。

最低限、各 attachment は次の情報を持つ想定。

```text
name
mime_type
size
artifact_id / artifact reference
```

動画も同じ経路に載せる。大容量ファイルのオンデマンド取得などは将来の最適化とし、Lesson 7 ではまず同じ materialize フローで扱う。

---

### 3. Browser boundary と Backend boundary を分離する

ファイルを選択しただけでは Backend に送らない。

```text
Browser
  file select
  file remove / replace
  ↓
  Send
──────── Browser / Backend boundary ────────
Backend
  text + attachments[] を受信
```

これにより、ユーザーが「やっぱり添付をやめた」と取り消した場合は Backend に何も残らない。

Backend に届いた後で初めて、そのファイルを今回の Interaction の入力として扱う。

---

## Runtime lifecycle

完成形では `WorkspaceIOPlugin` を中心に、1 Invocation の I/O lifecycle を管理する。

想定する役割分担は以下。

```text
on_user_message
    今回の user message / attachments を受理
    今回追加された attachment を把握する

before_run
    Workspace / Sandbox を準備
    新規 attachment を Artifact として保存
    新規 attachment だけ workspace/input/ に materialize

before_model
    このターンで追加された input を volatile reminder として通知

after_agent / after_run
    workspace/output/ の最終成果物を Artifact 化
    必要な cleanup を行う
```

実装時には ADK lifecycle を観察しながら、どの hook に何を置くのが最も自然か確認する。

---

## Incremental input sync

毎ターン Artifact 全件を `input/` に書き戻す方式は採用しない。

Sandbox / Workspace は Session 中残るため、通常ターンでは既存ファイルに触らず、**そのターンで新しく追加された attachment のみ materialize** する。

```text
Turn 1
  foo.pdf 添付
  → input/foo.pdf を materialize

Turn 2
  text only
  → file I/O なし

Turn 3
  bar.xlsx 添付
  → input/bar.xlsx だけ materialize
```

Workspace の状態と、そのターンで追加された input は別概念として扱う。

```text
Durable workspace state
    input/foo.pdf
    input/bar.xlsx

Turn-local context
    new_inputs = ["input/bar.xlsx"]
```

`new_inputs` は Session State に永続化する情報ではなく、原則として Invocation / Turn-local な情報として扱う。

---

## Volatile reminder

Lesson 6 で扱った volatile context の考え方を利用する。

新しい attachment があるターンだけ、例えば以下のような reminder を model context に追加する。

```text
<system-reminder>
New user input files were added:
- input/bar.xlsx

These files are available in the workspace.
</system-reminder>
```

Workspace に存在する全ファイル一覧を毎ターン注入しない。

過去ファイルが必要なら Agent が `input/` を参照する。

---

## Test scenarios

### Scenario A — File-attached chat, read only

ユーザーがファイル付きチャットを送る。

例:

```text
このファイルの内容を読んで要約して
```

期待する動作:

```text
Browser attachment
→ Artifact
→ workspace/input/
→ Agent が read / bash 等で確認
→ Chat response
```

成果物ファイルの生成は不要。

---

### Scenario B — Skill based file processing

ファイル処理を行う Skill を追加する。

Skill には次のファイル規約を持たせる。

```text
input/
    user input

work/
    intermediate files

output/
    final deliverables only
```

Agent は Skill に従い、中間生成物を `work/` に作り、最終成果物だけを `output/` に配置する。

これにより、単純なファイル付きチャットだけでなく、複数ステップのファイル処理も確認する。

---

## Output pipeline

現在、Lesson 7 では `after_agent_callback` による次の経路まで確認済み。

```text
Agent
→ workspace/output/report.txt
→ after_agent
→ read_file
→ callback_context.save_artifact(...)
→ InMemoryArtifactService
```

Agent Tool は `read / write / bash / process` のみであり、Agent 自身は `save_artifact()` を呼ばない。

今後はこれを `WorkspaceIOPlugin` を含む全体 I/O lifecycle に整理する。

---

## Host export for observation

Lesson 7 では `InMemoryArtifactService` を利用するため、Python process が終了すると Artifact は消える。

学習・デバッグ目的で、入力と出力の Artifact を **Agent の外側** でホスト filesystem に export する。

例えば以下のような構成を想定する。

```text
lessons/lesson_07/local_artifacts/
├─ input/
│  └─ sample.pdf
└─ output/
   └─ result.md
```

これは Agent のファイルプロトコルには含めない。

```text
Agent boundary
    workspace/input/
    workspace/output/

Harness
    ArtifactService

Learning / debug only
    Host filesystem export
```

Input / Output 両方をホストへ保存し、実際に何が Artifact として入り、何が成果物として出てきたかを Python process 終了後も目視確認できるようにする。

---

## Step-by-step implementation plan

### Step 0 — Output → Artifact

**完了済み。**

- Agent は `workspace/output/` に書く。
- `after_agent_callback` が `output/` を scan。
- ファイル bytes を `InMemoryArtifactService` に保存。
- `report.txt version=0` まで動作確認済み。

### Step 1 — WorkspaceIOPlugin lifecycle

- Lesson 6 の `plugin.py` を土台として流用。
- `WorkspaceIOPlugin` を作成。
- まず `on_user_message → before_run → Agent lifecycle` の順序だけ観察する。
- この段階では attachment / Artifact / Workspace I/O はまだ追加しない。

### Step 2 — attachments[] の疑似入力

- Browser / UI の代わりに Runner から attachment 付き Interaction を作る。
- text-only turn と attachment turn を区別する。
- 今回の attachment を Turn-local input として扱えることを確認する。

### Step 3 — Input Artifact registration

- Backend に届いた attachment を `InMemoryArtifactService` へ保存する。
- Artifact API は Agent には公開しない。

### Step 4 — Artifact → workspace/input/

- 新規 attachment のみ materialize。
- 過去 input の再コピーは行わない。
- bytes が Sandbox 内の実ファイルとして存在することを確認する。

### Step 5 — Volatile reminder

- `new_inputs` を `before_model` で system reminder に追加する。
- 新しい attachment がないターンでは reminder を追加しない。
- Lesson 6 の volatile context と接続する。

### Step 6 — Read-only file chat

- 実際のファイルを添付。
- Agent が `workspace/input/` から読み込む。
- ファイルを生成せず、Chat response のみ返すケースを確認する。

### Step 7 — Workspace file protocol in System Instruction

Agent に以下を明示する。

```text
input  = user → agent
work   = agent internal
output = agent → user
```

Artifact の存在は Agent に意識させない。

### Step 8 — Skill based processing

- Skill を有効化。
- input を読み込む。
- work に中間生成物を作る。
- output に最終成果物を置く。
- Agent がこの規約に従ってファイル処理できることを確認する。

### Step 9 — Output Artifact pipeline integration

- 既存 `after_agent` の `output/ → Artifact` 処理を全体 I/O lifecycle に統合する。
- 中間生成物は Artifact 化しない。
- `output/` のみユーザー成果物として昇格する。

### Step 10 — Host filesystem export

- Input Artifact を host `local_artifacts/input/` へ export。
- Output Artifact を host `local_artifacts/output/` へ export。
- Python process 終了後も成果物を確認できる状態にする。

### Step 11 — End-to-end verification

最終的に以下を一気通貫で確認する。

```text
User attachment
→ Backend interaction
→ Artifact
→ workspace/input/
→ Agent / Skill
→ workspace/work/
→ workspace/output/
→ Artifact
→ Host export
```

---

## Current next step

次は **Step 1 — WorkspaceIOPlugin lifecycle** から開始する。

Lesson 6 の Plugin 実装をコピーして最小化し、まず次の順序だけを観察する。

```text
on_user_message
→ before_run
→ before_agent
→ before_model
→ Agent
→ after_agent
```

この lifecycle を確認した後、attachments の疑似入力へ進む。
