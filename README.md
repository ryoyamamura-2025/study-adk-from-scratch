# Google Agent Development Kitの勉強用

見るべきファイル  
- [PROJECT_OVERVIEW.md](./PROJECT_OVERVIEW.md): このプロジェクトの概要
- [PROGRESS.md](./PROGRESS.md): 学習進捗（随時更新）

ディレクトリ構造
```text
.
├─ PROJECT_OVERVIEW.md
├─ PROGRESS.md
└─ lessons/
   ├─ lesson_00/   # Agent / Runner / Session / Event
   ├─ lesson_01/   # Tool / MCP
   ├─ lesson_02/   # SkillToolset
   ├─ lesson_03/   # Artifact
   └─ lesson_04/   # Environment / Workspace / Sandbox
      ├─ LESSON_04.md
      ├─ agent.py / runner.py
      ├─ run_environments.py / run_context.py / run_provider.py
      ├─ docker_environment.py
      ├─ docker_sandbox_provider.py
      ├─ tools/
      │  ├─ file_ops.py
      │  └─ processes/{terminal.py, process.py}
      └─ horizon/   # Long Horizon Harness由来の実装
         ├─ environment/{base.py, process.py, registry.py, sandbox.py, sandbox_process.py}
         ├─ environment_context.py
         └─ sandbox/runtime/{Dockerfile, server.py, protocol.py, entrypoint.sh}
```
