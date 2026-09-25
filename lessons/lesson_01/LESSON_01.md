# Lesson 1 — Tool Calling と MCP

## Lesson 1 の目的

ADK Agent に Tool を追加し、LLM が Tool の利用を判断してから、Tool の実行結果を使って最終回答を生成するまでの流れを理解する。

このLessonでは、まず同一Pythonプロセス内の Function Tool を使い、その後 Tool の実体を Windows 上の外部 MCP Server に置き換えた。

最終的に確認した実行経路は次の2つ。

```text
Function Tool

LLM
 ↓
FunctionCall Event
 ↓
ADK
 ↓
Python function
 ↓
FunctionResponse Event
 ↓
LLM
 ↓
Final Response Event
```

```text
MCP Tool

LLM
 ↓
FunctionCall Event
 ↓
ADK / McpToolset
 ↓
MCP tools/call
 ↓
External MCP Server
 ↓
FunctionResponse Event
 ↓
LLM
 ↓
Final Response Event
```

## 1. Python関数をToolとして登録できる

ADKでは通常のPython関数を `LlmAgent.tools` に渡すことで、Agentが利用できるFunction Toolとして扱える。

今回の最小例では、都市名を受け取って固定の天気情報を返す関数を作った。

```python
def get_weather(city: str) -> dict:
    """指定された都市の天気を返します。"""
    return {
        "city": city,
        "weather": "sunny",
        "temperature": 25,
    }
```

Agent側では、

```python
tools=[get_weather]
```

と登録した。

重要なのは、Tool登録時に関数が実行されるわけではないこと。

```text
Python function
      ↓
AgentへToolとして登録
      ↓
LLMが必要と判断したときだけ実行
```

関数名、docstring、型情報などからTool定義が作られ、LLMには利用可能なToolのschemaとして渡される。

## 2. Toolを使うかどうかはLLMが判断する

ユーザーから、

```text
神戸の天気を教えて
```

と入力すると、LLMは最終回答を直接生成するのではなく、まず次のFunctionCallを生成した。

```text
name = get_weather
args = {
  city: 神戸
}
```

ここでの責務は、

```text
LLM
= どのToolを使うか
= どの引数を渡すか
```

である。

LLM自身がPython関数を実行しているわけではない。

## 3. Tool Callingでは1 Invocationに複数Eventが流れる

Function Toolを実行したとき、Runnerから次の3つのAgent Eventが観察できた。

```text
FunctionCall Event
Final: False

FunctionResponse Event
Final: False

Final Response Event
Final: True
```

実際の流れは、

```text
User message
     ↓
LLM
     ↓
FunctionCall Event
     ↓
Tool execution
     ↓
FunctionResponse Event
     ↓
LLM
     ↓
Final Response Event
```

となる。

したがって、Agentの1回の実行は必ずしも「LLM response 1個」ではない。

Tool Callingを含む場合、1つのInvocationの中で複数Eventを順番に処理しながら実行が進む。

## 4. LLM / ADK / Tool / Runner の責務

今回のFunction Tool実行から、各レイヤーの責務を次のように整理できる。

```text
LLM
= Toolを使うか判断
= Tool名と引数を生成
= Tool結果を使って最終回答を生成

Tool
= 実際の処理を実行

ADK
= Tool定義をLLMへ渡す
= FunctionCallを受けてToolを実行
= Tool結果をFunctionResponseとしてLLMへ戻す

Runner
= Invocation全体を進行
= EventをSessionへ記録
= Eventを呼び出し元へyield
```

最も重要なのは、

```text
LLM = 意思決定
Tool = 実処理
ADK = 両者を接続
Runner = 実行全体の調整
```

という分担。

## 5. SessionにはTool実行過程もEventとして残る

Toolを使った1ターンでは、Sessionに次のEventが保存された。

```text
Event 0: user input
Event 1: function_call
Event 2: function_response
Event 3: final response
```

したがってSessionのEvent historyは、単なるユーザーとAgentの発言履歴ではない。

```text
Session Events
= 会話
+ Agentの途中実行
```

Tool CallやTool Resultも、Agent Runtimeの実行履歴として残る。

また、FunctionResponse Eventでは、

```text
author = study_agent
role   = user
```

となる場合がある。

`author` はEventを生成した主体を表し、`content.role` はLLMへ渡す会話履歴上のroleを表すため、両者は同じ概念ではない。

## 6. MCPを使うとTool実装をAgentから分離できる

次に、Toolの実体を同一Pythonプロセス内から外部MCP Serverへ移した。

今回の構成は次の通り。

```text
WSL
study-adk-from-scratch
ADK Agent
     │
     │ Streamable HTTP / MCP
     ▼
Windows
printer-mcp
     │
     ▼
PowerShell Get-Printer
     │
     ▼
Windows Printer subsystem
```

Windows側には独立したMCP Serverを立て、Windowsにインストールされているプリンター一覧を取得する `list_printers` Toolを公開した。

実際に、

```text
OneNote (Desktop)
Microsoft Print to PDF
Canon MG7700 series Printer WS
```

などのWindows側プリンター情報を、WSL上のADK Agentから取得できた。

この構成では、AgentとToolが、

- 別プロセス
- 別OS
- 別プロジェクト

に分離されている。

## 7. `McpToolset` がMCP ServerをADK Toolへ接続する

WSL側では、外部MCP Serverへの接続を `McpToolset` としてAgentへ登録した。

概念的には、

```text
LlmAgent
├─ Model
└─ Tools
    └─ McpToolset
         │
         ▼
      MCP Server
```

という構造になる。

Function ToolではAgent側がPython関数そのものを知っていた。

```text
Function Tool

ADK
└─ get_weather()
```

一方MCPでは、Agent側は個々のTool実装を直接知らない。

```text
MCP Tool

ADK
└─ McpToolset
      │
      ▼
   MCP Server
      ├─ list_printers
      └─ ...
```

Agent側に `list_printers` の実装を書く必要はない。

## 8. MCPではTool Discoveryがprotocol化されている

MCP Serverのmiddlewareで実際の通信を観察したところ、最初に次の流れが確認できた。

```text
initialize
↓
notifications/initialized
↓
tools/list
```

`initialize` ではClientとServerがprotocol versionやcapabilityを交換する。

その後ADK側から、

```text
tools/list
```

が送られた。

Serverは、

```text
name:
  list_printers

description:
  List printers installed on this Windows PC.

inputSchema:
  {}
```

などのTool定義を返した。

このためADK側にTool名を直接定義していなくても、MCP Serverが公開しているToolをAgentが利用できる。

つまりMCPは、単にToolをリモート実行する仕組みだけではなく、

```text
相手がどんなToolを持っているか
```

を標準的にDiscoveryする仕組みでもある。

## 9. MCP Tool実行は `tools/call` になる

LLMが `list_printers` を使うと判断すると、MCP Server側では次の通信が観察できた。

```text
method = tools/call

params = {
  name: list_printers,
  arguments: {}
}
```

実行経路は、

```text
LLM
 ↓
FunctionCall
 ↓
ADK MCPTool
 ↓
MCP tools/call
 ↓
Windows MCP Server
 ↓
list_printers()
 ↓
PowerShell Get-Printer
```

となる。

重要なのは、LLMがMCP protocolを直接話しているわけではないこと。

```text
LLM
= list_printersを使うと判断

ADK / MCPTool
= その判断をMCP tools/callへ変換

MCP Server
= 対応するToolを実行
```

という責務分担になる。

## 10. MCPのTool ResultをADKがFunctionResponseへ変換する

MCP ServerからのTool Resultでは、次のような構造が観察できた。

```text
content
structuredContent
isError
```

プリンター一覧は `structuredContent.result` に構造化されたデータとして含まれていた。

ADK側では、このMCP Tool Resultが最終的に、

```text
FunctionResponse Event
```

としてEvent Loopへ戻された。

そのためADKのEvent Layerから見ると、Function ToolとMCP Toolは非常に似ている。

```text
Function Tool

FunctionCall Event
↓
local Python function
↓
FunctionResponse Event
```

```text
MCP Tool

FunctionCall Event
↓
MCP tools/call
↓
remote Tool
↓
FunctionResponse Event
```

## 11. ADK EventとMCP RPCは別レイヤー

今回、ADK側ではCallとResponseが別Eventとして観察された。

```text
FunctionCall Event
↓
FunctionResponse Event
```

一方MCP Serverのmiddlewareでは、1回の `tools/call` に対して、

```text
request
↓
Tool execution
↓
result
```

を1つのRPC処理として観察した。

これは矛盾ではなく、見ているレイヤーが違う。

```text
ADK Event Layer

FunctionCall Event
      ↓
   Tool実行
      ↓
FunctionResponse Event


MCP Protocol Layer

tools/call request
      ↓
   Tool実行
      ↓
tools/call response
```

MCPを使っても、ADK Runtime側のTool Calling Eventモデルは維持される。

## Lesson 1 終了時点のメンタルモデル

```text
                         Runner
                           │
                           ▼
                          App
                           │
                           ▼
                       LlmAgent
                      /        \
                     ▼          ▼
                   Model       Tools
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
              FunctionTool              McpToolset
                    │                       │
              Python function          MCP Protocol
                                            │
                              ┌─────────────┴─────────────┐
                              ▼                           ▼
                         Tool Discovery              Tool Call
                          tools/list                 tools/call
                              │                           │
                              └─────────────┬─────────────┘
                                            ▼
                                       MCP Server
                                            │
                                            ▼
                                     External System
```

Lesson 1で得た最も重要な理解は、Tool実装の場所が変わっても、LLMから見たTool CallingとADK RuntimeのEventモデルを共通化できること。

```text
LLM
= Toolを選ぶ

ADK
= Tool CallingをRuntimeとして扱う

FunctionTool / MCPTool
= 実行先へのadapter

Tool実装
= 実際の外部処理
```

Function Toolでは実行先がローカルPython関数であり、MCP ToolではMCP protocolの向こう側にある外部Toolになる。

この分離により、Agent Runtimeを大きく変えずに、ローカル機能、別プロセス、別OS、将来的には顧客PCやデバイス側の機能へTool実行先を広げられる。