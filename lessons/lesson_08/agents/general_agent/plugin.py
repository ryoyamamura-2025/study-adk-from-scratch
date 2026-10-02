import copy
from pathlib import Path

from google.adk.plugins.base_plugin import BasePlugin
from google.genai import types

from .horizon.environment_context import active_environment


class WorkspaceIOPlugin(BasePlugin):
    def __init__(self):
        super().__init__(name="workspace_io_plugin")
        self._pending_inputs = {}

    async def on_user_message_callback(
        self,
        *,
        invocation_context,
        user_message,
    ):
        print("\n[PLUGIN] on_user_message")

        input_names = []

        for i, part in enumerate(
            user_message.parts or []
        ):
            if part.inline_data is None:
                continue

            inline_data = part.inline_data

            filename = (
                inline_data.display_name
                or (
                    "attachment_"
                    f"{invocation_context.invocation_id}_{i}"
                )
            )

            print(
                f"  attachment[{i}]:",
                f"name={filename}",
                f"mime_type={inline_data.mime_type}",
                f"size={len(inline_data.data or b'')} bytes",
            )

            # text/* は Gemini が inline_data を直接読めなかった。
            # 必要になれば、LLM向けには text Part として追加する。
            #
            # if (
            #     inline_data.mime_type
            #     and inline_data.mime_type.startswith("text/")
            # ):
            #     decoded = inline_data.data.decode(
            #         "utf-8",
            #         errors="replace",
            #     )
            #     user_message.parts.append(
            #         types.Part(
            #             text=(
            #                 f"\n[Attached file: {filename}]\n"
            #                 f"{decoded}"
            #             )
            #         )
            #     )

            artifact_service = (
                invocation_context.artifact_service
            )

            if artifact_service is None:
                print(
                    "  artifact service is not configured"
                )
                continue

            # 出力Artifactと名前が衝突しないよう input/ を付ける
            artifact_name = f"input/{Path(filename).name}"

            version = await artifact_service.save_artifact(
                app_name=invocation_context.app_name,
                user_id=invocation_context.user_id,
                session_id=invocation_context.session.id,
                filename=artifact_name,
                artifact=copy.copy(part),
            )

            print(
                f"  saved input artifact: "
                f"{artifact_name} version={version}"
            )

            self._pending_inputs.setdefault(
                invocation_context.invocation_id,
                [],
            ).append(
                (artifact_name, version)
            )

            input_names.append(artifact_name)

        # 添付があったターンのUser messageそのものに残す
        if input_names:
            files = "\n".join(
                f"- {name}"
                for name in input_names
            )

            reminder = (
                "<system-reminder>\n"
                "Attached files are available in the workspace:\n"
                f"{files}\n"
                "</system-reminder>"
            )

            user_message.parts.append(
                types.Part(text=reminder)
            )

        # inline_data は変更しない
        return None

    async def before_agent_callback(
        self,
        *,
        agent,
        callback_context,
    ):
        pending = self._pending_inputs.get(
            callback_context.invocation_id,
            [],
        )

        if not pending:
            return None

        # on_user_message には delta を載せるEventがないので、
        # ここで入力Artifactのdeltaを記録する。
        for artifact_name, version in pending:
            callback_context.actions.artifact_delta[
                artifact_name
            ] = version

        # ADKはstateが変わったときだけEventを作るため、
        # stateも更新してartifact_deltaをEventに載せる。
        callback_context.state[
            "workspace_io:last_inputs"
        ] = dict(pending)

        return None

    async def before_model_callback(
        self,
        *,
        callback_context,
        llm_request,
    ):
        print("\n[PLUGIN] before_model")

        invocation_id = callback_context.invocation_id
        environment = active_environment()
        input_dir = environment.working_dir / "input"

        # このInvocationで新しく添付されたファイルだけ
        # Artifact -> workspace/input にmaterializeする。
        pending = self._pending_inputs.pop(
            invocation_id,
            [],
        )

        if pending:
            await environment.make_dir(input_dir)

        for filename, version in pending:
            artifact = await callback_context.load_artifact(
                filename,
                version,
            )

            if (
                artifact is None
                or artifact.inline_data is None
            ):
                print(
                    f"  failed to load input artifact: "
                    f"{filename} version={version}"
                )
                continue

            safe_name = Path(filename).name
            target = input_dir / safe_name

            await environment.write_file(
                target,
                artifact.inline_data.data,
            )

            print(
                f"  materialized input: "
                f"{safe_name} -> {target}"
            )

        return None
