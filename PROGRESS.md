# Progress

## 現在地

- **Lesson 0: 完了**
- **Lesson 1: 完了**
- **Lesson 2: 完了**
- **Lesson 3: 完了**
- `InMemoryArtifactService` を `Runner` に接続し、Artifact が Session / State とは別の Runtime Service で管理されることを確認済み。
- 通常の Function Tool から `ToolContext` を通して `save_artifact` / `list_artifacts` / `load_artifact` を実行し、Artifact の保存・一覧取得・読み込みを確認済み。
- Artifact の内容は `google.genai.types.Part` として扱い、同名保存時には version が追加されることを確認済み。
- Artifact を操作しても Session State は空のままで、State と Artifact の責務が分離されていることを確認済み。

## 次に始めるセクション

**Lesson 4: Workspace / Sandbox — 未着手**

次のセッションでは、Artifact 連携を前提にせず、Workspace / Sandbox の基礎から開始する。

主な確認対象は、Agent に Workspace を与える方法、Workspace を与えたときに利用可能な Tool や Runtime 構成がどう変わるか、shell / file 操作系 Tool がどこから提供されるか、Sandbox が何を隔離するのか。

その後は、Callback / Lifecycle を独立した Lesson で扱い、さらに後段で Artifact と Workspace の I/O 接続を扱う予定。
