import atexit
from docker_sandbox_provider import DockerSandboxProvider

from horizon.environment_context import (
    clear_active_environment,
    set_active_environment,
)

provider = DockerSandboxProvider()

_environment_cache = {}

async def _ensure_environment(
    user_id: str,
    session_id: str,
):
    key = (user_id, session_id)

    environment = _environment_cache.get(key)

    if environment is not None:
        print(
            f"[environment] cache hit: "
            f"{user_id}/{session_id}"
        )
        return environment

    print(
        f"[environment] cache miss: "
        f"{user_id}/{session_id}"
    )

    environment, _ = provider.build_environment(
        user_id,
        session_id,
    )

    await environment.initialize()

    _environment_cache[key] = environment

    return environment

async def before_agent(callback_context):
    print("\n[CALLBACK] before_agent")
    session = callback_context.session

    user_id = session.user_id
    session_id = session.id
    print("  user_id:", user_id)
    print("  session_id:", session_id)

    environment = await _ensure_environment(
        user_id,
        session_id,
    )

    set_active_environment(environment)
    print(
        "  environment:",
        environment.sandbox_name,
    )

    return None

async def after_agent(callback_context):
    print("\n[CALLBACK] after_agent")

    clear_active_environment()

    return None

def _close_cached_environments():
    print("\n[environment] process cleanup")

    for key, environment in _environment_cache.items():
        print(
            f"  close: {key} "
            f"-> {environment.sandbox_name}"
        )

        close_sync = getattr(
            environment,
            "close_sync",
            None,
        )

        if close_sync is not None:
            close_sync()

    _environment_cache.clear()


atexit.register(_close_cached_environments)


async def before_model(callback_context, llm_request):
    project_name = callback_context.state.get("project_name")

    runtime_context = (
        "# Runtime Context\n"
        f"project_name: {project_name}"
    )

    existing = llm_request.config.system_instruction or ""

    llm_request.config.system_instruction = (
        f"{existing}\n\n{runtime_context}"
    )

    print("\n[CALLBACK] before_model")

    print("\n--- system_instruction ---")
    print(llm_request.config.system_instruction)

    print("\n--- contents ---")
    print("count:", len(llm_request.contents))

    for i, content in enumerate(llm_request.contents):
        print(f"[{i}] role={content.role}")

        for part in content.parts or []:
            if part.text:
                print("  text:", part.text)

            if part.function_call:
                print("  function_call:", part.function_call)

            if part.function_response:
                print("  function_response:", part.function_response)

    print("\n--- tools ---")
    tools = llm_request.config.tools or []
    print("count:", len(tools))

    for tool in tools:
        for declaration in tool.function_declarations or []:
            print(" ", declaration.name)

    return None