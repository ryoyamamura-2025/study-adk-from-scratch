# study-adk-from-scratch — Project Overview

## 目的

`study-adk-from-scratch` は、Google Agent Development Kit（ADK）を「完成済みの便利APIとして使う」のではなく、**小さなAgentからAgent Harnessを段階的に組み上げることで内部構造を理解する**ための学習プロジェクト。

教育設計は LangChain の `create_agent` から Deep Agents 相当を一段ずつ組み立てる教材を参考にし、実装上の正は Google ADK の公式ドキュメントと公式/curated recipe を優先する。

最終目標は次の2つ。

1. ADK のコードを読んで、Agent / Runtime / Session / Tool / Skill / Sandbox / Sub-agent / Memory / HITL などの責務を説明・変更できること。
2. ADK を土台に、Google Managed Agents API のような **config-driven なAgent実行基盤**を自分で設計・実装できること。

完成形そのものを最初からコピーするのではなく、各機能を必要になった順に追加し、「何が増えたのか」「ADK本体の責務かHarness側の責務か」「どこを差し替え可能か」を理解することを重視する。

## 教材の方針

- 本体実装は Python script / package で進める。
- Notebook は内部状態やEventなどを観察する補助用途に限る。
- 便利なscaffoldを最初から使わず、ADKのプリミティブを明示的に組み合わせる。
- 各Lessonでは、まず最小実装を動かし、その後に公式ADKやLong Horizon Harnessの実装と照合する。
- LangChain/Deep Agentsは「教材の段階設計」の参考、Google ADK/公式recipeは「ADK実装の正」として扱う。
- 最終段階では、Agent configuration と runtime execution を分離し、Managed Agents APIに近い責務分割を自作する。

## 主な参照テキスト・ページ

### 教育設計の参考：LangChain / Deep Agents

- LangChain — Build a data analysis agent from scratch  
  https://github.com/langchain-ai/docs/blob/main/src/oss/langchain/deep-agent-from-scratch.mdx

- Deep Agents from Scratch repository  
  https://github.com/langchain-ai/deep-agents-from-scratch

- LangChain overview (`create_agent` と harness の考え方)  
  https://docs.langchain.com/oss/python/langchain/overview

### 実装の正：Google ADK

- ADK documentation  
  https://adk.dev/

- App  
  https://adk.dev/apps/

- Runtime / Event Loop  
  https://adk.dev/runtime/event-loop/

- Session / State / Memory overview  
  https://adk.dev/sessions/

- Session lifecycle  
  https://adk.dev/sessions/session/

- Vertex AI / Model Garden models from ADK  
  https://adk.dev/agents/models/vertex/

- Google Cloud setup for ADK  
  https://adk.dev/get-started/google-cloud/

### 完成形の参考：Long Horizon Harness

- ADK curated recipe index  
  https://github.com/google/agents-cli/blob/main/skills/google-agents-cli-adk-code/references/samples.md

- Long Horizon Harness recipe  
  https://github.com/google/adk-samples/tree/main/core/python/long-horizon-harness

このrecipeは、sandbox、runtime-discovered `SKILL.md`、cross-session memory、guardrails、sub-agent delegation、durable HITL、secrets、context compactionなどを組み合わせた完成度の高いAgent Harnessとして参照する。教材では必要なpatternだけを段階的に理解・移植する。

### 最終アーキテクチャの参考：Google Managed Agents API

- Managed Agents API overview  
  https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/managed-agents

- Interactions API / agent interaction  
  https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/managed-agents/interact-with-agents

Managed Agents APIの `Agents API = control plane`、`Interactions API = data plane` という責務分離や、sandbox / skills / tools / persisted interaction を最終設計の参考にする。ただしAPIのクローンを作ること自体が目的ではない。

## 開発環境

### プロジェクト

```text
study-adk-from-scratch/
├─ pyproject.toml
├─ uv.lock
├─ .env
└─ lessons/
   └─ lesson_00/
      ├─ agent.py
      └─ runner.py
```

今後のLessonも `lessons/lesson_XX/` に追加する。

### Python / package management

- Python: 3.11以上を前提
- package manager: `uv`
- IDE/Editor: 任意（VS Codeを想定）
- 実装形式: `.py` script を基本とする
- Notebook: 実験・内部観察専用

初期セットアップ:

```bash
uv init
uv add google-adk
uv add "litellm>=1.84"
uv add python-dotenv
```

実際に解決されたpackage versionは `uv.lock` を正とする。

### Google Cloud認証

ローカル開発では Application Default Credentials (ADC) を使用する。

```bash
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
gcloud auth application-default print-access-token
```

Model Garden上で対象モデルの利用条件/EULAに同意し、有効化しておく。

### 開発用LLM

開発時のコストを抑えるため、Vertex AI Model Garden MaaS の Llama 4 Scout を利用する。

```text
vertex_ai/meta/llama-4-scout-17b-16e-instruct-maas
```

ADKからは `google.adk.models.lite_llm.LiteLlm` 経由で接続する。

現在の利用リージョン:

```text
us-east5
```

### `.env`

プロジェクトルートの `.env` を `python-dotenv` でロードする。

```env
GOOGLE_GENAI_USE_ENTERPRISE=TRUE
GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
GOOGLE_CLOUD_LOCATION=us-east5

VERTEXAI_PROJECT=YOUR_PROJECT_ID
VERTEXAI_LOCATION=us-east5

PYTHONUTF8=1
```

`.env` はsource controlに含めない。

```gitignore
.env
```

`GOOGLE_*` はADK / Google Cloud側、`VERTEXAI_*` は現在利用しているLiteLLM Vertex connector側の設定として保持する。

### 現在のモデル生成設定

Llama 4 Scout + LiteLLM + ADK の現在の開発環境では、出力上限を明示して利用している。

```python
from google.genai import types

generate_content_config=types.GenerateContentConfig(
    max_output_tokens=256,
)
```

切り分け時、LiteLLM単体では `max_tokens` を明示すると正常に呼び出せ、ADK側では `GenerateContentConfig.max_output_tokens` を設定することで正常動作を確認した。この設定は現時点のプロジェクト実行条件として維持する。

## 学習の到達イメージ

最小のADK Agentから始め、必要な能力を順番に追加して、最終的に概ね次の責務を自分で説明・変更できる状態を目指す。

```text
Agent Configuration
        ↓
App / Agent Factory
        ↓
ADK Runtime / Runner
        ↓
Session / State / Event
        ↓
Tools / Skills / MCP
        ↓
Workspace / Artifact / Sandbox
        ↓
Planning / Sub-agents
        ↓
Context management / Memory
        ↓
HITL / Guardrails
        ↓
API / Managed runtime
```

学習の成功条件は「完成コードが動くこと」ではなく、**各レイヤーがなぜ必要で、どこに実装され、何と差し替え可能なのかを説明してカスタマイズできること**。
