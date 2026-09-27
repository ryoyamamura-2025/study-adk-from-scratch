import asyncio
import posixpath
from pathlib import Path

from google.adk.environment import BaseEnvironment, ExecutionResult


class DockerEnvironment(BaseEnvironment):
    def __init__(
        self,
        container_name: str = "study-adk-lesson4",
        image: str = "python:3.13-slim",
    ):
        self.container_name = container_name
        self.image = image
        self._working_dir = Path("/workspace")
        self._is_initialized = False

    @property
    def working_dir(self) -> Path:
        return self._working_dir

    async def initialize(self) -> None:
        # 既存コンテナがある場合は再利用。ない場合は作成
        exit_code, stdout, _ = await self._run_docker(
            "inspect",
            "-f",
            "{{.State.Running}}",
            self.container_name,
        )

        if exit_code == 0 and stdout.decode().strip() == "true":
            print("Reattach existing container")
            self._is_initialized = True
            return

        exit_code, _, stderr = await self._run_docker(
            "run",
            "-d",
            "--rm",
            "--name",
            self.container_name,
            "-w",
            str(self.working_dir),
            self.image,
            "sleep",
            "infinity",
        )

        if exit_code != 0:
            raise RuntimeError(stderr.decode("utf-8"))

        print("Created new container")
        self._is_initialized = True

        # 以下はコンテナを close で完全に消す設定
        # # 前回異常終了したcontainerが残っていても再実行できるよう削除
        # await self._run_docker(
        #     "rm",
        #     "-f",
        #     self.container_name,
        # )

        # exit_code, stdout, stderr = await self._run_docker(
        #     "run",
        #     "-d",
        #     "--rm",
        #     "--name",
        #     self.container_name,
        #     "-w",
        #     str(self.working_dir),
        #     self.image,
        #     "sleep",
        #     "infinity",
        # )

        # if exit_code != 0:
        #     raise RuntimeError(stderr.decode("utf-8"))

        # self._is_initialized = True

    async def close(self) -> None:
        # close でコンテナを削除↓
        # await self._run_docker(
        #     "rm",
        #     "-f",
        #     self.container_name,
        # )

        self._is_initialized = False

    # closeとは別にコンテナを完全に消す関数を独自で実装（runnerがcloseしてもコンテナは残る）
    async def delete(self) -> None:
        await self._run_docker(
            "rm",
            "-f",
            self.container_name,
        )

        self._is_initialized = False

    async def execute(
        self,
        command: str,
        *,
        timeout: float | None = None,
    ) -> ExecutionResult:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "exec",
            "-w",
            str(self.working_dir),
            self.container_name,
            "sh",
            "-c",
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()

            return ExecutionResult(
                exit_code=124,
                timed_out=True,
            )

        return ExecutionResult(
            exit_code=proc.returncode or 0,
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
        )

    async def read_file(self, path: str | Path) -> bytes:
        path = self._resolve_path(path)

        exit_code, stdout, stderr = await self._run_docker(
            "exec",
            self.container_name,
            "python",
            "-c",
            (
                "from pathlib import Path; "
                "import sys; "
                "sys.stdout.buffer.write(Path(sys.argv[1]).read_bytes())"
            ),
            str(path),
        )

        if exit_code != 0:
            raise FileNotFoundError(
                stderr.decode("utf-8", errors="replace")
            )

        return stdout

    async def write_file(
        self,
        path: str | Path,
        content: str | bytes,
    ) -> None:
        path = self._resolve_path(path)

        if isinstance(content, str):
            content = content.encode("utf-8")

        exit_code, _, stderr = await self._run_docker(
            "exec",
            "-i",
            self.container_name,
            "python",
            "-c",
            (
                "from pathlib import Path; "
                "import sys; "
                "p = Path(sys.argv[1]); "
                "p.parent.mkdir(parents=True, exist_ok=True); "
                "p.write_bytes(sys.stdin.buffer.read())"
            ),
            str(path),
            input_data=content,
        )

        if exit_code != 0:
            raise RuntimeError(
                stderr.decode("utf-8", errors="replace")
            )

    def _resolve_path(self, path: str | Path) -> Path:
        candidate = Path(path)

        if candidate.is_absolute():
            resolved = candidate
        else:
            resolved = self.working_dir / candidate

        normalized = Path(
            posixpath.normpath(str(resolved))
        )

        if (
            normalized != self.working_dir
            and self.working_dir not in normalized.parents
        ):
            raise ValueError(
                f"Path escapes working directory: {path}"
            )

        return normalized

    async def _run_docker(
        self,
        *args: str,
        input_data: bytes | None = None,
    ) -> tuple[int, bytes, bytes]:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            *args,
            stdin=(
                asyncio.subprocess.PIPE
                if input_data is not None
                else None
            ),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await proc.communicate(
            input=input_data
        )

        return proc.returncode or 0, stdout, stderr