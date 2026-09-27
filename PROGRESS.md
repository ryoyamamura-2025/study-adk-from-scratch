# Progress

## 現在地

- **Lesson 0: 完了**
- **Lesson 1: 完了**
- **Lesson 2: 完了**
- **Lesson 3: 完了**
- **Lesson 4: 完了**
- ADK `LocalEnvironment` / `EnvironmentToolset` を動かし、Workspace の path boundary と Sandbox isolation が別物であることを確認済み。
- 独自 `DockerEnvironment` と LHA の `SandboxEnvironment` / runtime を使い、host と隔離された Docker Sandbox 内で file / shell 操作が実行されることを確認済み。
- `Environment lifetime != Sandbox lifetime`、Provider が provision / reattach を Environment から分離すること、`ProcessHandle` による長時間process管理を確認済み。
- LHA の `ContextVar` に Environment をbindし、`active_environment()` を使う `read` / `write` / `bash` / `process` Tool を Agent に接続済み。
- `ProcessRegistry` により、同じ ADK Session の別turnから background process を `list` / `poll` できることを確認済み。

## 次に始めるセクション

**Lesson 5: Callback / Lifecycle — 未着手**

次は、Lesson 4 では固定していた Environment / Sandbox のbindを Runtime lifecycle に接続する。

主な確認対象は、Session State に保持した Sandbox ID から Provider を通して Environment をresolveする流れ、turnごとの `ContextVar` bind、Callback の実行順序と責務、SkillToolset を含む sessionごとの動的bind。

Artifact と Workspace の I/O 接続は、その後の独立した Lesson で扱う予定。
