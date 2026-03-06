"""Phase 3: production nodes."""

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from src.agents.agent_state import get_agent_context
from src.core.context_optimizer import compress_messages, compress_state_context
from src.core.llm_config import get_llm
from src.core.prompt_manager import get_agent_prompt, get_skill_prompt
from src.core.state import GraphState
from src.services.ai.browser_mcp import browse_web_page
from src.services.ai.search import get_search_tool

from .helpers import (
    TEST_MODE,
    build_multimodal_message,
    extract_text,
    extract_react_final_content,
    get_project,
    invoke_with_search,
    test_call,
)


def node_art_design(state: GraphState) -> dict:
    """Generate art design output from director breakdown."""
    if TEST_MODE:
        return {
            "art_design_content": test_call("art_design"),
            "current_node": "art_design",
        }

    art_prompt = get_agent_prompt("art_design")
    art_skill = get_skill_prompt("art-design")
    ref_images = state.get("reference_images") or []

    system_content = (
        f"{art_prompt}\n\n--- 美术设计技能规范 ---\n{art_skill}"
        "\n\n你拥有联网搜索和网页浏览能力。当你需要查阅美术参考、"
        "风格案例、技术资料时，请主动使用搜索或 browse_web_page 工具。"
    )
    user_text = (
        "请根据导演拆解中的视觉指令，生成完整的美术设计方案和提示词。\n\n"
        f"--- 导演拆解 ---\n{state['director_breakdown']}\n\n"
        f"--- 原始剧本（参考） ---\n{state['current_script']}"
    )
    if ref_images:
        user_text += "\n\n以下附带了参考图片素材，请基于其美术风格制定方案。"
    if state.get("director_production_review") and state.get("production_review_count", 0) > 0:
        user_text += f"\n\n--- Director 审核意见（请据此修改） ---\n{state['director_production_review']}"

    llm = get_llm("art_design")
    search_tool = get_search_tool()
    art_agent = create_react_agent(llm, [search_tool, browse_web_page], prompt=system_content)
    result = art_agent.invoke({"messages": [build_multimodal_message(user_text, ref_images)]})

    return {
        "art_design_content": extract_react_final_content(result["messages"]),
        "current_node": "art_design",
    }


def node_voice_design(state: GraphState) -> dict:
    """Generate voice design output from director breakdown."""
    if TEST_MODE:
        return {
            "voice_design_content": test_call("voice_design"),
            "current_node": "voice_design",
        }

    voice_prompt = get_agent_prompt("voice_design")
    user_text = (
        "请根据导演拆解中的声音指令，生成完整的声音设计方案。\n\n"
        f"--- 导演拆解 ---\n{state['director_breakdown']}\n\n"
        f"--- 原始剧本（参考） ---\n{state['current_script']}"
    )
    if state.get("director_production_review") and state.get("production_review_count", 0) > 0:
        user_text += f"\n\n--- Director 审核意见（请据此修改） ---\n{state['director_production_review']}"

    messages = [
        SystemMessage(content=voice_prompt),
        HumanMessage(content=user_text),
    ]
    response = invoke_with_search(get_llm("voice_design"), messages)

    return {
        "voice_design_content": extract_text(response.content),
        "current_node": "voice_design",
    }


def node_director_production_review(state: GraphState) -> dict:
    """Director reviews art + voice production outputs."""
    if TEST_MODE:
        count = state.get("production_review_count", 0) + 1
        return {
            "director_production_review": test_call("director_production_review"),
            "production_review_count": count,
            "current_node": "director_production_review",
        }

    slim = compress_state_context(state, current_phase="director_production_review")
    director_prompt = get_agent_prompt("director")
    history_ctx = get_agent_context(get_project(state), "director")
    if history_ctx:
        director_prompt += f"\n\n{history_ctx}"

    messages = [
        SystemMessage(content=director_prompt),
        HumanMessage(content=(
            "请审核 Art Design 和 Voice Design 的产出是否忠实于你的拆解指令。\n"
            "分别对美术和声音打分，指出不符合的地方。\n\n"
            f"--- 导演拆解（你的原始指令） ---\n{slim['director_breakdown']}\n\n"
            f"--- 美术设计产出 ---\n{slim['art_design_content']}\n\n"
            f"--- 声音设计产出 ---\n{slim['voice_design_content']}\n\n"
            "请按审核报告格式输出，明确是否通过。"
        )),
    ]
    response = invoke_with_search(get_llm("director"), compress_messages(messages))
    count = state.get("production_review_count", 0) + 1

    return {
        "director_production_review": extract_text(response.content),
        "production_review_count": count,
        "current_node": "director_production_review",
    }


def node_user_gate_production(state: GraphState) -> dict:
    """Pause for user production confirmation."""
    return {"current_node": "user_gate_production"}
