# Lesson 5 — Callback / Lifecycle

## Lesson 5 の目的

ADK の Callback が Agent / Model / Tool の実行経路のどこに入り、何を観察・短絡・置換できるのかを理解する。

そのうえで Lesson 4 では `runner.py` から固定的に行っていた Environment の bind を `before_agent_callback` に移し、**1 Session = 1 Sandbox** の前提で、Session ごとに対応する Environment を選択して `ContextVar` へ bind する流れを実装した。

最終的に確認した実行経路は次の通り。

```text
Runner.run_async()
        ↓
before_agent_callback
        ↓
(user_id, session_id)
        ↓
Environment cache
   ├─ hit  → 既存 Environment
   └─ miss → DockerSandboxProvider
                 ↓
            provision / reattach
                 ↓
            SandboxEnvironment
        ↓
set_active_environment()
        ↓
ContextVar
        ↓
read / write / bash / process
        ↓
after_agent_callback
        ↓
clear_active_environment()
```

## 1. Callback は lifecycle の interception point

ADK の Callback は単なる event listener ではなく、Agent / Model / Tool の lifecycle に介入するための hook である。

主に次の Callback を確認した。

```text
Agent
├─ before_agent_callback
└─ after_agent_callback

Model
├─ before_model_callback
└─ after_model_callback

Tool
├─ before_tool_callback
└─ after_tool_callback
```

Tool Call を1回行う Agent を実行すると、概ね次の順序になった。

```text
before_agent

  before_model
  after_model
  Event: function_call

  before_tool
  Tool body
  after_tool
  Event: function_response

  before_model
  after_model
  Event: final response

after_agent
```

1回の `Runner.run_async()` の中でも、Tool Call が発生すると Model は複数回呼ばれる。

したがって Callback の発火単位は次のように異なる。

```text
Agent callback
= Agent call 単位

Model callback
= LLM call 単位

Tool callback
= Tool execution 単位
```

同じ Agent call の中では `invocation_id` が共通であり、1 invocation の中に複数の Model / Tool step が含まれることも確認した。

## 2. `None` と非 `None` の返却では処理が変わる

Callback は観察するだけでなく、返却値によって通常処理を短絡・置換できる。

基本的には、

```text
return None
→ 通常処理を続行
```

となる。

一方、Callback ごとに定められた型を返すと処理へ介入できる。

```text
before_agent
→ Content を返すと Agent 本体を skip

before_model
→ LlmResponse を返すと LLM call を skip

before_tool
→ dict を返すと Tool 本体を skip

after_model
→ LlmResponse を返すと response を置換

after_tool
→ dict を返すと Tool response を置換
```

「適当な値を返せば skip」ではなく、各 Callback が要求する型を返す必要がある。

この違いから、

```text
before_*
= 実行前に短絡できる地点

after_*
= 実行後の結果へ介入できる地点
```

と理解した。

## 3. Callback function 自体はアプリ側で定義する

ADK は Callback の差し込み口、Context、Model / Tool の入出力型を提供するが、Callback 内で何を行うかはアプリ側で定義する。

`callback.py` のようなファイル名や分離方法は ADK の必須構造ではない。

```text
普通の Python function
        ↓
LlmAgent(
    before_agent_callback=...,
    before_model_callback=...,
    before_tool_callback=...,
)
        ↓
ADK が lifecycle の該当地点で呼び出す
```

今回の最終実装では、Sandbox / Environment の bind 処理を `callback.py` にまとめた。

## 4. Lesson 4 の Environment bind を Callback へ移した

Lesson 4 では `runner.py` が、

```text
Provider
 ↓
Environment
 ↓
initialize
 ↓
set_active_environment
 ↓
Runner.run_async
```

までを直接行っていた。

Lesson 5 ではこの責務を `before_agent_callback` へ移した。

```text
Runner
 ↓
ADK lifecycle
 ↓
before_agent_callback
 ↓
Environment resolve / bind
 ↓
Agent / Tool
```

これにより Runner は「どの Sandbox を使うか」を知らず、実行時の lifecycle に合わせて Environment が選択されるようになった。

## 5. ContextVar は Session storage ではない

`ContextVar` は、Python process 全体で1つの値を共有する通常の module global とは異なり、async execution context ごとに値を分離して保持できる。

LHA の `environment_context.py` では概ね次の形になっている。

```python
_active_env = ContextVar(
    "lha_active_environment",
    default=None,
)


def set_active_environment(env):
    _active_env.set(env)


def active_environment():
    return _active_env.get()
```

概念的には、

```text
Python process
├─ async Task A
│   └─ active Environment = Sandbox A
│
└─ async Task B
    └─ active Environment = Sandbox B
```

となる。

これにより Tool は Environment を引数として受け取らず、

```python
env = active_environment()
```

で現在の実行に対応する Environment を取得できる。

重要なのは、`ContextVar` 自体が「どの Session がどの Sandbox を使うか」を管理するわけではないこと。

```text
Session → Environment の対応
= cache / Provider / callback の責務

現在の invocation で Tool が使う Environment
= ContextVar の責務
```

と分離して考える。

## 6. ContextVar は turn ごとに re-bind する

`ContextVar` は ADK Session に永続保存される値ではない。

別の `asyncio.Task` に移ると、前の turn で設定した値がそのまま利用できるとは限らない。

そのため `before_agent_callback` で毎回、

```text
Session
 ↓
Environment resolve
 ↓
set_active_environment(env)
```

を行う。

LHA の `on_session_start_callback` も名前とは異なり、Environment の bind 部分は各 invocation で実行し直している。

今回の実装でも、

```text
before_agent
→ Environment を ContextVar に bind

after_agent
→ ContextVar を clear
```

とした。

## 7. 1 Session = 1 Sandbox に変更した

現行 LHA の Sandbox lifecycle は基本的に **1 user = 1 Environment / Sandbox** を前提としており、process 内 cache も `user_id` を中心に管理している。

この学習プロジェクトでは以前から、

```text
User
├─ Session A → Sandbox A
└─ Session B → Sandbox B
```

を前提としている。

そのため Lesson 4 の `DockerSandboxProvider` を、

```python
build_environment(user_id)
```

から、

```python
build_environment(user_id, session_id)
```

へ変更した。

Docker container 名も、

```text
study-lha-sandbox-{user_id}-{session_id}
```

とした。

実際に同一 user で `session_001` と `session_002` を作成し、別 Sandbox が provision され、片方の Workspace に作成した `hello.txt` がもう片方からは見えないことを確認した。

## 8. Environment cache と Sandbox persistence は別

`callback.py` では、

```python
_environment_cache[(user_id, session_id)] = environment
```

として process 内で Environment object を再利用する。

ただし、この cache が Sandbox を永続化しているわけではない。

cache が無くても毎 turn、

```text
Provider.build_environment
 ↓
既存 Docker container を発見
 ↓
reattach
 ↓
新しい SandboxEnvironment object
```

とすれば同じ Workspace を再利用できる。

したがって、

```text
Sandbox persistence
= Docker / remote platform + Provider の責務

Environment cache
= process 内の接続 object 再利用
```

である。

## 9. Environment cache は特に remote Sandbox で重要になる

ローカル Docker では cache が無くても機能上は成立するが、cache があると毎 turn の次の処理を避けられる。

```text
Sandbox discovery
port / endpoint resolve
SandboxEnvironment object 作成
httpx.AsyncClient 作成
health check
remote auth / routing 情報取得
```

LHA の remote Sandbox では、Environment object 内部の `httpx.AsyncClient` が HTTP connection pool を保持する。

HTTP request 自体は stateless でも、その下の TCP / TLS connection は keep-alive で再利用できる。

```text
HTTP request
    ↓
httpx.AsyncClient
    ↓
connection pool
    ↓
TCP / TLS connection
```

そのため remote Sandbox では Environment cache の価値が大きい。

LHA はさらに同時 cache miss による二重 provision を避けるため `asyncio.Lock` も持つが、このLessonでは Callback / bind の理解を優先し、そこまでは実装していない。

## 10. Sandbox / Environment / ContextVar の lifetime は異なる

今回整理した lifetime は次の通り。

```text
ContextVar bind
= invocation / async context 単位

Agent before / after callback
= Agent call 単位

Environment object
= process 内 cache で再利用可能

Sandbox
= process を越えて存続可能

ADK Session
= SessionService が管理
```

`after_agent_callback` は Session 終了通知ではなく、1回の Agent call の終了 hook である。

したがって Sandbox や cached Environment を `after_agent` のたびに破棄するのは今回の目的には合わない。

最終コードには process 終了時の `atexit` cleanup も置いたが、今回の `runner.py` は短い script 実行なので、これは中心的な学習対象ではない。

## 11. LHA の `lifecycle.py` と Callback lifecycle は別物

LHA の、

```text
horizon/sandbox/lifecycle.py
```

という名前は、ADK Callback の lifecycle を実装するファイルではない。

ここは Vertex Agent Runtime Sandbox の、

```text
provision
find / reattach
delete
snapshot / restore
template
auth / routing token
```

などを SDK 上で扱う helper 群である。

一方、Environment cache / Provider resolve / ContextVar bind を orchestrate しているのは主に、

```text
horizon/conversation/session_start.py
```

である。

今回の Lesson では `lifecycle.py` という名前を新たに作らず、学習対象である Callback との関係を見やすくするため、Environment bind の処理を `callback.py` に置いた。

## 12. Lesson 5 で分かった責務分離

最終的な責務は次のように整理できる。

```text
Callback
= いつ Environment を選択 / bind するか

Environment cache
= Session に対応する live Environment object を process 内で再利用

Provider
= Sandbox をどう provision / reattach するか

Environment
= Sandbox をどう操作するか

ContextVar
= 今の async execution context からどの Environment を参照するか

Tool
= LLM に見せる操作

Sandbox
= 実際の隔離された実行環境
```

Lesson 4 では個別に理解した Provider / Environment / ContextVar が、Lesson 5 で ADK Runtime lifecycle に接続された。

## 参照

### Google ADK

- Callbacks  
  https://adk.dev/callbacks/

- Types of callbacks  
  https://adk.dev/callbacks/types-of-callbacks/

- Context  
  https://adk.dev/context/

### Long Horizon Harness

- Long Horizon Harness  
  https://github.com/google/adk-recipes/tree/main/core/python/long-horizon-harness

- `horizon/environment_context.py`  
  https://github.com/google/adk-recipes/blob/main/core/python/long-horizon-harness/horizon/environment_context.py

- `horizon/conversation/session_start.py`  
  https://github.com/google/adk-recipes/blob/main/core/python/long-horizon-harness/horizon/conversation/session_start.py

- `horizon/sandbox/provider.py`  
  https://github.com/google/adk-recipes/blob/main/core/python/long-horizon-harness/horizon/sandbox/provider.py

- `horizon/sandbox/lifecycle.py`  
  https://github.com/google/adk-recipes/blob/main/core/python/long-horizon-harness/horizon/sandbox/lifecycle.py

- `horizon/environment/sandbox.py`  
  https://github.com/google/adk-recipes/blob/main/core/python/long-horizon-harness/horizon/environment/sandbox.py
