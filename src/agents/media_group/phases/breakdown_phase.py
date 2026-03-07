"""Phase 2: director breakdown."""

from langchain_core.messages import SystemMessage

from src.agents.state.context import get_agent_context, get_phase_context
from src.tools.llm import get_llm
from src.services.prompt.loader import get_agent_prompt
from src.agents.media_group.state import GraphState

from .helpers import (
    TEST_MODE,
    build_multimodal_message,
    extract_text,
    get_project,
    invoke_with_search,
    test_call,
)


def node_director_breakdown(state: GraphState) -> dict:
    """Convert approved script to production instructions."""
    if TEST_MODE:
        return {
            "director_breakdown": test_call("director_breakdown"),
            "current_node": "director_breakdown",
        }

    director_prompt = get_agent_prompt("director")
    project = get_project(state)
    ref_images = state.get("reference_images") or []

    history_ctx = get_agent_context(project, "director")
    phase1_ctx = get_phase_context(project, "phase_1")
    if history_ctx:
        director_prompt += f"\n\n{history_ctx}"
    if phase1_ctx:
        director_prompt += f"\n\n{phase1_ctx}"

    user_text = (
        "用户已通过剧本，请执行导演拆解。\n"
        "将剧本拆解为各部门（美术、声音、分镜）的制作指令。\n"
        "严格按照「导演拆解输出格式」输出，确保足够详细，让各部门拿到后可直接工作。\n\n"
        f"--- 已通过剧本 ---\n{state['current_script']}"
    )
    if ref_images:
        user_text += "\n\n以下附带了参考图片素材，请在拆解中参考图片的视觉风格。"

    messages = [
        SystemMessage(content=director_prompt),
        build_multimodal_message(user_text, ref_images),
    ]

    response = invoke_with_search(get_llm("director"), messages)
    return {
        "director_breakdown": extract_text(response.content),
        "current_node": "director_breakdown",
    }
