import asyncio
from pathlib import Path

from docker_sandbox_provider import DockerSandboxProvider


async def main():
    provider = DockerSandboxProvider()

    environment, pending = provider.build_environment(
        "user003"
    )

    print("Environment:", type(environment).__name__)
    print("Sandbox:", environment.sandbox_name)
    print("Pending migration:", pending)

    await environment.initialize()

    await environment.write_file(
        Path("provider.txt"),
        "created through DockerSandboxProvider",
    )

    content = await environment.read_file(
        Path("provider.txt")
    )

    print("Content:", content.decode())

    await environment.close()


if __name__ == "__main__":
    asyncio.run(main())