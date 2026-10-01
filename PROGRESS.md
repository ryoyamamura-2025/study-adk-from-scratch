# Progress

## 現在地

- **Lesson 0: 完了**
- **Lesson 1: 完了**
- **Lesson 2: 完了**
- **Lesson 3: 完了**
- **Lesson 4: 完了**
- **Lesson 5: 完了**
- **Lesson 6: 完了**
- **Lesson 7: 完了**
- Artifact と Workspace の責務を分離し、Agent 自身には Artifact API を公開しない構成を確認済み。
- User attachment を ArtifactService に登録し、新規 input だけを Sandbox の `workspace/input/` へ materialize する経路を実装済み。
- `input / work / output` の Workspace file protocol を System Instruction に定義し、現在の input file を volatile reminder として Model context に追加する構成を確認済み。
- `before_agent / after_agent` で output の `size + mtime` metadata を比較し、変更された最終成果物だけを Artifact version として保存する構成に整理済み。
- Event の `artifact_delta` を使って生成・更新された output Artifact を追跡し、InMemoryArtifactService が消える前に host filesystem へ export する経路を実装済み。
- Skill based processing は Lesson 7 では意図的にスキップし、Artifact ↔ Workspace I/O pipeline の理解にスコープを限定した。

## 次に始めるセクション

**未定**

Lesson 7 までで、Agent / Tool / MCP / Skill / Artifact / Workspace / Sandbox / Callback / Context Management / File I/O pipeline の基礎を一通り接続した。

次の学習テーマは、次セッションで決める。
