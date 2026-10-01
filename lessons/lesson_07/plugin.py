import copy
from pathlib import Path
from google.adk.plugins.base_plugin import BasePlugin
from google.genai import types
from horizon.environment_context import active_environment

class WorkspaceIOPlugin(BasePlugin):
    def __init__(self):
        super().__init__(name="workspace_io_plugin")
        self._pending_inputs = {}

    async def on_user_message_callback(self, *, invocation_context, user_message):
        print("\n[PLUGIN] on_user_message")

        for i, part in enumerate(user_message.parts or []):

            if part.inline_data is None:
                continue
            
            inline_data = part.inline_data

            print(
                f"  attachment[{i}]:",
                f"name={inline_data.display_name}",
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
          
            artifact_service = invocation_context.artifact_service
            
            if artifact_service is None:
                print("  artifact service is not configured")
                continue
            
            filename = (
                inline_data.display_name
                or f"attachment_{invocation_context.invocation_id}_{i}"
            )
            
            version = await artifact_service.save_artifact(
                app_name=invocation_context.app_name,
                user_id=invocation_context.user_id,
                session_id=invocation_context.session.id,
                filename=filename,
                artifact=copy.copy(part),
            )
            
            print(
                f"  saved input artifact: "
                f"{filename} version={version}"
            )

            self._pending_inputs.setdefault(
                invocation_context.invocation_id,
                [],
            ).append(
                (filename, version)
            )

            print(self._pending_inputs)

        # inline_data は変更しない
        return None

    # async def before_run_callback(self, *, invocation_context):
    #     print("\n[PLUGIN] before_run")
    #     print("  invocation_id:", invocation_context.invocation_id)
    #     print("  session events:", len(invocation_context.session.events))
    #     return None

    # async def before_agent_callback(self, *, agent, callback_context):
    #     print(f"\n[PLUGIN] before_agent ({agent.name})")
    #     return None

    async def before_model_callback(self, *, callback_context, llm_request):
        print("\n[PLUGIN] before_model")

        invocation_id = callback_context.invocation_id

        pending = self._pending_inputs.pop(
           invocation_id,
            [],
        )

        if not pending:
            print("マテリアライズするものはない")
            return None

        environment = active_environment()
        input_dir = environment.working_dir / "input"
        await environment.make_dir(input_dir)

        for filename, version in pending:
            artifact = await callback_context.load_artifact(
                filename,
                version,
            )

            if artifact is None or artifact.inline_data is None:
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

    # async def after_agent_callback(self, *, agent, callback_context):
    #     print(f"\n[PLUGIN] after_agent ({agent.name})")
    #     return None

    # async def after_run_callback(self, *, invocation_context):
    #     print("\n[PLUGIN] after_run")
    #     return None