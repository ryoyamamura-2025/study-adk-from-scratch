# Progress

## 現在地

- **Lesson 0: 完了**
- **Lesson 1: 完了**
- **Lesson 2: 完了**
- **Lesson 3: 完了**
- **Lesson 4: 完了**
- **Lesson 5: 完了**
- **Lesson 6: 完了**
- `before_model_callback` で `LlmRequest` の `system_instruction` / `contents` / Tool declaration を観察し、Session Events から Model Call ごとの context が再構成されることを確認済み。
- Session State から Runtime Context を注入し、`instruction` / `static_instruction`、固定 context / 動的 context の役割を整理済み。
- Skill catalog の system prompt 注入と `load_skill` による progressive disclosure を確認し、Skill を Context Management の一部として理解済み。
- Long Horizon Harness の context を **static / context / volatile** の3層で整理し、volatile reminder を `contents` 末尾へ注入する構造を確認済み。
- 最小 `IterationPlugin` を作成し、App Plugin → Session State → volatile context の流れを確認済み。raw `session.state` mutation と Event `state_delta` による永続化の違いも確認済み。
- 古い大容量 Tool result のみを Model Context から除く Tool output pruning を実装し、Session history と Model request projection を分けて考えることを確認済み。
- LHA の overflow / spill は Tool 実行時の巨大 output 対策、Tool Prune は古い result の context 削減であり、Compaction はさらに別レイヤーであることを整理済み。

## 次に始めるセクション

**Lesson 7: Artifact ↔ Workspace I/O — 未着手**

次は、ADK Artifact と Sandbox / Workspace を接続し、入力ファイルを Workspace へ展開して Agent が処理し、生成物を Artifact として外へ戻す一連の I/O を学ぶ。

Lesson 4 では意図的に扱わなかった `input / work / output` のような Workspace 上のファイル配置や、Artifact と Workspace の責務境界をここで整理する。
