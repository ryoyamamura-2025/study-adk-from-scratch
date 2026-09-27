# Lesson 4 — Environment / Workspace / Sandbox

## Lesson 4 の目的

ADK の `Environment` を起点に、Agent がファイルやshellを操作する場所と、その実行場所を隔離する Sandbox の違いを理解する。

このLessonでは、まず ADK 標準の `LocalEnvironment` / `EnvironmentToolset` を動かし、その後に Docker を使った独自 Environment、Long Horizon Harness（LHA）の `SandboxEnvironment` / runtime / `ProcessHandle` / `ContextVar` / Provider を段階的に確認した。

最後は LHA と同じ考え方で、Environment を Tool に固定で埋め込まず `active_environment()` から取得する `read` / `write` / `bash` / `process` Tool を Agent に登録し、Docker Sandbox 内の Workspace を複数turnにわたって操作した。

最終的に確認した実行経路は次の通り。

```text
DockerSandboxProvider
        ↓
SandboxEnvironment
        ↓
set_active_environment()
        ↓
ContextVar
        ↓
read / write / bash / process
        ↓
LlmAgent
        ↓
Runner
        ↓
LHA runtime (FastAPI)
        ↓
Docker Sandbox
        ↓
/workspace
```

## 1. Environment は Agent の実行場所を抽象化する

ADK の `BaseEnvironment` は、Agent / Tool から実行場所の実装を隠すための抽象化である。

主な interface は次の通り。

```text
Environment
├─ working_dir
├─ initialize()
├─ close()
├─ execute()
├─ read_file()
└─ write_file()
```

Tool 側は「ローカルprocessなのか」「remote sandboxなのか」を直接知る必要がなく、Environment interface を通して操作できる。

```text
Tool
 ↓
Environment interface
 ↓
Local / Docker / Remote Sandbox
```

この indirection により、同じ上位ロジックから実行backendを差し替えられる。

## 2. LocalEnvironment で Workspace の基本を確認した

最初に ADK 標準の `LocalEnvironment` を直接操作した。

`working_dir` を指定しない場合は一時ディレクトリが作られ、`initialize()` 後に file read / write / shell execute が可能になる。

今回確認した基本操作は次の通り。

```text
initialize
 ↓
write_file
 ↓
read_file
 ↓
execute
 ↓
close
```

自動生成された一時 Workspace は `close()` 後に削除された。

一方、明示的な `working_dir` を指定した場合は、そのディレクトリ自体は `close()` 後も残った。

### file API と execute の境界は同じではない

明示的な Workspace で、次を試した。

```text
read_file("../outside")
→ ValueError: Path escapes working directory
```

一方、

```text
execute("cat ../outside")
→ 読める
```

となった。

したがって、今回の `LocalEnvironment` では、

```text
read_file / write_file
= Workspace path の境界を持つ

execute
= host shell process を実行する
```

という違いがあった。

ここから、**Workspace の path boundary と OS / process の isolation は別物**だと分かった。

## 3. Workspace と Sandbox は同じものではない

このLessonで最も重要だった区別の1つ。

```text
Workspace
= Agent が作業対象として扱う file / directory の領域

Sandbox
= process / filesystem / network などの実行環境を隔離する仕組み
```

`LocalEnvironment` に `working_dir` があっても、その `execute()` は host 上で動く。

つまり、

```text
Workspace boundary
≠
Sandbox boundary
```

である。

## 4. 独自 DockerEnvironment で isolation を確認した

次に `BaseEnvironment` を継承した学習用 `DockerEnvironment` を作成した。

主な構成は次の通り。

```text
DockerEnvironment
├─ initialize
│  ├─ docker run
│  └─ 既存containerへreattach
├─ execute
│  └─ docker exec
├─ read_file
├─ write_file
├─ close
└─ delete
```

Host にだけ作った、

```text
/tmp/study_adk_host_only.txt
```

を `LocalEnvironment.execute()` からは読めたが、`DockerEnvironment.execute()` からは読めなかった。

```text
Local execute
→ host process / host filesystem

Docker execute
→ container process / container filesystem
```

これにより Sandbox isolation を実際に確認できた。

## 5. Environment lifetime と Sandbox lifetime は別

独自 DockerEnvironment では、`close()` で container を削除せず、明示的な `delete()` を分けた。

```text
Environment.close()
→ client / connection を閉じる

Sandbox delete
→ 実行環境そのものを削除する
```

同じ container に再接続すると、以前作成した file が残っていた。

この区別は LHA の `SandboxEnvironment` にも共通しており、`close()` は local HTTP client を閉じるだけで、remote Sandbox 自体の lifetime とは別に扱われる。

したがって、

```text
Environment lifetime
≠
Sandbox lifetime
```

と理解した。

## 6. LHA の Environment は ADK Environment を拡張している

LHA の `Environment` は ADK の `BaseEnvironment` を土台にしつつ、Long Horizon な Agent に必要な操作を追加している。

主な追加能力は次の通り。

```text
file / directory
├─ list_directory
├─ delete_file
├─ make_dir
├─ download_zip
└─ upload_zip

process
├─ spawn_process
├─ list_processes
└─ kill_process

other
├─ refresh_auth
└─ cache_identity
```

特に `spawn_process()` と `ProcessHandle` によって、1回の Tool Call より長く動くprocessを扱えるようになっている。

## 7. LHA Sandbox は client と runtime に分かれる

LHA の `SandboxEnvironment` は、Sandbox の中で直接処理するclassではない。

構造は次の通り。

```text
SandboxEnvironment
   ↓ HTTP
Sandbox runtime (FastAPI)
   ↓
Sandbox OS / filesystem / process
```

LHA runtime には file / exec / process 用の endpoint があり、SandboxEnvironment はそれらへ HTTP request を送る。

本番の LHA は Agent Runtime Sandbox の load balancer を経由するが、このLessonでは同じ runtime を Docker container で起動し、`SandboxEnvironment` に `base_url` を追加して localhost へ接続した。

```text
LHA production
SandboxEnvironment
 ↓ HTTPS / Vertex LB
Agent Runtime Sandbox
 ↓
LHA runtime

Lesson 4
SandboxEnvironment
 ↓ HTTP localhost
Docker container
 ↓
同じ LHA runtime
```

これにより、remote Sandbox 用の client / runtime protocol をほぼそのままローカルで確認できた。

## 8. Provider は Sandbox の provision / reattach を Environment から分離する

LHA では Sandbox の作成や再接続を `SandboxProvider` に分離している。

概念的には、

```text
Provider
= どのSandboxを使うか、どう作るか

Environment
= そのSandboxをどう操作するか

Runtime
= Sandbox内で操作をどう実行するか

Sandbox
= 実際の隔離された実行環境
```

となる。

このLessonでは `DockerSandboxProvider` を作り、

```text
user_id
 ↓
既存 Docker container を確認
 ├─ running → reattach
 └─ 無い    → provision
 ↓
Host port を取得
 ↓
SandboxEnvironment を生成
```

とした。

Provider 自体はLesson専用の考え方ではなく、本番では `VertexSandboxProvider` のような別 backend に差し替えられる層である。

## 9. ProcessHandle で長時間processを扱える

LHA の `spawn_process()` は `ProcessHandle` を返す。

`ProcessHandle` には、

```text
session_id
pid
command
is_running
exit_code
output_size

read()
write()
wait()
kill()
```

などがある。

例えば、

```python
exit_code = await handle.wait(timeout=2)
```

は最大2秒だけ終了を待つ。

- 2秒以内に終了 → exit code
- まだ実行中 → `None`

終了したかどうかだけなら `wait()` / `exit_code` で判断でき、stdout を確認したい場合に `read()` を使う。

この仕組みにより、Agent は長時間processを1回の Tool Call で待ち続ける必要がない。

## 10. ContextVar は Tool と Environment を late binding する

LHA は Tool に Environment object を固定で埋め込まず、`ContextVar` に現在の Environment をbindする。

```text
set_active_environment(env)
        ↓
ContextVar
        ↓
active_environment()
        ↓
Tool
```

例えば Tool 側は、

```python
env = active_environment()
```

だけで現在の Environment を取得する。

これにより Tool の引数 schema に Environment / Sandbox ID を含める必要がない。

```text
LLM が見る引数
→ path / command など

Runtime dependency
→ Environment は ContextVar から取得
```

これは Tool の汎用性を保つための runtime dependency injection と考えられる。

このLessonでは Callback をまだ扱わないため、`runner.py` で固定 Sandbox を1回だけ、

```python
set_active_environment(environment)
```

してから Runner を実行した。

Sessionごと / turnごとに動的に Environment をbindする仕組みは後続の Callback / Lifecycle Lessonで扱う。

## 11. EnvironmentToolset を最終構成では使わなかった理由

ADK 標準の `EnvironmentToolset` は、生成時に1つの Environment を受け取り、その Environment にbindされた file / execute Tool を提供する。

```text
EnvironmentToolset
 ↓
固定 Environment
```

固定 Environment だけを使う今回の最小構成なら技術的には利用できる。

しかし、最終的に想定している、

```text
Session A → Sandbox A
Session B → Sandbox B
```

のような構成では、Tool側が実行時に Environment を選べる方が扱いやすい。

LHA も `EnvironmentToolset` ではなく、`active_environment()` を参照する独自 Tool を Agent に登録している。

このLessonでも LHA の設計を理解するため、最終構成では同じ方式を採用した。

## 12. Environment API と Agent Tool は1:1ではない

Environment が提供する primitive operation と、LLM に見せる Tool は別レイヤーである。

```text
Environment API
= backend capability

Agent Tool
= model-facing operation / UX
```

例えば LHA の `bash` は `Environment.execute()` をそのまま公開しているわけではない。

```text
bash
 ↓
active_environment()
 ↓
spawn_process()
 ↓
ProcessHandle.wait()
 ↓
ProcessHandle.read()
```

という組み合わせになっている。

このLessonでは LHA production Tool の permission / secrets / Artifact / output overflow / workspace window などは持ち込まず、Environmentとの接続構造を残した `read` / `write` / `bash` / `process` を作成した。

## 13. bash は foreground-first の shell Tool

今回の `bash` は、最初にprocessを起動して一定時間 foreground で待つ。

```text
bash(command)
 ↓
spawn_process
 ↓
wait(timeout)
 ├─ 終了 → stdout / exit_code を返す
 └─ 継続 → ProcessRegistryへ登録
             ↓
           background process化
```

重要なのは timeout 時にprocessをkillしないこと。

長時間かかる処理は background へ昇格し、その後 `process` Tool から継続操作できる。

短い shell command を普通の Tool として扱いつつ、長時間処理にも自然につなげられる設計になっている。

## 14. process は background process manager

今回の `process` Tool は次の action を持つ。

```text
spawn
list
poll
log
wait
kill
write
```

`spawn` は最初から background process として起動し、`ProcessHandle` を registry へ登録してすぐ Agent に制御を返す。

```text
process(spawn)
 ↓
Environment.spawn_process
 ↓
ProcessHandle
 ↓
ProcessRegistry.register
 ↓
即 return
```

`poll` / `log` / `wait` / `kill` / `write` は registry から対象 Handle を取得して操作する。

`write` では background process の stdin に文字列を送ることもできる。

## 15. ProcessRegistry は ADK Session 単位で Handle を保持する

LHA の `ProcessRegistry` は `ProcessHandle` を Session State に保存しない。

`ProcessHandle` は live Python object で JSON serializable ではないため、module-level store を ADK `session_id` でkeyingして保持する。

```text
_SESSION_REGISTRIES
├─ session_001
│  └─ ProcessRegistry
│     ├─ proc_xxx
│     └─ proc_yyy
└─ session_002
   └─ ProcessRegistry
```

そのため同じ Python process 内であれば、別turnになっても同じ ADK Session から Handle を再取得できる。

一方これは永続Stateではないため、application process 自体が再起動した場合まで Handle object が残るわけではない。

## 16. Agent / Runner まで接続した最終確認

最終的な Agent には次の4 Toolを登録した。

```text
read
write
bash
process
```

Environment object や `EnvironmentToolset` は Agent に直接渡していない。

```text
Agent
├─ read
├─ write
├─ bash
└─ process
      ↓
active_environment()
      ↓
SandboxEnvironment
```

最終確認では Gemini 3.5 Flash を使用し、4turnを実行した。

### Turn 1 — file I/O

```text
write("hello.txt", "hello from sandbox")
 ↓
read("hello.txt")
 ↓
hello from sandbox
```

Sandbox内 `/workspace/hello.txt` の作成と読み込みを確認した。

### Turn 2 — foreground shell

```text
bash("pwd && ls -la")
```

結果は、

```text
/workspace
...
hello.txt
```

となり、shellも host ではなく Docker Sandbox の Workspace 上で実行されていることを確認した。

### Turn 3 — background process

```text
process(
    action="spawn",
    command="python ... time.sleep(10) ..."
)
```

から、

```text
session_id = proc_...
pid = ...
status = running
```

が即返った。

### Turn 4 — turnを跨いだprocess操作

別の `Runner.run_async()` で、

```text
process(action="list")
 ↓
前turnのprocessを発見
 ↓
process(action="poll")
 ↓
output = start
status = running
```

まで確認した。

これにより、

```text
ADK Session
+
ProcessRegistry
+
Sandbox ProcessHandle
```

が複数turnにわたって連携することを確認できた。

## 17. LHA由来コードとLesson側コードを分離した

今回のディレクトリでは、LHAからほぼそのまま持ってきた基盤コードを `horizon/` 配下に置き、Lesson側で作ったコードを外に分離した。

```text
lesson_04/
├─ horizon/
│  ├─ environment/
│  ├─ environment_context.py
│  └─ sandbox/runtime/
│
├─ tools/
├─ docker_sandbox_provider.py
├─ agent.py
└─ runner.py
```

`horizon/` は LHA の Environment / Sandbox / Process / runtime の実装を読むための基盤、`tools/` と Provider / Agent / Runner は、それらをこのLessonでどう接続したかを見るためのコードという位置づけにした。

なお `SandboxEnvironment` は LHA版をベースに、local Docker runtimeへ接続するための `base_url` を追加している。

## 18. Lesson 4 終了時点の責務分担

```text
DockerSandboxProvider
= Sandbox の provision / reattach

SandboxEnvironment
= Sandbox runtime への client interface

LHA runtime
= Sandbox 内で file / shell / process 操作を実行

ContextVar
= 現在の Invocation で使う Environment をbind

read / write
= Agent向け file operation

bash
= foreground-first shell operation

process
= background process manager

ProcessRegistry
= ADK Session 単位で live ProcessHandle を保持

Agent
= Tool の選択

Runner
= Session / Invocation / Tool execution の実行ループ
```

Lesson 4 で得た最も重要な理解は、**Workspace、Environment、Sandbox、Provider、Runtime、Tool はそれぞれ別の責務であり、LHA はそれらを分離したまま ContextVar と Agent Tool で接続している**という点。

また、Environmentを固定でAgent Toolに埋め込むのではなく runtime にlate bindingすることで、後から Sessionごとに異なる Sandbox を割り当てられる構造にできることも理解できた。

## 次に扱うこと

このLessonでは Callback / Lifecycle を意図的に扱わず、固定 Sandbox を Runner 実行前に `set_active_environment()` した。

次の段階では、

```text
Session
 ↓
Sandbox ID / Provider
 ↓
Environment resolve
 ↓
ContextVar bind
 ↓
Skill / Tool
```

を Callback / Lifecycle と組み合わせ、Sessionごと・turnごとに Environment や Skill を動的にbindする仕組みを扱う。

Artifact と Workspace の I/O 接続はその後の独立したテーマとする。

## 実装上の補足

今回コピーした LHA `SandboxEnvironment` は内部で `_initialized` を使っている一方、ADK `BaseEnvironment.is_initialized` は `_is_initialized` を参照するため、`initialize()` 後も `is_initialized` が `False` と表示された。

SandboxEnvironment自体の通信・初期化は成功していたため、このLessonでは LHA 実装を学ぶことを優先し、この差分自体は修正していない。

## 参照した公式ドキュメント・実装

- ADK Python — BaseEnvironment / LocalEnvironment guide  
  https://github.com/google/adk-python/blob/main/docs/guides/environment/base_environment/index.md

- ADK Python — `LocalEnvironment`  
  https://github.com/google/adk-python/blob/main/src/google/adk/environment/_local_environment.py

- ADK Python — `EnvironmentToolset`  
  https://github.com/google/adk-python/blob/main/src/google/adk/tools/environment/_environment_toolset.py

- Long Horizon Harness — `Environment`  
  https://github.com/google/adk-recipes/blob/main/core/python/long-horizon-harness/horizon/environment/base.py

- Long Horizon Harness — `SandboxEnvironment`  
  https://github.com/google/adk-recipes/blob/main/core/python/long-horizon-harness/horizon/environment/sandbox.py

- Long Horizon Harness — `ProcessHandle`  
  https://github.com/google/adk-recipes/blob/main/core/python/long-horizon-harness/horizon/environment/process.py

- Long Horizon Harness — `ProcessRegistry`  
  https://github.com/google/adk-recipes/blob/main/core/python/long-horizon-harness/horizon/environment/registry.py

- Long Horizon Harness — Environment `ContextVar`  
  https://github.com/google/adk-recipes/blob/main/core/python/long-horizon-harness/horizon/environment_context.py

- Long Horizon Harness — `SandboxProvider`  
  https://github.com/google/adk-recipes/blob/main/core/python/long-horizon-harness/horizon/sandbox/provider.py

- Long Horizon Harness — Sandbox runtime server  
  https://github.com/google/adk-recipes/blob/main/core/python/long-horizon-harness/horizon/sandbox/runtime/server.py

- Long Horizon Harness — `bash`  
  https://github.com/google/adk-recipes/blob/main/core/python/long-horizon-harness/horizon/tools/processes/terminal.py

- Long Horizon Harness — `process`  
  https://github.com/google/adk-recipes/blob/main/core/python/long-horizon-harness/horizon/tools/processes/process.py

- Long Horizon Harness — Agent wiring  
  https://github.com/google/adk-recipes/blob/main/core/python/long-horizon-harness/horizon/agent.py
