from google.adk.plugins.base_plugin import BasePlugin

class WorkspaceIOPlugin(BasePlugin):
    def __init__(self):
        super().__init__(name="workspace_io_plugin")

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
        
        return None

    # async def before_run_callback(self, *, invocation_context):
    #     print("\n[PLUGIN] before_run")
    #     print("  invocation_id:", invocation_context.invocation_id)
    #     print("  session events:", len(invocation_context.session.events))
    #     return None

    # async def before_agent_callback(self, *, agent, callback_context):
    #     print(f"\n[PLUGIN] before_agent ({agent.name})")
    #     return None

    # async def before_model_callback(self, *, callback_context, llm_request):
    #     print("\n[PLUGIN] before_model")
    #     return None

    # async def after_agent_callback(self, *, agent, callback_context):
    #     print(f"\n[PLUGIN] after_agent ({agent.name})")
    #     return None

    # async def after_run_callback(self, *, invocation_context):
    #     print("\n[PLUGIN] after_run")
    #     return None