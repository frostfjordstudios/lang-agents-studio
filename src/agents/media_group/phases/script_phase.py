"""Phase 1: script writing and reviews."""

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from src.agents.state.context import get_agent_context
from src.services.compressor.message_compress import compress_messages
from src.services.compressor.state_compress import compress_state_context
from src.tools.llm import get_llm
from src.services.prompt.loader import get_agent_prompt, get_skill_prompt
from src.agents.media_group.state import GraphState
from src.tools.browser import browse_web_page
from src.tools.search import get_search_tool

from .helpers import (
    TEST_MODE,
    build_multimodal_message,
    extract_text,
    get_project,
    invoke_with_search,
    test_call,
    extract_react_final_content,
)


def node_writer(state: GraphState) -> dict:
    """Writer with ReAct tools for search and browsing."""
    if TEST_MODE:
        return {"current_script": test_call("writer"), "current_node": "writer"}

    slim = compress_state_context(state, current_phase="writer")
    writer_prompt = get_agent_prompt("writer")
    writer_prompt += (
        "\n\n你拥有联网搜索能力和网页浏览能力。当你需要查阅真实世界的知识、行业资料、"
        "历史背景、技术细节等信息时，请主动使用搜索工具。"
        "当你需要深入阅读某个网页的具体内容时，使用 browse_web_page 工具。"
        "搜索完成后，将搜索结果融入你的创作中。"
    )

    ref_images = slim.get("reference_images") or []
    ref_text = slim.get("reference_text", "")

    user_text = f"请根据以下需求编写剧本：\n\n{slim['user_request']}\n\n请严格按照剧本格式输出。"
    if ref_text:
        user_text += f"\n\n--- 参考资料 ---\n{ref_text}"
    if ref_images:
        user_text += "\n\n以下附带了参考图片素材，请在创作中融入图片中的视觉元素和风格特征。"

    director_review = slim.get("director_script_review", "")
    showrunner_review = slim.get("showrunner_script_review", "")
    user_feedback = slim.get("user_script_feedback", "")

    if director_review and state.get("script_review_count", 0) > 0:
        feedback_parts = [f"Director 审核意见：\n{director_review}"]
        if showrunner_review:
            feedback_parts.append(f"Showrunner 审核意见：\n{showrunner_review}")
        if user_feedback:
            feedback_parts.append(f"用户反馈：\n{user_feedback}")
        feedback_parts.append("请据此修改剧本。")
        user_text += "\n\n" + "\n\n".join(feedback_parts)

    llm = get_llm("writer")
    search_tool = get_search_tool()
    writer_agent = create_react_agent(llm, [search_tool, browse_web_page], prompt=writer_prompt)
    result = writer_agent.invoke({"messages": [build_multimodal_message(user_text, ref_images)]})

    return {
        "current_script": extract_react_final_content(result["messages"]),
        "current_node": "writer",
    }


def node_director_script_review(state: GraphState) -> dict:
    """Director script review with score."""
    if TEST_MODE:
        count = state.get("script_review_count", 0) + 1
        return {
            "director_script_review": test_call("director_script_review"),
            "script_review_count": count,
            "current_node": "director_script_review",
        }

    slim = compress_state_context(state, current_phase="director_script_review")
    director_prompt = get_agent_prompt("director")
    history_ctx = get_agent_context(get_project(state), "director")
    if history_ctx:
        director_prompt += f"\n\n{history_ctx}"

    messages = [
        SystemMessage(content=director_prompt),
        HumanMessage(content=(
            "请对以下剧本执行专业审核。\n"
            "从导演视角评估叙事结构、节奏、人物弧光、戏剧冲突、视觉可执行性。\n"
            "按照审核报告格式输出评分和结论。\n\n"
            f"--- 剧本内容 ---\n{slim['current_script']}"
        )),
    ]

    response = invoke_with_search(get_llm("director"), compress_messages(messages))
    count = state.get("script_review_count", 0) + 1

    return {
        "director_script_review": extract_text(response.content),
        "script_review_count": count,
        "current_node": "director_script_review",
    }


def node_showrunner_script_review(state: GraphState) -> dict:
    """Showrunner business + compliance review."""
    if TEST_MODE:
        return {
            "showrunner_script_review": test_call("showrunner_script_review"),
            "current_node": "showrunner_script_review",
        }

    slim = compress_state_context(state, current_phase="showrunner_script_review")
    showrunner_prompt = get_agent_prompt("showrunner")
    compliance_skill = get_skill_prompt("compliance-review")
    history_ctx = get_agent_context(get_project(state), "showrunner")

    system_content = (
        f"{showrunner_prompt}\n\n"
        f"--- 合规审核详细标准 ---\n{compliance_skill}"
    )
    if history_ctx:
        system_content += f"\n\n{history_ctx}"

    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=(
            "Director 已完成专业审核（第1步），请你执行业务审核（第2步）和合规审核（第3步）。\n\n"
            f"--- Director 审核报告 ---\n{slim['director_script_review']}\n\n"
            f"--- 剧本内容 ---\n{slim['current_script']}\n\n"
            f"--- 用户原始需求 ---\n{slim['user_request']}"
        )),
    ]

    response = invoke_with_search(get_llm("showrunner"), compress_messages(messages))
    return {
        "showrunner_script_review": extract_text(response.content),
        "current_node": "showrunner_script_review",
    }


def node_user_gate_script(state: GraphState) -> dict:
    """Pause for user script confirmation."""
    return {"current_node": "user_gate_script"}
