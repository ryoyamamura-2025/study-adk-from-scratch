# Progress

## 現在地

- **Lesson 0: 完了**
- **Lesson 1: 完了**
- **Lesson 2: 完了**
- `SkillToolset` を使い、`list_skills → load_skill → Skill activation` の流れを確認済み。
- `adk_additional_tools` により、Skill が activate された後だけ Printer MCP の `list_printers` Tool を利用可能にできることを確認済み。
- Skill activation は Session State の `_adk_activated_skill_study_agent` に保持され、`root_agent.tools` 自体を書き換えずに Runtime 上で Tool が動的解決されることを確認済み。
- 天気質問では `get_weather` に直接進み、Skill activation / Printer MCP 接続が起きない negative control も確認済み。

## 次に始めるセクション

**Lesson 3: 未着手**

次のセッションでは Lesson 3 のテーマ選定から開始する。

プロジェクトの到達イメージ上では、Skills の次段階として Workspace / Artifact / Sandbox を候補とする。

Long Horizon Harness の Skill catalog 事前注入や、ADK main branch の Skill discovery 拡張については、Callback / Harness 拡張を扱うセクションで再訪する。
