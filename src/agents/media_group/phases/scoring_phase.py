"""Phase 4b: multi-agent scoring."""

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.state.context import get_agent_context
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


def _build_scoring_context(state: GraphState) -> str:
    return (
        f"--- 最终分镜提示词（评分对象） ---\n{state['final_storyboard']}\n\n"
        f"--- 导演拆解（基准指令） ---\n{state['director_breakdown']}\n\n"
        f"--- 美术设计方案 ---\n{state.get('art_design_content', '')}\n\n"
        f"--- 声音设计方案 ---\n{state.get('voice_design_content', '')}\n\n"
        f"--- 原始剧本 ---\n{state['current_script']}"
    )


def _score_as_agent(
    state: GraphState,
    agent_name: str,
    role_name: str,
    extra_instruction: str = "",
) -> str:
    if TEST_MODE:
        return test_call("scoring")

    agent_prompt = get_agent_prompt(role_name)
    scoring_skill = get_skill_prompt("production-scoring")
    system_content = (
        f"{agent_prompt}\n\n"
        f"--- 多角色加权评分规范 ---\n{scoring_skill}"
    )

    history_ctx = get_agent_context(get_project(state), agent_name)
    if history_ctx:
        system_content += f"\n\n{history_ctx}"

    user_text = (
        f"请从你（{agent_name}）的专业视角对最终分镜提示词进行 7 维评分。\n"
        "在你擅长的维度上严格打分，非本职维度给直觉分。\n"
        "按「单角色评分输出格式」输出。\n\n"
        f"{_build_scoring_context(state)}"
    )
    if extra_instruction:
        user_text += f"\n\n{extra_instruction}"

    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=user_text),
    ]
    response = invoke_with_search(get_llm(role_name), messages)
    return extract_text(response.content)


def node_scoring_director(state: GraphState) -> dict:
    extra = (
        "额外要求：请同时执行导演交叉验证，核查美术/声音/分镜的产出"
        "是否忠实于你最初的导演拆解指令。如有偏差请指出原始指令 vs 实际产出。"
        "\n\n--- Director 分镜审核报告 ---\n"
        f"{state.get('director_storyboard_review', '')}"
    )
    return {
        "scoring_director": _score_as_agent(state, "director", "director", extra),
        "current_node": "scoring_director",
    }


def node_scoring_writer(state: GraphState) -> dict:
    return {
        "scoring_writer": _score_as_agent(state, "writer", "writer"),
        "current_node": "scoring_writer",
    }


def node_scoring_art(state: GraphState) -> dict:
    return {
        "scoring_art": _score_as_agent(state, "art_design", "art_design"),
        "current_node": "scoring_art",
    }


def node_scoring_voice(state: GraphState) -> dict:
    return {
        "scoring_voice": _score_as_agent(state, "voice_design", "voice_design"),
        "current_node": "scoring_voice",
    }


def node_scoring_storyboard(state: GraphState) -> dict:
    return {
        "scoring_storyboard": _score_as_agent(state, "storyboard", "storyboard"),
        "current_node": "scoring_storyboard",
    }


def node_scoring_showrunner(state: GraphState) -> dict:
    return {
        "scoring_showrunner": _score_as_agent(state, "showrunner", "showrunner"),
        "current_node": "scoring_showrunner",
    }


def node_scoring_summary(state: GraphState) -> dict:
    """Showrunner summarizes weighted final report."""
    if TEST_MODE:
        return {
            "final_scoring_report": test_call("scoring_summary"),
            "current_node": "scoring_summary",
        }

    showrunner_prompt = get_agent_prompt("showrunner")
    scoring_skill = get_skill_prompt("production-scoring")

    all_scores = (
        f"--- 🎬 导演评分 ---\n{state.get('scoring_director', '')}\n\n"
        f"--- ✍️ 编剧评分 ---\n{state.get('scoring_writer', '')}\n\n"
        f"--- 🎨 美术评分 ---\n{state.get('scoring_art', '')}\n\n"
        f"--- 🔊 声音评分 ---\n{state.get('scoring_voice', '')}\n\n"
        f"--- 📐 分镜评分 ---\n{state.get('scoring_storyboard', '')}\n\n"
        f"--- 🎯 制片评分 ---\n{state.get('scoring_showrunner', '')}"
    )

    messages = [
        SystemMessage(content=(
            f"{showrunner_prompt}\n\n"
            f"--- 多角色加权评分规范 ---\n{scoring_skill}"
        )),
        HumanMessage(content=(
            "所有角色评分已完成，请汇总生成最终加权评分报告。\n"
            "按照「制片汇总格式」输出，包含：\n"
            "1. 各角色原始评分表\n"
            "2. 按权重矩阵计算加权维度均分\n"
            "3. 总加权均分\n"
            "4. 各角色问题汇总\n"
            "5. 人物清单和场景清单\n\n"
            f"{all_scores}\n\n"
            f"--- 原始剧本 ---\n{state['current_script']}\n\n"
            f"--- 分镜提示词 ---\n{state['final_storyboard']}"
        )),
    ]
    response = invoke_with_search(get_llm("showrunner"), messages)

    return {
        "final_scoring_report": extract_text(response.content),
        "current_node": "scoring_summary",
    }
