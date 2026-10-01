# Lesson 7 — Artifact ↔ Workspace I/O

## Lesson 7 の目的

Lesson 7 では、ユーザーが添付したファイルを Sandbox Workspace に渡し、Agent が処理し、最終成果物を Artifact として外へ戻すまでのファイル I/O 境界をつないだ。

中心となる考え方は、**Agent に Artifact API を直接触らせず、Agent は Workspace 上のファイルだけを扱う**ことである。

最終的な責務分離は次の通り。

```text
User / UI
   │
   │ attachment
   ▼
ArtifactService
   │
   │ materialize
   ▼
Workspace
├─ input/    User → Agent
├─ work/     Agent internal
└─ output/   Agent → User
   │
   │ changed outputs only
   ▼
ArtifactService
   │
   └─ Host export（学習・確認用）
```

---

## 1. Artifact と Workspace は別の責務

Lesson 3 では Artifact を、Lesson 4 では Workspace / Sandbox を個別に扱った。

Lesson 7 では両者を接続した。

```text
Artifact
= Agent の外側でファイルを受け渡すためのデータ境界

Workspace
= Agent が実際にファイルを読む・書く作業領域
```

Agent にとって重要なのは Artifact の存在ではなく、Workspace 上のファイルである。

そのため Agent の Tool は引き続き、

```text
read
write
bash
process
```

だけとし、`save_artifact()` / `load_artifact()` は Agent Tool として公開しない。

Artifact ↔ Workspace の橋渡しは Harness / Plugin 側の責務とした。

---

## 2. Workspace のファイルプロトコルを決めた

Agent の System Instruction に次の規約を追加した。

```text
input/
  ユーザーから受け取ったファイル
  原則 read-only

work/
  Agent が処理途中に使う中間ファイル・一時ファイル

output/
  ユーザーへ返す最終成果物
```

重要なのは、単なるディレクトリ名ではなく、**Agent と外部のデータ境界を明示したこと**である。

```text
input  = User → Agent
work   = Agent internal
output = Agent → User
```

Agent は Workspace からの相対パスを利用する。

---

## 3. User attachment は inline のまま保持しつつ Artifact にも保存する

`WorkspaceIOPlugin.on_user_message_callback` で、User message の `inline_data` attachment を検出する。

ここで attachment を2つの用途に分けた。

```text
User message の inline_data
→ Model が直接見られる入力として残す

同じ attachment
→ ArtifactService に保存
→ Workspace materialize 用に使う
```

つまり、Artifact に保存したからといって元の `inline_data` を User message から削除しない。

これは ADK 標準の `SaveFilesAsArtifactsPlugin` をそのまま使うのではなく、今回の学習用 I/O protocol に合わせて実装した部分である。

---

## 4. 新しい attachment だけ Workspace に materialize する

Sandbox / Workspace は Session 中残るため、毎 Turn すべての Artifact を `input/` に書き戻す必要はない。

Plugin では `invocation_id` ごとに、その Invocation で新しく追加された attachment の、

```text
(filename, artifact_version)
```

だけを一時的に保持する。

最初の `before_model_callback` で、

```text
Artifact
  ↓ load_artifact
workspace/input/
  ↓ write_file
実ファイル
```

として materialize する。

その後 `pending_inputs` から取り除くため、同じ Invocation 内で Model Call が複数回発生しても再コピーしない。

```text
Turn
  ├─ Model Call #1 → materialize
  ├─ Tool Call
  └─ Model Call #2 → 再materializeしない
```

---

## 5. InvocationContext と CallbackContext の違いを実際に使った

今回、Plugin lifecycle によって context type が異なることを確認した。

`on_user_message_callback` では `InvocationContext` を受け取る。

そのため Artifact 保存は、

```python
invocation_context.artifact_service.save_artifact(...)
```

として直接 ArtifactService を使う。

一方、`before_model_callback` では `CallbackContext` を受け取るため、

```python
await callback_context.load_artifact(...)
```

という callback 向け convenience API を使える。

概念的には次の関係として整理した。

```text
CallbackContext
    ↓ callback向け facade
InvocationContext
    ↓
ArtifactService / Session / App / ...
```

---

## 6. Workspace 上の input を volatile reminder で知らせる

Lesson 6 で学んだ volatile context の考え方をそのまま利用した。

`before_model_callback` で現在の `input/` を確認し、Model request の `contents` 末尾へ、

```text
<system-reminder>
Files from the user are available in the workspace:
- input/sample.jpg
</system-reminder>
```

を synthetic `role="user"` content として追加する。

ここで重要なのは、Workspace file protocol のような**固定ルール**と、現在存在するファイルのような**変動情報**を分けたことである。

```text
System Instruction
= input / work / output の固定ルール

Volatile reminder
= 今 Workspace に存在する input ファイル
```

これにより、volatile な file list を stable system prefix に混ぜない。

---

## 7. text attachment の挙動差も確認した

画像の `inline_data` は Model が利用できた。

一方で `text/plain` を `inline_data` として渡したケースでは、Gemini がその内容を直接利用できない挙動を確認した。

必要なら、

```text
text/* inline_data
→ decode
→ text Part として Model に追加
```

という workaround を入れられるが、Lesson 7 の主題ではないため実装はコメントとして残し、有効化していない。

---

## 8. output/ の全ファイルを毎回 Artifact 化しない

最初の実装では `after_agent` が `output/` の全ファイルを毎 Turn 読み、Artifact として保存していた。

この方式では、変更していないファイルにも毎回新しい Artifact version が付く。

そこで最終実装では、

```text
before_agent
  ↓
output/ の metadata snapshot

Agent execution

after_agent
  ↓
output/ の metadata snapshot

before と after を比較
  ↓
変更されたファイルだけ read_file
  ↓
save_artifact
```

という方式にした。

比較している metadata は、

```text
filename
size
mtime
```

である。

ファイル本体の bytes や SHA を全件計算しないため、変更していない大容量ファイルを毎 Turn 読み込む必要がない。

---

## 9. filesystem watcher は採用しなかった

大量ファイルに対する最適化として Linux の `inotify` / `inotifywait` も検討した。

これは変更されたファイルだけをイベントとして取得できるため、ファイル数が非常に多い場合には効率が良い。

一方、今回の Sandbox では毎 Turn、

```text
background process spawn
watcher ready 待ち
watcher stop
event read
```

という追加 lifecycle が必要になる。

Lesson 7 の学習目的に対して複雑性が大きいため、最終的には採用せず、既存の `list_directory()` が返す metadata の before / after 比較に戻した。

Sandbox runtime の `server.py` 自体も変更しない方針とした。

---

## 10. Artifact version は「output が変わったとき」に進む

同じ output filename を更新すると、`save_artifact()` により Artifact version が増える。

イメージは次の通り。

```text
Turn 1
output/summary.txt 作成
→ summary.txt version 0

Turn 2
output/summary.txt 更新
→ summary.txt version 1

Turn 3
ファイル変更なし
→ save_artifact しない
→ version 1 のまま
```

つまり、Artifact version を「Turn数」ではなく「成果物の変更」と対応させる形にした。

---

## 11. output の削除は検出するが Artifact deletion までは行わない

before / after snapshot の比較では、削除された output file も把握できる。

現在は、

```text
deleted outputs: [...]
```

としてログに出すだけで、ArtifactService 側の過去 Artifact を削除する処理までは実装していない。

Lesson 7 では、

```text
新規 / 更新された成果物を Artifact へ昇格する
```

ところを主題とした。

---

## 12. Host export は Agent の外側で行う

Lesson 7 では `InMemoryArtifactService` を使っているため、Python process が終了すると Artifact は失われる。

そこで E2E確認用に、Runner が最終 Artifact をホスト側の、

```text
lessons/lesson_07/host_output/
```

へ書き出す。

重要なのは、これは Agent Tool ではないこと。

```text
Agent
→ output/ に成果物を書く

Harness
→ output を Artifact 化する

Runner / learning harness
→ Artifact を host_output/ に export
```

Agent の責務と、学習・観察用の host export を分離した。

---

## 13. artifact_delta を使って今回生成された成果物を追跡する

`callback_context.save_artifact()` は、その Event の、

```text
event.actions.artifact_delta
```

へ保存された Artifact version を記録する。

Runner は Event stream を見ながら、この delta を集める。

そのため最終的な host export では、

```text
今回生成・更新された output Artifact
```

だけを対象にできる。

Input attachment の Artifact 保存は `InvocationContext.artifact_service.save_artifact()` を直接呼んでいるため、今回の host export 対象には含めていない。

---

## 14. 最終 E2E scenario

最終 `runner.py` は3 Turn の scenario になっている。

```text
Turn 1
画像 attachment
↓
Artifact
↓
workspace/input/sample.jpg
↓
Agent
↓
output/summary.txt
↓
Artifact version 0

Turn 2
既存 summary.txt を詳しくする
↓
output/summary.txt 更新
↓
Artifact version 1

Turn 3
ファイルを変更しない
↓
metadata差分なし
↓
Artifact保存なし

最後
↓
latest output Artifact
↓
host_output/summary.txt
```

これにより、入力から最終成果物までの責務が一つにつながった。

---

## 15. Skill based processing は Lesson 7 では扱わなかった

当初計画には、Skill を使って、

```text
input
→ work
→ output
```

を処理する Step 8 があった。

ただし、Skill 自体は Lesson 2 / Lesson 6 ですでに扱っており、Artifact ↔ Workspace I/O の理解には必須ではないため、Lesson 7 では意図的にスキップした。

今回のゴールは Skill の再確認ではなく、**Agent file I/O pipeline の完成**に絞った。

---

## 16. Lesson 7 で分かった責務分離

最終的には次のように整理できる。

```text
User / UI
= attachment を送る

WorkspaceIOPlugin
= input attachment を Artifact として登録
= Artifact を workspace/input へ materialize
= Workspace input を volatile reminder として Model に知らせる

Agent
= Workspace 上のファイルだけを読む・処理する
= 中間生成物は work/
= 最終成果物は output/

Agent callback / Harness
= Sandbox lifecycle
= output metadata snapshot
= 変更された output だけ Artifact 化

ArtifactService
= Agent の外側のファイル受け渡し・version管理

Runner
= Session / ArtifactService を接続
= Event stream を観察
= 学習用に output Artifact を host filesystem へ export
```

Lesson 3 の Artifact、Lesson 4 / 5 の Workspace / Sandbox / lifecycle、Lesson 6 の volatile context が、Lesson 7 で一つのファイル I/O pipeline としてつながった。

---

## 17. 現時点の制約・割り切り

Lesson 7 の最終実装では次を割り切っている。

- output change detection は `filename + size + mtime` の metadata 比較。
- 同一秒内に同一sizeで書き換えるなど、metadataが変わらない特殊ケースは理論上見逃しうる。
- 1 directory あたり `list_directory(..., limit=10_000)` とし、それを超えた場合はエラーにする。
- output file deletion は検出のみで Artifact deletion は行わない。
- input file の同名 collision / rename policy は扱わない。
- text attachment の inline_data workaround は有効化していない。
- production 向けの durable ArtifactService / remote object storage は扱わない。

これらは今回の目的である I/O責務の理解とは別の最適化・運用課題として残した。

---

## 参照

### Google ADK

- ADK Artifact documentation  
  https://adk.dev/artifacts/

- Artifact service guide  
  https://github.com/google/adk-python/blob/main/docs/guides/artifacts/artifact_service/index.md

- `BaseArtifactService`  
  https://github.com/google/adk-python/blob/main/src/google/adk/artifacts/base_artifact_service.py

- `InMemoryArtifactService`  
  https://github.com/google/adk-python/blob/main/src/google/adk/artifacts/in_memory_artifact_service.py

- `Context` / `CallbackContext`  
  https://github.com/google/adk-python/blob/main/src/google/adk/agents/context.py

- `SaveFilesAsArtifactsPlugin`  
  https://github.com/google/adk-python/blob/main/src/google/adk/plugins/save_files_as_artifacts_plugin.py

### Long Horizon Harness

- Long Horizon Harness  
  https://github.com/google/adk-recipes/tree/main/core/python/long-horizon-harness

- Sandbox Environment  
  https://github.com/google/adk-recipes/blob/main/core/python/long-horizon-harness/horizon/environment/sandbox.py

- Volatile reminders  
  https://github.com/google/adk-recipes/blob/main/core/python/long-horizon-harness/horizon/conversation/reminders.py
