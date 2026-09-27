import asyncio
from pathlib import Path

from google.adk.environment import LocalEnvironment
from docker_environment import DockerEnvironment
from horizon.environment.sandbox import SandboxEnvironment

ENVIRONMENT = "lha_sandbox"

async def main():
    # Environmentを定義
    # Toolとして渡す execute, read_file は共通。Environment側のクラスの実装で差分を吸収
    if ENVIRONMENT == "docker":
        environment = DockerEnvironment()
    elif ENVIRONMENT == "lha_sandbox":
        environment = SandboxEnvironment(
            client=None,
            sandbox_name="study-lha-sandbox-user001",
            lb_host="unused",
            routing_token="local",
            sandbox_token="local",
            owner="user001",
            base_url="http://127.0.0.1:18080",
        )
    else:
        environment = LocalEnvironment()

    print("=== CREATED ===")
    print("Environment:", type(environment).__name__)
    print("Initialized:", environment.is_initialized)

    print("\n=== BEFORE INITIALIZE ===")
    print("working_dir:", environment.working_dir)

    await environment.initialize()
    print("\n=== INITIALIZED ===")
    print("Initialized:", environment.is_initialized)
    print("Working dir:", environment.working_dir)

    # ファイル書き込み
    await environment.write_file(
        Path("hello.txt"),
        "hello environment",
    )

    # ファイル読み込み
    content = await environment.read_file(
        Path("hello.txt")
    )

    print("\n=== FILE ===")
    print(content.decode("utf-8"))

    # コマンド実行
    result = await environment.execute(
        "pwd && ls -la && cat /etc/os-release"
    )

    print("\n=== EXECUTE ===")
    print("Exit code:", result.exit_code)
    print("Stdout:")
    print(result.stdout)
    print("Stderr:")
    print(result.stderr)

    # コマンド実行 別パターン（Dockerとホスト環境の隔離を確認）
    host_file = Path("/tmp/study_adk_host_only.txt")
    host_file.write_text(
        "this file exists only on host",
        encoding="utf-8",
    )

    print("\n=== HOST FILE FROM ENVIRONMENT ===")

    result = await environment.execute(
        "cat /tmp/study_adk_host_only.txt"
    )

    print("Exit code:", result.exit_code)
    print("Stdout:", result.stdout)
    print("Stderr:", result.stderr)

    if ENVIRONMENT == "lha_sandbox":
        print("\n=== SPAWN PROCESS ===")

        handle = await environment.spawn_process(
            "for i in 1 2 3 4 5; do echo step-$i; sleep 1; done",
            cwd="/workspace",
        )

        print("Handle:", type(handle).__name__)
        print("Session ID:", handle.session_id)
        print("PID:", handle.pid)

        print("\n=== WAIT 2 SEC ===")

        exit_code = await handle.wait(timeout=2)

        print("Exit code:", exit_code)
        print("Running:", handle.is_running)

        print("\n=== PARTIAL OUTPUT ===")

        data, offset, exit_code = await handle.read()

        print(data.decode("utf-8"))
        print("Next offset:", offset)
        print("Exit code:", exit_code)

        print("\n=== PROCESS LIST ===")

        processes = await environment.list_processes()

        for process in processes:
            print(process)

        print("\n=== WAIT UNTIL FINISHED ===")

        exit_code = await handle.wait(timeout=10)

        data, _, _ = await handle.read(offset=offset)

        print("Exit code:", exit_code)
        print("Remaining output:")
        print(data.decode("utf-8"))

    await environment.close()

    print("\n=== CLOSED ===")
    print("Initialized:", environment.is_initialized)


if __name__ == "__main__":
    asyncio.run(main())