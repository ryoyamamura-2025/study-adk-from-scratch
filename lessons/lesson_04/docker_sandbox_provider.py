import subprocess

from horizon.environment.sandbox import SandboxEnvironment


class DockerSandboxProvider:
    def __init__(self, image: str = "study-lha-sandbox"):
        self.image = image

    def build_environment(self, user_id: str):
        container_name = f"study-lha-sandbox-{user_id}"

        if self._is_running(container_name):
            print(f"[provider] reattach: {container_name}")
        else:
            self._remove_if_exists(container_name)

            print(f"[provider] provision: {container_name}")

            subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    container_name,
                    "-p",
                    "127.0.0.1::8080",
                    self.image,
                ],
                check=True,
                capture_output=True,
                text=True,
            )

        port = self._get_host_port(container_name)

        environment = SandboxEnvironment(
            client=None,
            sandbox_name=container_name,
            lb_host="unused",
            routing_token="local",
            sandbox_token="local",
            owner=user_id,
            base_url=f"http://127.0.0.1:{port}",
        )

        # Long HorizonのProviderと同じ戻り値形式
        # 2つ目は後でworkspace migrationに使う
        return environment, None

    def _is_running(self, container_name: str) -> bool:
        result = subprocess.run(
            [
                "docker",
                "inspect",
                "-f",
                "{{.State.Running}}",
                container_name,
            ],
            capture_output=True,
            text=True,
        )

        return (
            result.returncode == 0
            and result.stdout.strip() == "true"
        )

    def _remove_if_exists(self, container_name: str) -> None:
        subprocess.run(
            [
                "docker",
                "rm",
                "-f",
                container_name,
            ],
            capture_output=True,
        )

    def _get_host_port(self, container_name: str) -> str:
        result = subprocess.run(
            [
                "docker",
                "inspect",
                "-f",
                '{{(index (index .NetworkSettings.Ports "8080/tcp") 0).HostPort}}',
                container_name,
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        return result.stdout.strip()