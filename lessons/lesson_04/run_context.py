import asyncio
from pathlib import Path

from horizon.environment.sandbox import SandboxEnvironment
from horizon.environment_context import (
    active_environment,
    set_active_environment,
)


def create_environment(
    user_id: str,
    port: int,
) -> SandboxEnvironment:
    return SandboxEnvironment(
        client=None,
        sandbox_name=f"study-lha-sandbox-{user_id}",
        lb_host="unused",
        routing_token="local",
        sandbox_token="local",
        owner=user_id,
        base_url=f"http://127.0.0.1:{port}",
    )


async def use_workspace(user_id: str, environment: SandboxEnvironment):
    # このTaskで使うEnvironmentを設定
    set_active_environment(environment)

    await environment.initialize()

    # ↓ ここから先は environment 変数を直接使わない
    env = active_environment()

    print(f"\n=== {user_id} ===")
    print("Environment:", env.sandbox_name)

    await env.write_file(
        Path("user.txt"),
        f"hello from {user_id}",
    )

    # 並行実行が分かりやすいよう少し待つ
    await asyncio.sleep(1)

    content = await env.read_file(Path("user.txt"))

    print("Content:", content.decode())


async def main():
    env1 = create_environment("user001", 18080)
    env2 = create_environment("user002", 18081)

    await asyncio.gather(
        use_workspace("user001", env1),
        use_workspace("user002", env2),
    )

    await env1.close()
    await env2.close()


if __name__ == "__main__":
    asyncio.run(main())