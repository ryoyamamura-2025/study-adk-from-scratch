# Progress

## 現在地

- **Lesson 0: 完了**
- **Lesson 1: 完了**
- **Lesson 2: 完了**
- **Lesson 3: 完了**
- **Lesson 4: 完了**
- **Lesson 5: 完了**
- Agent / Model / Tool Callback の発火単位と実行順序を確認し、`None` では通常続行、非 `None` の返却では before 側で short-circuit、after 側で結果へ介入できることを確認済み。
- Lesson 4 で Runner から固定的に行っていた Environment bind を `before_agent_callback` へ移し、Runtime lifecycle に接続済み。
- `(user_id, session_id)` 単位の Environment cache と `DockerSandboxProvider` を使い、**1 Session = 1 Sandbox** の分離を確認済み。
- `before_agent` で Session に対応する Environment を `ContextVar` へ bindし、`read` / `write` / `bash` / `process` Tool が `active_environment()` から利用する流れを確認済み。
- `ContextVar` は Session storage ではなく、現在の async execution context へ runtime dependency を渡す仕組みであり、turn / invocation ごとに re-bind が必要であることを確認済み。
- Sandbox persistence と process 内 Environment cache は別責務であり、cache は特に remote Sandbox で connection reuse / discovery / health check / auth 等のコスト削減に重要であることを整理済み。

## 次に始めるセクション

**Lesson 6: Context Management — 未着手**

次は、Agent が各 Model Call で「何を context として見るか」を扱う。

主な確認対象は、`before_model_callback` を使った system instruction / 動的 context の組み立て、Skill や session情報などの runtime context 注入、不要・古い context の整理、および Long Horizon Harness の context management 実装との比較。

Artifact と Workspace の I/O 接続は、その後の独立した Lesson で扱う予定。
