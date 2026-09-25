# Lesson 3 — Artifacts

## Lesson 3 の目的

ADK の Artifact を追加し、Session / State とは別にファイルやバイナリデータを管理する仕組みを理解する。

このLessonでは `InMemoryArtifactService` を `Runner` に接続し、通常の Function Tool から `ToolContext` を通して Artifact の保存・一覧取得・読み込みを行った。

最終的に確認した実行経路は次の通り。

```text
User
 ↓
LLM
 ↓
Function Tool
 ↓
ToolContext
 ↓
save_artifact / list_artifacts / load_artifact
 ↓
ArtifactService
 ↓
Artifact
```

## 1. Artifact は Session State とは別に管理される

Lesson 0 から利用している `Session` には、会話履歴となる Events と State が含まれる。

```text
SessionService
└─ Session
   ├─ Events
   └─ State
```

State は Session と独立した Service ではなく、Session が持つ実行状態の一部である。

一方 Artifact は、`ArtifactService` という別の Service で管理される。

今回の `Runner` は次の構成になった。

```text
Runner
├─ InMemorySessionService
│  └─ Session
│     ├─ Events
│     └─ State
│
└─ InMemoryArtifactService
   └─ Artifacts
```

Artifact の保存・一覧取得・読み込みを行っても、今回の実行後の Session State は空のままだった。

したがって、

```text
State
= Agent の実行状態を保持する

Artifact
= ファイルやバイナリデータなどの実体を保持する
```

という責務の違いを確認できた。

## 2. ArtifactService は Runner に接続する Runtime Service

`runner.py` では `InMemoryArtifactService` を作成し、`Runner` に渡した。

```python
session_service = InMemorySessionService()
artifact_service = InMemoryArtifactService()

runner = Runner(
    app=app,
    session_service=session_service,
    artifact_service=artifact_service
)
```

この時点では Agent に新しい Tool が自動追加されるわけではない。

ArtifactService を Runner に接続することは、Runtime に Artifact を保存・取得できる基盤を追加することを意味する。

```text
Runner
 ↓
Invocation Context
 ↓
ArtifactService
```

今回使用した `InMemoryArtifactService` はメモリ上に Artifact を保持するため、学習用の最小構成として利用した。

## 3. Artifact を操作する Tool は普通の Function Tool

今回追加した、

```text
save_text_file
list_text_files
load_text_file
```

は Artifact 専用の特殊な Tool ではなく、`get_weather` と同じ通常の Function Tool である。

Agent には明示的に次のように登録した。

```python
tools=[
    get_weather,
    save_text_file,
    list_text_files,
    load_text_file,
]
```

違いは、Artifact を操作する Tool が引数として `ToolContext` を受け取ることにある。

## 4. ToolContext は Tool から ADK Runtime へアクセスする窓口

保存 Tool は次の形にした。

```python
async def save_text_file(
    filename: str,
    content: str,
    tool_context: ToolContext,
) -> dict:
    ...
```

`filename` と `content` は LLM が Function Call の引数として決める。

一方 `tool_context` は LLM が生成する引数ではなく、ADK Runtime が Tool 実行時に自動的に渡す。

```text
LLM が決める
├─ filename
└─ content

ADK Runtime が渡す
└─ ToolContext
```

`ToolContext` からは、現在の Invocation に紐づく State や ArtifactService などへアクセスできる。

今回の Artifact 操作では、Tool 側が `app_name`、`user_id`、`session_id`、利用する ArtifactService を個別に受け取る必要はなく、`ToolContext` が現在の Runtime 情報を使って ArtifactService へ接続した。

```text
Function Tool
 ↓
ToolContext
 ↓
現在の Invocation 情報
 ↓
ArtifactService
```

## 5. Artifact の内容は `google.genai.types.Part` で渡す

ArtifactService に保存する Artifact の内容は `types.Part` として渡した。

テキスト保存では、

```python
artifact = types.Part.from_text(text=content)
```

としてから、

```python
version = await tool_context.save_artifact(
    filename=filename,
    artifact=artifact,
)
```

を実行した。

つまり今回の Artifact は概念的には、

```text
filename
+ version
+ types.Part
```

として管理される。

`types.Part` はテキストだけでなく bytes と MIME type を持つデータも表現できるため、画像やPDFなども Artifact として扱える。

## 6. ToolContext から save / list / load を実行できる

今回、Artifact の基本操作として3つを確認した。

### 保存

```python
await tool_context.save_artifact(
    filename=filename,
    artifact=artifact,
)
```

保存すると version 番号が返る。

### 一覧取得

```python
await tool_context.list_artifacts()
```

現在の Session から見える Artifact の filename 一覧を取得できる。

### 読み込み

```python
await tool_context.load_artifact(
    filename=filename,
)
```

version を指定しない場合は最新 version が読み込まれ、戻り値は保存時と同じ `types.Part` になる。

今回のテストでは、

```text
save_text_file
 ↓
hello.txt を保存

list_text_files
 ↓
['hello.txt']

load_text_file
 ↓
hello artifact
```

まで確認した。

## 7. 同名 Artifact の保存は versioning される

最初の実験では Model が同じ `save_text_file` を3回呼び出したため、意図せず Artifact の versioning も確認できた。

```text
hello.txt
├─ version 0
├─ version 1
└─ version 2
```

ArtifactService が勝手に重複保存したわけではなく、ログ上では異なる FunctionCall ID で Model が3回 Tool を呼んでいた。

したがって、

```text
LLM
= Tool を呼ぶか判断する

Runner
= FunctionCall ごとに Tool を実行する

ArtifactService
= 同じ filename への保存を新しい version として管理する
```

という責務分担になる。

## 8. 複数 Tool Call は同じ Model Response から発行できる

最終確認では、ユーザーから、

```text
保存し、Artifactの一覧を表示・読み込みを行い、
Artifactが本当に保存されたか確認して
```

と指示した。

Model は1回の Response 内で、

```text
save_text_file
list_text_files
load_text_file
```

の3つの FunctionCall をまとめて生成した。

その後、それぞれの FunctionResponse がまとめて返り、最後に Final Response が生成された。

```text
User
 ↓
Model Response
 ├─ save_text_file
 ├─ list_text_files
 └─ load_text_file
 ↓
Function Responses
 ↓
Final Response
```

このため、`save_text_file` の戻り値に書いた次の Tool を促す `note` を読んでから `load_text_file` が選ばれたわけではない。

Model はユーザー指示、Tool名、docstring、引数 schema などから、最初の段階で3つの Tool が必要だと判断していた。

## 9. Lesson 3 終了時点の責務分担

```text
Runner
├─ SessionService
│  └─ Session
│     ├─ Events
│     └─ State
│
└─ ArtifactService
   └─ named / versioned Artifacts

LlmAgent
└─ Function Tools
   ├─ save_text_file
   ├─ list_text_files
   └─ load_text_file
          │
          ▼
      ToolContext
          │
          ▼
   ArtifactService
```

Lesson 3 で得た最も重要な理解は、Artifact が Session State にファイルを詰め込む仕組みではなく、**Runner に接続された独立した ArtifactService が named / versioned data を管理し、Tool は ToolContext を通してその Runtime Service を利用する**という点。

## 参照した公式ドキュメント・実装

- ADK — Artifacts  
  https://adk.dev/artifacts/

- ADK — Agent context  
  https://adk.dev/context/

- ADK — Custom Tools / Tool Context  
  https://adk.dev/tools-custom/

- ADK Python — `Context` implementation (`save_artifact`, `load_artifact`, `list_artifacts`)  
  https://github.com/google/adk-python/blob/main/src/google/adk/agents/context.py

- ADK Python — `InMemoryArtifactService`  
  https://github.com/google/adk-python/blob/main/src/google/adk/artifacts/in_memory_artifact_service.py
