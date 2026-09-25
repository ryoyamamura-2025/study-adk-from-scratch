# Lesson 0 — ADK Runtime の骨格

## Lesson 0 の目的

最小のADK Agentを実際に動かしながら、LLMを呼ぶ前後に存在するADKの基本コンポーネントと、その責務分担を理解する。

Lesson 0ではToolやSkillなどの機能は追加せず、次の関係だけに集中した。

```text
App
 └─ root_agent (LlmAgent)
        └─ Model

Runner
 ├─ App
 └─ SessionService
        └─ Session
              ├─ State
              └─ Events
```

## 1. `LlmAgent` はLLMそのものではない

`LlmAgent` は「どのモデルを使い、どのinstructionで、どのようにAgentとして振る舞うか」を定義するオブジェクト。

概念的には次のように、ModelはAgentの構成要素の1つ。

```text
LlmAgent
├─ name
├─ instruction
├─ model
└─ generation config
```

したがって、

```text
Agent ≠ LLM
```

である。

ADKのAgent側にAgentとしての振る舞いを定義し、モデル接続は別レイヤーとして扱える。この分離により、同じAgent設計でもModel connectorを差し替えられる。

## 2. `Runner` はAgentを実行するオーケストレーター

Agentを定義しただけでは、ユーザー入力を受けて会話を進める実行ループは存在しない。

`Runner` が実行時の中心となり、

- 対象Sessionを取得する
- 新しいUser messageをSessionに記録する
- Agentを実行する
- Agentから生成されたEventを受け取る
- Eventに含まれる変更をServiceへ反映する
- Eventを呼び出し元へyieldする

という処理を調整する。

重要なのは、

```text
Agent = 実行ロジック
Runner = 実行の調整役
```

という分担。

## 3. `SessionService` と `Runner` は別の責務

`SessionService` はSessionを作成・取得・保存するServiceであり、`create_session()` を呼んでもRunnerやAgentは実行されない。

```text
SessionService
  ├─ create_session()
  ├─ get_session()
  └─ append_event()

Runner
  └─ AgentのInvocationを実行
```

Runnerを生成するときにSessionServiceを渡すのは、

> Runnerが実行時にSessionを読み書きするときは、このServiceを使う

と指定しているだけ。

つまりRunnerがSessionServiceを所有してSession作成を自動実行するのではなく、Runnerが同じSessionServiceへの参照を使って実行を進める。

## 4. `Session` は1つの会話スレッド

Sessionは単なる文字列のチャット履歴ではなく、1つの会話・実行コンテキストを表すデータコンテナ。

主に、

```text
Session
├─ app_name
├─ user_id
├─ session_id
├─ state
└─ events
```

を持つ。

SessionService上では、概念的に次の組み合わせで会話を識別する。

```text
(app_name, user_id, session_id)
```

そのため、同じ `user_id` / `session_id` でも `app_name` が異なれば別のSessionとして扱える。

## 5. `Event` がADK Runtimeの基本単位

ADKでは「1回のLLM responseを返す」というより、RuntimeがEventをやり取りしながらInvocationを進める。

1ターンの最小ケースでは、

```text
User message
    ↓
User Event
    ↓
Agent execution
    ↓
Agent response Event
```

となる。

実際の観察では、実行前のSessionは、

```text
Events: 0
```

だった。

1ターン実行後は、

```text
Events: 2
```

になった。

保存されていたのは、

```text
Event 0: author=user
Event 1: author=study_agent
```

の2つ。

一方、

```python
async for event in runner.run_async(...):
```

で呼び出し元に見えたのはAgent側のresponse Eventだった。

これはRunnerが、User messageをまずSessionへEventとして保存したうえでAgentを実行し、AgentからyieldされたEventを保存しながら上流にもyieldするため。

## 6. `run_async()` はEvent streamを返す

`Runner.run_async()` は「最終回答1個」を返す普通の関数として考えない。

概念的には、

```text
Runner
  ├─ yield Event
  ├─ yield Event
  ├─ yield Event
  └─ ...
```

という非同期Event stream。

最小のLLM応答ではAgent response Event 1個だけでも、Toolを追加すると将来的には、

```text
LLM decision
   ↓
Tool call Event
   ↓
Tool result Event
   ↓
LLM response Event
   ↓
Final Event
```

のように1 Invocation内で複数Eventが流れる。

`event.is_final_response()` は、そのEventがInvocationにおける最終回答かを判定するために使える。

## 7. Multi-turn会話はSessionのEvent historyを使う

2ターン目の入力では、過去のmessageを手動で連結しなかった。

Runnerには、

```text
user_id
session_id
new_message
```

だけを渡した。

それでもAgentは前の質問を参照できた。

理由は、RunnerがSessionServiceから既存Sessionを取得し、そのSessionに保存されたEvent historyを実行コンテキストとして利用するため。

2ターン実行後は、

```text
Event 0: user
Event 1: study_agent
Event 2: user
Event 3: study_agent
```

となり、SessionのEvent数は4になった。

つまりMulti-turnの継続性は、呼び出し側で `messages[]` を毎回組み立てるのではなく、ADK RuntimeとSessionが管理する。

## 8. `InMemorySessionService` は永続化しない

今回利用した `InMemorySessionService` は、Pythonプロセス内にSessionを保持する。

```text
プロセス実行中 → Sessionあり
プロセス終了   → Session消失
```

したがって、これはRuntime構造を学習するための簡易実装。

将来、Session backendを永続化Serviceへ差し替えても、RunnerとSessionServiceを分離して理解していればAgent側の設計を大きく変更せずに済む。

## 9. `App` はAgentシステム全体のトップレベル定義

`App` はroot agentを含む、Agent application全体のトップレベルコンテナ。

```text
App
└─ root_agent
```

さらにADKでは、App-levelのplugin、context management、resumabilityなどの設定もここに載せられる。

Runnerには、

```python
Runner(
    app=app,
    session_service=session_service,
)
```

のようにAppそのものを渡す。

一方SessionにはAppオブジェクトを格納せず、

```text
app.name
```

を `app_name` として渡す。

したがって責務は、

```text
App
  = Agent applicationの定義

Runner
  = Appを実行するRuntime orchestrator

SessionService
  = Sessionの管理・永続化interface

Session
  = 1つの会話スレッド

Event
  = Runtime内で流れる記録・変更・出力の基本単位
```

と整理できる。

## Lesson 0 終了時点のメンタルモデル

最も重要な理解は次の図。

```text
                       Runner
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
             App              SessionService
              │                     │
              ▼                     ▼
         root_agent              Session
              │                 ├─ State
              ▼                 └─ Events
           LlmAgent
              │
              ▼
            Model
```

Runnerは、App側の「実行ロジック」とSessionService側の「会話状態」をつなぎ、Event Loopとして1回のInvocationを進める。

このRuntime骨格を理解した状態で、次からTool CallingなどのAgent機能を追加していく。
