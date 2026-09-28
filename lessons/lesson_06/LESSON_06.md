# Lesson 6 — Context Management

## Lesson 6 の目的

Agent が各 Model Call で「何を context として見るか」を理解する。

Lesson 5 では Callback の lifecycle を確認したが、Lesson 6 では `before_model_callback` を単なる hook としてではなく、**Session / State / Skill / Tool result などから、その Model Call に渡す `LlmRequest` を組み立てる地点**として観察した。

最終的に確認した考え方は次の通り。

```text
Session / State / Skill / Tool Results
                ↓
        context assembly
                ↓
          LlmRequest
       ├─ system_instruction
       ├─ contents
       └─ tools
                ↓
              Model
```

Context Management は「履歴を保存すること」そのものではなく、**保存されている履歴・状態から、その瞬間に Model へ見せる context をどう投影するか**という責務として整理した。

---

## 1. まず `LlmRequest` の中身を観察した

`before_model_callback` で次を出力した。

```text
system_instruction
contents
  ├─ role
  ├─ text
  ├─ function_call
  └─ function_response
tools
```

最初の Model Call では、User message が1件だけ `contents` に入っていた。

Tool Call が発生すると、同じ Turn の中で再度 Model Call が行われる。

```text
User
 ↓
Model Call #1
 ↓
function_call
 ↓
Tool
 ↓
function_response
 ↓
Model Call #2
 ↓
final response
```

したがって、

```text
1 Turn = 1 Model Call
```

ではない。

Lesson 5 で Callback の発火単位として確認した内容を、今回は `LlmRequest.contents` の変化として確認できた。

---

## 2. Session Events から Model 用 `contents` が再構成される

Turn 2 の最初の Model Call では、Turn 1 の履歴も `contents` に含まれていた。

概ね次の形になる。

```text
contents
├─ user: Turn 1 input
├─ model: function_call
├─ user: function_response
├─ model: Turn 1 final response
└─ user: Turn 2 input
```

ここで `function_response` が `role="user"` として入ることも確認した。

これは「人間が発話した」という意味ではない。

ADK / Gemini の会話表現上、Tool result が user-side content として表現されているだけである。

したがって、Context を扱うときは、

```text
role=user
```

だけを見て「人間の入力」と判断してはいけない。

今回の Tool Prune でも、最新の本物の User message を探すために、

```text
text を持つ
かつ
function_call / function_response を持たない
```

という条件を使った。

---

## 3. `system_instruction` は ADK によって組み立てられる

Agent に、

```python
instruction="あなたは優秀なアシスタントです"
```

を設定すると、Model に送る `system_instruction` には Agent の instruction だけでなく ADK 側の情報も追加される。

観察した例では、Agent の internal name に関する instruction も追加されていた。

つまり、Agent に設定した文字列がそのまま Model API に送られるのではなく、ADK が Model request を組み立てる。

```text
Agent configuration
      ↓
ADK LLM flow
      ↓
LlmRequest.system_instruction
```

`before_model_callback` は、この組み立て後・Model送信前の request を観察・変更できる。

---

## 4. Session State から Runtime Context を注入した

Session 作成時に、

```python
state={
    "project_name": "study-adk-from-scratch",
}
```

を渡した。

Callback 側では、

```python
project_name = callback_context.state.get("project_name")
```

として読み取り、`system_instruction` に Runtime Context を追加した。

```text
Session State
     ↓
callback_context.state
     ↓
before_model_callback
     ↓
system_instruction
```

重要なのは、Callback 内で State を扱う場合、基本的には、

```python
callback_context.state
```

のような **delta-aware な State interface** を使うことである。

Session の raw dict を直接触ることとは意味が異なる。

---

## 5. State は Event の `state_delta` を通して永続化される

Lesson 6 では Plugin の最小実装も試した。

`before_run_callback` で、

```python
invocation_context.session.state["iteration"] += 1
```

としたところ、同じ invocation 内では値が見えるが、次の Turn で値が増えず再び `1` になった。

原因は `InMemorySessionService` が Session をコピーして Runner に渡していることだった。

```text
SessionService 内の保存 Session
          ↓ copy
InvocationContext.session
          ↓
before_run で raw state を変更
```

このコピーを変更しても、それだけでは保存元 Session に変更が戻らない。

ADK の Session State 更新は Event の、

```text
Event.actions.state_delta
```

を通して SessionService に反映される。

今回の最小 Plugin では、

```python
async def on_event_callback(...):
    event.actions.state_delta["iteration"] = iteration
```

として永続化した。

その結果、

```text
Turn 1 → iteration = 1
Turn 2 → iteration = 2
```

を確認できた。

この経験から、

```text
session.state の raw mutation
≠
persisted Session State update
```

であることを確認した。

---

## 6. `instruction` と `static_instruction`

ADK の `LlmAgent` には、通常の `instruction` に加えて `static_instruction` がある。

役割は次のように整理した。

```text
static_instruction
= Model Call 間で基本的に変化しない固定 context

instruction
= Agent の instruction
  State placeholder や callable により動的にできる
```

`static_instruction` は prompt prefix を安定させ、context caching を使いやすくするための設計である。

ただし、`static_instruction` を設定しただけで明示的な Context Cache が自動的に有効になるわけではない。

明示的な cache は App の `context_cache_config` など別の設定で扱う。

また現行 ADK では `static_instruction` を設定した場合、dynamic な `instruction` は static system prefix とは別の位置に組み立てられる。

この挙動を確認し、固定 context と動的 context を分けて考える理由を理解した。

---

## 7. Skill は Context Management の一部でもある

Lesson 2 で SkillToolset 自体は触ったが、Lesson 6 では **Skill が Model Context にどう見えるか**を確認した。

標準 ADK の `SkillToolset` では、Tool filter により `list_skills` を外した場合、利用可能な Skill catalog が `<available_skills>` として Model instruction に注入される。

今回、

```text
残す
- load_skill
- load_skill_resource

外す
- list_skills
- run_skill_script
```

という Tool surface を試し、Skill catalog が system instruction に入ることを確認した。

その後 Model が必要と判断した Skill だけ、

```text
load_skill
```

で全文を取得する。

```text
最初の Context
  ↓
Skill name / description の catalog
  ↓
Model が必要性を判断
  ↓
load_skill
  ↓
Skill 本文
```

これは Progressive Disclosure になっている。

全 Skill 本文を常に Context に入れず、まず catalog だけを見せ、必要な Skill の詳細だけ後から追加する。

Skill は Agent 能力の拡張であると同時に、**Context量を制御する仕組み**でもある。

---

## 8. LHA の SkillToolset は標準 ADK の仕組みを利用している

Long Horizon Harness の `HorizonSkillToolset` は、標準 ADK の Skill 機構を使いつつ Tool surface を整理している。

主な考え方は次の通り。

```text
Skill catalog
→ system instruction に常時注入

Skill 本文
→ load_skill で必要時だけ取得

Skill resource
→ load_skill(..., resource=...)

Skill script
→ 専用 run_skill_script ではなく bash 側で実行
```

また、User Skill と Built-in Skill の探索や shadowing など Harness 側のルールも追加されている。

Lesson 6 では LHA 実装を丸ごと移植せず、標準 ADK だけで catalog injection と progressive disclosure を確認した。

---

## 9. LHA の Context は `static / context / volatile` の3層で考える

LHA の system prompt 構築を調べると、大きく3層に整理できる。

```text
static tier
    ↓
context tier
    ↓
conversation history
    ↓
volatile tier
```

### static tier

Process / App build 時点でほぼ固定の instruction。

例:

```text
Agent identity
Safety / style
Tool guidance
Skill guidance
Workspace / execution guidance
```

LHA では `build_static_instruction()` がこれを作り、`Agent.static_instruction` に渡す。

### context tier

Project / Workspace に応じて変わるが、同じ Workspace では deterministic に扱える context。

LHA は、

```text
.horizon.md
LHA.md
AGENTS.md
CLAUDE.md
.cursorrules
```

などから優先順位付きで1つを探索し、Project Context として system instruction に追加する。

複数ファイルを全部足すのではなく、first match で1つだけ使い、Context膨張や指示競合を避けている。

### volatile tier

毎 invocation / turn で変わりうる情報。

例:

```text
iteration
last_error
date
environment hint
workspace hint
available secrets
budget warning
```

これらは stable system prefix に混ぜず、`<system-reminder>` として `contents` の末尾に追加する。

---

## 10. Volatile Context は `contents` の末尾に置く

Lesson 6 では最小例として、

```text
<system-reminder>
Iteration: N
</system-reminder>
```

を `contents` の末尾へ追加した。

```python
llm_request.contents.append(
    types.Content(
        role="user",
        parts=[types.Part(text=volatile)],
    )
)
```

これは LHA の `reminders.py` と同じ基本構造である。

ここでも `role="user"` は人間の発話という意味ではなく、Model request 上の synthetic content である。

volatile な情報を stable system prefix に混ぜないことで、毎回変わる情報が固定 prefix を壊すのを避けられる。

```text
stable / cache-eligible prefix
            ↓
        history
            ↓
volatile reminder
```

という並びになる。

---

## 11. Plugin は Agent callback より広い scope を持つ

Context の volatile state を動かすため、最小 `IterationPlugin` を作成した。

ここで Agent / App / Runner / Plugin の責務も整理した。

```text
Agent
= この Agent は何者で、何ができ、どう振る舞うか

App
= root agent と application-wide policy / component の構成

Runner
= Session / Artifact / Memory 等につないで App を実際に実行する runtime

Plugin
= App 内の Agent / Model / Tool / Run lifecycle を横断する処理
```

Agent callback は特定 Agent に紐づく。

一方 Plugin は App / Runner 全体に登録され、Agent tree を横断して lifecycle に介入できる。

```text
Agent callback
= per-Agent behavior

Plugin
= application-wide cross-cutting behavior
```

LHA が Iteration Budget や Guardrail のような機能を Plugin に置く理由もこの責務分離で理解できた。

Lesson 5 の Sandbox attach / bind も、将来的には Environment lifecycle Plugin として切り出せる可能性があるが、Lesson 6 ではそこまでリファクタせず、Plugin の最小理解に留めた。

---

## 12. Plugin → State → Volatile Context の流れを確認した

最小 `IterationPlugin` は、`before_run_callback` で iteration を更新し、`on_event_callback` の `state_delta` で永続化した。

その State を `before_model_callback` が読み、volatile reminder に反映した。

```text
Runner.run_async
      ↓
App Plugin.before_run
      ↓
iteration + 1
      ↓
Agent / before_model
      ↓
callback_context.state
      ↓
<system-reminder>
Iteration: N
</system-reminder>
      ↓
Model
      ↓
Plugin.on_event
      ↓
Event.actions.state_delta
      ↓
SessionService
```

Turn 1 / Turn 2 で、

```text
Iteration: 1
Iteration: 2
```

と変化することを確認した。

これにより LHA の volatile context が単なる固定 prompt ではなく、**Runtime state を次の Model Call へフィードバックする仕組み**であることを理解した。

---

## 13. Tool output pruning は「履歴削除」ではなく Model Context の節約

最後に、大きな Tool result を返す `large_output` Tool を用意した。

```python
def large_output() -> dict:
    return {
        "data": "X" * 5000,
    }
```

Turn 1 では Tool result をそのまま Model に見せる。

Turn 2 では、最新 User message より前にある大きな `function_response` を、

```text
[output pruned to reclaim context]
```

へ置き換えた。

```text
Turn 1
User
 ↓
Tool → large output
 ↓
Model
  ※ 今の Turn なので必要。残す

Turn 2
User
 ↓
before_model
 ↓
古い large Tool result を prune
 ↓
Model
```

大事なのは **同じ Turn の Tool result は prune しない**こと。

Tool実行直後の Model Callでは、その結果を使って推論する必要がある。

次 Turn 以降で古くなった結果だけを対象にした。

---

## 14. LHA の Tool Prune はより実用的な policy を持つ

LHA の `tool_output_pruning.py` では、単純に「古ければ全部削る」のではなく、次を保護する。

```text
直近数 Turn
直近一定 token budget
小さい Tool output
Skill output
Subagent result
Clarify result
```

そして、古くて大きく、十分な context 回収効果がある Tool output だけを prune する。

これは LLM を使わない deterministic な Context 削減である。

```text
Tool Prune
= cheap / deterministic

Compaction
= LLM を使って会話履歴を意味的に圧縮
```

LHA 自身も、Compaction を行う前に Tool output から安く Context を回収する設計になっている。

---

## 15. LHA の overflow と Tool Prune は別のタイミングで働く

LHA の `read` / `bash` / `process` などは、Tool output が大きすぎる場合、Tool 実装側で full output を Workspace 上のファイルへ spill する。

Model に返す FunctionResponse は、

```text
preview
truncated=true
overflow_path
```

のようになる。

これは `after_tool_callback` で全Tool共通に行うのではなく、巨大出力があり得る Tool が共通の output-overflow utility を使う設計である。

その後さらに時間が経ち、Tool Prune の対象になった場合は、preview 本文も削られるが `*_overflow_path` は残す。

```text
Tool execution 時

full output
    ↓
Workspace に spill
    ↓
preview + overflow_path


古くなった後

preview + overflow_path
    ↓ Tool Prune
pruned marker + overflow_path
```

したがって、

```text
overflow
= 今この瞬間に巨大 output 全文を Context に入れない

Tool Prune
= 過去の preview すら Context から落とす
```

という2段階の Context 制御になっている。

必要になれば Agent は `overflow_path` を使って一部だけ再読できる。

全文を毎回再読するのであれば Context節約効果は小さいため、offset / limit / search 等で必要部分だけ再取得することが前提となる。

---

## 16. Context Management と History Management は分けて考える

Lesson 6 で最も重要な整理は次である。

```text
Session Events / State
= source of truth

        ↓

Context Management
= 今回の Model Call に何を見せるか

        ↓

LlmRequest
```

例えば、

```text
Skill catalog injection
volatile reminder
Tool output pruning
Project Context injection
```

はすべて「今回 Model に見せるもの」の調整である。

一方で、会話履歴自体を要約・圧縮する `EventsCompactionConfig` は別テーマである。

Lesson 6 では Context projection を理解するため、Event Compaction は扱わなかった。

---

## 17. Lesson 6 で確認した LHA との対応

今回の学習内容と LHA の主な実装は次のように対応する。

```text
Lesson 6                      Long Horizon Harness

static_instruction        →  build_static_instruction()
Project Context           →  system_prompt_assembly_callback
Skill catalog             →  HorizonSkillToolset
volatile reminder         →  reminder_injection_callback
iteration state           →  IterationBudgetPlugin
old Tool output           →  prune_tool_outputs_callback
large Tool output         →  output overflow / spill
```

Lesson 4 / 5 で Sandbox と Runtime lifecycle を理解し、Lesson 6 で「その Runtime から得られる情報を Model Context にどう見せるか」がつながった。

---

## 18. Lesson 6 で分かった責務分離

最終的には次のように整理できる。

```text
Session / Event
= 会話と State の source of truth

Agent
= instruction / tools / skill / behavior

App
= root agent + application-wide configuration / plugins

Plugin
= Runtime 全体を横断する policy / lifecycle behavior

before_model_callback
= Model Call直前の Context assembly / projection point

Skill
= 必要な instruction を progressive disclosure する仕組み

Tool Prune
= 古い大容量 Tool result を Model Context から除く

Overflow
= 巨大 Tool output 本体を Workspace 側へ逃がす

Compaction
= 会話履歴そのものを意味的に圧縮する別レイヤー
```

Context Management は単一機能ではなく、これらを組み合わせて「Model に必要十分な情報だけを渡す」設計である。

---

## 参照

### Google ADK

- ADK Python repository  
  https://github.com/google/adk-python

- `LlmAgent`  
  https://github.com/google/adk-python/blob/main/src/google/adk/agents/llm_agent.py

- `Context` / `CallbackContext`  
  https://github.com/google/adk-python/blob/main/src/google/adk/agents/context.py

- `App`  
  https://github.com/google/adk-python/blob/main/src/google/adk/apps/app.py

- `BasePlugin`  
  https://github.com/google/adk-python/blob/main/src/google/adk/plugins/base_plugin.py

- `Runner`  
  https://github.com/google/adk-python/blob/main/src/google/adk/runners.py

- `SkillToolset`  
  https://github.com/google/adk-python/blob/main/src/google/adk/tools/skill_toolset.py

- `InMemorySessionService`  
  https://github.com/google/adk-python/blob/main/src/google/adk/sessions/in_memory_session_service.py

### Long Horizon Harness

- Long Horizon Harness  
  https://github.com/google/adk-recipes/tree/main/core/python/long-horizon-harness

- `horizon/conversation/system_prompt.py`  
  https://github.com/google/adk-recipes/blob/main/core/python/long-horizon-harness/horizon/conversation/system_prompt.py

- `horizon/conversation/reminders.py`  
  https://github.com/google/adk-recipes/blob/main/core/python/long-horizon-harness/horizon/conversation/reminders.py

- `horizon/conversation/iteration_budget_plugin.py`  
  https://github.com/google/adk-recipes/blob/main/core/python/long-horizon-harness/horizon/conversation/iteration_budget_plugin.py

- `horizon/context/tool_output_pruning.py`  
  https://github.com/google/adk-recipes/blob/main/core/python/long-horizon-harness/horizon/context/tool_output_pruning.py

- `horizon/tools/_output_overflow.py`  
  https://github.com/google/adk-recipes/blob/main/core/python/long-horizon-harness/horizon/tools/_output_overflow.py

- `horizon/tools/file_ops.py`  
  https://github.com/google/adk-recipes/blob/main/core/python/long-horizon-harness/horizon/tools/file_ops.py
