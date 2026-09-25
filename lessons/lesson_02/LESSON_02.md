# Lesson 2 — Skills と動的Tool追加

## Lesson 2 の目的

ADK の Skill を追加し、必要なときだけ Skill の詳細 instructions と Skill 固有の Tool を利用可能にする仕組みを理解する。

このLessonでは、Lesson 1 で常時 Agent に登録していた Printer MCP を Skill の `additional_tools` 側へ移し、プリンターに関する質問が来たときだけ `list_printers` Tool が利用可能になる構成を作った。

最終的に確認した実行経路は次の通り。

```text
User
 ↓
LLM
 ↓
list_skills
 ↓
Skill の name / description を取得
 ↓
LLM
 ↓
load_skill
 ↓
SKILL.md 本文を取得
+ Skill を Session State で activate
 ↓
SkillToolset
 ↓
adk_additional_tools を解決
 ↓
Printer MCP の list_printers が利用可能になる
 ↓
LLM
 ↓
list_printers
 ↓
MCP tools/call
 ↓
Final Response
```

## 1. Skill は `SKILL.md` を中心に構成される

今回作成した Skill は次の構成。

```text
skills/
└─ printer-management/
   └─ SKILL.md
```

`SKILL.md` には YAML frontmatter と Markdown 本文を記述した。

```yaml
---
name: printer-management
description: Windows PCにインストールされているプリンターを確認するときに使用するSkillです。
metadata:
  adk_additional_tools:
    - list_printers
---
```

本文には、Skill が選択された後に Agent が従う具体的な instructions を記述した。

```text
Windows PCにインストールされているプリンターについて質問された場合は、
list_printers Toolを使用して実際のWindows PCの情報を確認する。
```

今回の構成では、

```text
frontmatter
= Skillを発見・識別するための情報

SKILL.md body
= Skill選択後に読む詳細instructions
```

という役割分担になる。

## 2. `load_skills_from_dir` で Skill を Python オブジェクトとしてロードする

Agent 起動時に `skills/` 配下を読み込み、ADK の `Skill` オブジェクトへ変換した。

```python
skills_dir = Path(__file__).parent / "skills"
skills = load_skills_from_dir(skills_dir)
```

`load_skills_from_dir` には、個別 Skill のディレクトリではなく複数 Skill を格納する親ディレクトリを渡す。

```text
load_skills_from_dir(
    .../skills/
)
        ↓
skills/ 配下の各サブディレクトリを確認
        ↓
printer-management/SKILL.md
```

個別 Skill を1つだけロードする `load_skill_from_dir` とは責務が異なる。

## 3. `SkillToolset` が Skill と Agent Runtime を接続する

ロードした Skill は `SkillToolset` に渡した。

```python
skill_toolset = SkillToolset(
    skills=skills,
    additional_tools=[printer_mcp]
)
```

Agent には Printer MCP を直接登録せず、

```python
tools=[get_weather, skill_toolset]
```

とした。

実際に `root_agent.tools` を表示すると、次の2つだけだった。

```text
get_weather
SkillToolset
```

ここに `list_printers` は存在しない。

つまり今回の構成は、

```text
LlmAgent
├─ get_weather
└─ SkillToolset
    ├─ Skill管理Tool
    ├─ printer-management
    └─ additional_tools
         └─ Printer MCP
              └─ list_printers
```

となる。

Printer MCP はコード上には存在するが、最初から通常の Agent Tool として公開されているわけではない。

## 4. ADK v2.9.2 では Skill の discovery も Tool Calling で行う

今回使用した ADK v2.9.2 の `SkillToolset` は、最初から具体的な Skill 名や description を Model に渡すのではなく、Skill 管理用の Tool を公開する。

主な Tool は次の通り。

```text
list_skills
load_skill
load_skill_resource
run_skill_script
```

プリンターについて質問すると、最初に Model が `list_skills` を選択した。

```text
FunctionCall
name = list_skills
```

その結果として、初めて Model は次の Skill catalog を取得した。

```text
name:
  printer-management

description:
  Windows PCにインストールされているプリンターを確認するときに使用するSkillです。
```

したがって v2.9.2 では、

```text
Model
最初は具体的なSkillを知らない
 ↓
list_skills
 ↓
name / description を知る
```

という discovery になる。

## 5. `list_skills` を呼ぶかどうかは Model が判断する

ADK は `list_skills` という Tool と Skill を扱うための system instruction を Model へ提供する。

しかし、ユーザー入力に対して実際に `list_skills` を呼ぶかどうかは Model の Tool selection である。

プリンター質問では、

```text
今繋がっているプリンターって何がある？
```

に対して Model が、

```text
list_skills
```

を選択した。

一方、

```text
Kobeの天気を教えて
```

では `list_skills` を呼ばず、直接、

```text
get_weather(city="Kobe")
```

を実行した。

したがって、

```text
ADK
= Skillを探す仕組みとToolを提供

LLM
= 今回Skillを探す必要があるか判断
```

という責務分担になる。

## 6. `load_skill` で Skill の詳細 instructions を取得する

`list_skills` の結果から `printer-management` が適切だと判断した Model は、次に、

```text
load_skill(
  skill_name="printer-management"
)
```

を呼び出した。

その FunctionResponse には `SKILL.md` の本文が含まれていた。

```text
instructions:
  Windows PCにインストールされているプリンターについて質問された場合は、
  list_printers Toolを使用して実際のWindows PCの情報を確認する。
```

このため Skill は、すべての詳細 instructions を最初から prompt に入れるのではなく、必要と判断された後に本文を読み込む progressive disclosure の仕組みとして利用できる。

```text
Level 1
name / description
 ↓
Level 2
SKILL.md body
 ↓
Level 3
references / assets / scripts
```

今回のLessonでは Level 2 までを実際に確認した。

## 7. `load_skill` は Skill を Session State で activate する

実行後の Session State を確認すると、次の値が保存されていた。

```text
_adk_activated_skill_study_agent:
  ['printer-management']
```

つまり `load_skill` は単に Markdown を読むだけではない。

```text
load_skill
 ↓
Skill instructions を返す
+
Skillをactive状態としてSession Stateへ記録する
```

という2つの意味を持つ。

この active 状態が、次の動的 Tool 解決に使われる。

## 8. `adk_additional_tools` で Skill 固有Toolを動的に追加できる

`printer-management` の frontmatter には、

```yaml
metadata:
  adk_additional_tools:
    - list_printers
```

を記述した。

一方 `SkillToolset` には候補となる Printer MCP を、

```python
additional_tools=[printer_mcp]
```

として渡した。

Skill が activate されると、`SkillToolset` は Session State を確認し、active Skill の `adk_additional_tools` に指定された Tool 名を `additional_tools` から解決する。

```text
Session State
printer-management = active
       ↓
SKILL.md frontmatter
adk_additional_tools = [list_printers]
       ↓
SkillToolset
       ↓
additional_tools の Printer MCP を確認
       ↓
list_printers を利用可能にする
```

これにより、プリンターと無関係な通常の会話では `list_printers` を Model の Tool 候補へ出さず、Skill が必要になった後だけ利用可能にできる。

## 9. `root_agent.tools` 自体が書き換わるわけではない

Skill activation 後も `root_agent.tools` の定義そのものは、

```text
get_weather
SkillToolset
```

のまま。

`list_printers` が `root_agent.tools` に恒久的に append されるわけではない。

動的 Tool は、概念的には、

```text
SkillToolset.get_tools(context)
 ↓
Session Stateを確認
 ↓
active Skillを確認
 ↓
adk_additional_toolsを解決
 ↓
その時点で利用可能なTool群を返す
```

という形で解決される。

したがって、

```text
Agent Configuration
= get_weather + SkillToolset

Runtime上の利用可能Tool
= Agent Configuration
  + active Skillに応じたdynamic tools
```

と考えると理解しやすい。

## 10. Skill activation 後に初めて Printer MCP が必要になる

プリンター質問では、`load_skill` の後に Printer MCP への接続処理が発生し、その後 `list_printers` が FunctionCall された。

```text
load_skill
 ↓
printer-management active
 ↓
Printer MCPからToolを解決
 ↓
list_printers
 ↓
MCP tools/call
```

一方、天気質問では、

```text
get_weather
 ↓
Final Response
```

だけで終了した。

Session State も空のままで、`printer-management` は activate されなかった。

この negative control により、Printer MCP が `additional_tools` に定義されているだけでは常時利用されず、Skill activation が動的 Tool 利用の条件になっていることを確認できた。

## 11. ADK側の責務とModel側の責務

今回の実行から、Skillに関する責務を次のように整理できる。

```text
ADK / SkillToolset
= Skill管理ToolをModelへ提供
= list_skillsの結果を返す
= load_skillでinstructionsを返す
= Skill activationをSession Stateへ保存
= active Skillに応じてadditional toolsを解決

LLM
= Skillを探す必要があるか判断
= list_skillsを呼ぶか判断
= catalogからどのSkillを選ぶか判断
= load_skillを呼ぶ
= Skill instructionsを読んで次のToolを選ぶ

MCP Toolset
= Skill activation後に必要なMCP Toolを提供
= MCP protocol経由で外部処理を実行
```

最も重要なのは、

```text
ADK
= Skillを遅延発見・遅延ロード・動的Tool解決する仕組み

LLM
= その仕組みをいつ、どのSkillに使うか判断
```

という分担。

## 12. Long Horizon Harness との違いは後で再訪する

今回使用した ADK v2.9.2 では、具体的な Skill catalog は `list_skills` Tool を使って取得する。

一方、Long Horizon Harness では Skill catalog を system prompt 側へ事前に渡す独自の Harness 実装を持っており、Model が最初から利用可能な Skill の概要を知る構成になっている。

また、ADK の main branch では `SkillDiscoveryMode.LAZY / EAGER` が追加されており、`EAGER` では local Skill catalog を system instruction へ注入できる実装が入っている。ただし、この機能は今回使用した v2.9.2 には存在しない。

したがって今回のLessonでは、使用中versionのnative Skill挙動に集中し、

```text
Skill catalogをsystem promptへどう注入するか
Callback / HookでLLM Requestをどう拡張するか
Long Horizon Harnessがどこを自前実装しているか
```

は、今後 Callback / Harness 拡張を扱うLessonで再訪する。

## Lesson 2 終了時点のメンタルモデル

```text
                           LlmAgent
                          /        \
                         ▼          ▼
                 Function Tool   SkillToolset
                  get_weather         │
                                      │
                          ┌───────────┴────────────┐
                          ▼                        ▼
                    Skill management          Skills
                     list_skills                  │
                     load_skill                   ▼
                                      printer-management
                                               │
                                               ▼
                                      Session State
                                          active
                                               │
                                               ▼
                                   adk_additional_tools
                                               │
                                               ▼
                                         Printer MCP
                                               │
                                               ▼
                                         list_printers
                                               │
                                               ▼
                                          MCP Server
```

Lesson 2で得た最も重要な理解は、Skillが単なる「追加prompt」ではなく、必要な instructions と Tool を Runtime 上で段階的に有効化する仕組みであること。

```text
Skill discovery
= 必要なSkillを探す

Skill loading
= 詳細instructionsを読む

Skill activation
= Session上でSkillをactiveにする

Dynamic Tool resolution
= active Skillに必要なToolだけを利用可能にする
```

この仕組みにより、すべてのinstructionsとToolを常時Agentへ載せず、タスクに応じて能力を段階的に追加できる。

## 参照したADK / GitHub

- Google ADK — Skills  
  https://adk.dev/skills/

- Google ADK Python v2.9.2 — `SkillToolset` implementation  
  https://github.com/google/adk-python/blob/v2.9.2/src/google/adk/tools/skill_toolset.py

- Google ADK Python v2.9.2 — Skill loader implementation  
  https://github.com/google/adk-python/blob/v2.9.2/src/google/adk/skills/_utils.py

- Google ADK Python main — current `SkillToolset` implementation  
  https://github.com/google/adk-python/blob/main/src/google/adk/tools/skill_toolset.py

- Google ADK Long Horizon Harness sample  
  https://github.com/google/adk-samples/tree/main/core/python/long-horizon-harness
