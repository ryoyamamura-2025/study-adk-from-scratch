from google.adk.plugins.base_plugin import BasePlugin

class IterationPlugin(BasePlugin):

    def __init__(self):
        super().__init__(name="iteration_plugin")

    async def before_run_callback(self, *, invocation_context):
        state = invocation_context.session.state
        current = int(state.get("iteration") or 0)
        state["iteration"] = current + 1

        
        print(
            "[PLUGIN] iteration:",
            state["iteration"],
        )

        return None

    async def on_event_callback(
        self,
        *,
        invocation_context,
        event,
    ):
        iteration = invocation_context.session.state.get("iteration")

        event.actions.state_delta["iteration"] = iteration

        return None