# Progress

## 現在地

- **Lesson 0: 完了**
- 最小ADKアプリをローカルで正常実行できている。
- 同一Sessionで2ターンの会話が成立することを確認済み。
- `App` を明示的に `Runner` へ渡す構成まで到達。
- 開発用LLMへの接続も正常動作済み。

## 次に始めるセクション

**Lesson 1: Tool Calling**

次のセッションでは、最小のFunction Toolを1つ追加するところから開始する。

最初の狙いは、便利な高レベル機能を増やすことではなく、

```text
LLMがTool使用を判断
→ Tool call
→ Tool実行
→ Tool result
→ LLMが最終回答
```

がADKのEvent Loop上でどう見えるかを観察し、Tool Callingの実行経路を理解すること。

Lesson 1は新しいチャットセッションから開始する。
