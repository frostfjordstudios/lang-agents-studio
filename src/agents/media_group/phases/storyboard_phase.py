"""Phase 4: storyboard generation and review."""

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.state.context import get_agent_context
from src.services.compressor.message_compress import compress_messages
from src.services.compressor.state_compress import compress_state_context
from src.tools.llm import get_llm
from src.services.prompt.loader import get_agent_prompt, get_skill_prompt
from src.agents.media_group.state import GraphState

from .helpers import (
    TEST_MODE,
    extract_text,
    get_project,
    invoke_with_search,
    test_call,
)


def node_storyboard(state: GraphState) -> dict:
    """Storyboard artist generates final storyboard prompt."""
    if TEST_MODE:
        return {"final_storyboard": test_call("storyboard"), "current_node": "storyboard"}

    slim = compress_state_context(state, current_phase="storyboard")
    storyboard_prompt = get_agent_prompt("storyboard")
    storyboard_skill = get_skill_prompt("seedance-storyboard")

    system_content = (
        f"{storyboard_prompt}\n\n"
        f"--- SeeDance 2.0 分镜编写规范 ---\n{storyboard_skill}"
    )
    user_text = (
        "请整合以下所有材料，编写完整的分镜提示词。\n\n"
        f"--- 导演拆解 ---\n{slim['director_breakdown']}\n\n"
        f"--- 美术设计方案 ---\n{slim['art_design_content']}\n\n"
        f"--- 声音设计方案 ---\n{slim['voice_design_content']}\n\n"
        f"--- 原始剧本 ---\n{slim['current_script']}"
    )
    if slim.get("director_storyboard_review") and state.get("storyboard_review_count", 0) > 0:
        user_text += f"\n\n--- Director 审核意见（请据此修改） ---\n{slim['director_storyboard_review']}"

    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=user_text),
    ]
    response = invoke_with_search(get_llm("storyboard"), compress_messages(messages))

    return {
        "final_storyboard": extract_text(response.content),
        "current_node": "storyboard",
    }


def node_director_storyboard_review(state: GraphState) -> dict:
    """Director reviews storyboard with 7-dimension scoring."""
    if TEST_MODE:
        count = state.get("storyboard_review_count", 0) + 1
        return {
            "director_storyboard_review": test_call("director_storyboard_review"),
            "storyboard_review_count": count,
            "current_node": "director_storyboard_review",
        }

    slim = compress_state_context(state, current_phase="director_storyboard_review")
    director_prompt = get_agent_prompt("director")
    history_ctx = get_agent_context(get_project(state), "director")
    if history_ctx:
        director_prompt += f"\n\n{history_ctx}"

    review_skill = get_skill_prompt("seedance-prompt-review")
    scoring_skill = get_skill_prompt("production-scoring")
    system_content = (
        f"{director_prompt}\n\n"
        f"--- 提示词审核标准 ---\n{review_skill}\n\n"
        f"--- 七维评分标准 ---\n{scoring_skill}"
    )

    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=(
            "请对以下分镜提示词执行终审。\n"
            "1. 按七维标准打分（节拍密度/画面感/动作链/镜头/光影/情绪/衔接）\n"
            "2. 总分不足8分的，定位具体问题出在哪个环节（美术/声音/分镜）\n"
            "3. 按审核报告格式输出\n\n"
            f"--- 分镜提示词 ---\n{slim['final_storyboard']}\n\n"
            f"--- 导演拆解（对照基准） ---\n{slim['director_breakdown']}\n\n"
            f"--- 原始剧本 ---\n{slim['current_script']}"
        )),
    ]
    response = invoke_with_search(get_llm("director"), compress_messages(messages))
    count = state.get("storyboard_review_count", 0) + 1

    return {
        "director_storyboard_review": extract_text(response.content),
        "storyboard_review_count": count,
        "current_node": "director_storyboard_review",
    }
