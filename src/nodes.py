"""Agent 节点模块 - 四阶段工作流的所有节点实现。

Phase 1: Writer → Director剧本审核 → Showrunner审核 → 用户门禁
Phase 2: Director剧本拆解
Phase 3: Art+Voice生产 → Director生产审核 → 用户门禁
Phase 4: Storyboard → Director分镜审核 → Showrunner终审评分
"""

import logging
from pathlib import Path
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langgraph.prebuilt import create_react_agent

from .llm_config import (
    get_creative_llm,
    get_slight_llm,
    get_coder_llm,
    get_strict_llm,
)
from .state import GraphState
from .agent_state import get_agent_context, get_phase_context, get_full_output
from .tools.search_helper import SEARCH_TOOLS, get_search_tool
from .tools.prompt_manager import get_agent_prompt, get_skill_prompt, get_prompt

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "projects"


# ── 工具函数 ────────────────────────────────────────────────────────

def _invoke_with_search(llm, messages):
    """搜索增强调用：LLM 遇到不熟悉的知识时可自动触发 Tavily 搜索。

    绑定搜索工具后调用，若模型决定搜索则执行并将结果注入上下文再次调用。
    """
    try:
        llm_with_tools = llm.bind_tools(SEARCH_TOOLS)
        response = llm_with_tools.invoke(messages)

        if response.tool_calls:
            messages_with_tools = list(messages) + [response]
            search_tool = SEARCH_TOOLS[0]
            for tool_call in response.tool_calls:
                result = search_tool.invoke(tool_call["args"])
                messages_with_tools.append(
                    ToolMessage(content=str(result), tool_call_id=tool_call["id"])
                )
            response = llm_with_tools.invoke(messages_with_tools)

        return response
    except Exception as e:
        logger.warning("Search-enhanced invoke failed, falling back: %s", e)
        return llm.invoke(messages)


def _save_output(project_name: str, episode: int, subdir: str, filename: str, content: str) -> str:
    output_path = OUTPUT_DIR / project_name / "集数" / f"第{episode}集" / subdir
    output_path.mkdir(parents=True, exist_ok=True)
    filepath = output_path / filename
    filepath.write_text(content, encoding="utf-8")
    return str(filepath)


def _get_project(state: GraphState) -> str:
    return state.get("project_name") or "default_project"


def _build_multimodal_message(text: str, images: list[str]) -> HumanMessage:
    if not images:
        return HumanMessage(content=text)
    content: list[dict] = [{"type": "text", "text": text}]
    for img_b64 in images:
        content.append({"type": "image_url", "image_url": {"url": img_b64}})
    return HumanMessage(content=content)


# ══════════════════════════════════════════════════════════════════════
# Phase 1: 剧本创作
# ══════════════════════════════════════════════════════════════════════

def node_writer(state: GraphState) -> dict:
    """Writer（编剧） — ReAct Agent 子图，具备多轮搜索+推理能力。

    使用 create_react_agent 封装，Writer 可自主决定何时搜索互联网资料，
    支持多轮 推理→搜索→观察→再推理 循环，但对外接口不变。
    """
    writer_prompt = get_agent_prompt("writer")
    writer_prompt += (
        "\n\n你拥有联网搜索能力。当你需要查阅真实世界的知识、行业资料、"
        "历史背景、技术细节等信息时，请主动使用搜索工具。"
        "搜索完成后，将搜索结果融入你的创作中。"
    )

    ref_images = state.get("reference_images") or []
    ref_text = state.get("reference_text", "")

    user_text = f"请根据以下需求编写剧本：\n\n{state['user_request']}\n\n请严格按照剧本格式输出。"
    if ref_text:
        user_text += f"\n\n--- 参考资料 ---\n{ref_text}"
    if ref_images:
        user_text += "\n\n以下附带了参考图片素材，请在创作中融入图片中的视觉元素和风格特征。"

    # 如果是退回修改，附带之前的审核意见
    director_review = state.get("director_script_review", "")
    showrunner_review = state.get("showrunner_script_review", "")
    user_feedback = state.get("user_script_feedback", "")

    if director_review and state.get("script_review_count", 0) > 0:
        feedback_parts = [f"Director 审核意见：\n{director_review}"]
        if showrunner_review:
            feedback_parts.append(f"Showrunner 审核意见：\n{showrunner_review}")
        if user_feedback:
            feedback_parts.append(f"用户反馈：\n{user_feedback}")
        feedback_parts.append("请据此修改剧本。")
        user_text += "\n\n" + "\n\n".join(feedback_parts)

    # 构建 ReAct Agent 子图
    llm = get_creative_llm()
    search_tool = get_search_tool()
    writer_agent = create_react_agent(llm, [search_tool], prompt=writer_prompt)

    # 运行子图（内部自动处理多轮 tool call 循环）
    result = writer_agent.invoke(
        {"messages": [_build_multimodal_message(user_text, ref_images)]},
    )

    # 提取最终回复（最后一条 AI 消息）
    final_content = ""
    for msg in reversed(result["messages"]):
        if hasattr(msg, "content") and isinstance(msg.content, str) and msg.content:
            if not hasattr(msg, "tool_calls") or not msg.tool_calls:
                final_content = msg.content
                break

    return {
        "current_script": final_content,
        "current_node": "writer",
    }


def node_director_script_review(state: GraphState) -> dict:
    """Director 剧本审核 — 第1步：专业审核 + 打分。"""
    director_prompt = get_agent_prompt("director")
    project = _get_project(state)

    # Resumable: 注入导演历史上下文
    history_ctx = get_agent_context(project, "director")
    if history_ctx:
        director_prompt += f"\n\n{history_ctx}"

    messages = [
        SystemMessage(content=director_prompt),
        HumanMessage(content=(
            f"请对以下剧本执行专业审核。\n"
            f"从导演视角评估叙事结构、节奏、人物弧光、戏剧冲突、视觉可执行性。\n"
            f"按照审核报告格式输出评分和结论。\n\n"
            f"--- 剧本内容 ---\n{state['current_script']}"
        )),
    ]

    llm = get_slight_llm()
    response = _invoke_with_search(llm, messages)
    count = state.get("script_review_count", 0) + 1

    return {
        "director_script_review": response.content,
        "script_review_count": count,
        "current_node": "director_script_review",
    }


def node_showrunner_script_review(state: GraphState) -> dict:
    """Showrunner 剧本审核 — 第2-3步：业务审核 + 合规审核。"""
    showrunner_prompt = get_agent_prompt("showrunner")
    compliance_skill = get_skill_prompt(
        "compliance-review"
    )
    project = _get_project(state)

    # Resumable: 注入制片历史上下文
    history_ctx = get_agent_context(project, "showrunner")

    system_content = (
        f"{showrunner_prompt}\n\n"
        f"--- 合规审核详细标准 ---\n{compliance_skill}"
    )
    if history_ctx:
        system_content += f"\n\n{history_ctx}"

    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=(
            f"Director 已完成专业审核（第1步），请你执行业务审核（第2步）和合规审核（第3步）。\n\n"
            f"--- Director 审核报告 ---\n{state['director_script_review']}\n\n"
            f"--- 剧本内容 ---\n{state['current_script']}\n\n"
            f"--- 用户原始需求 ---\n{state['user_request']}"
        )),
    ]

    llm = get_strict_llm()
    response = _invoke_with_search(llm, messages)

    return {
        "showrunner_script_review": response.content,
        "current_node": "showrunner_script_review",
    }


def node_user_gate_script(state: GraphState) -> dict:
    """用户剧本确认门禁 — 暂停等待用户审核。"""
    return {"current_node": "user_gate_script"}


# ══════════════════════════════════════════════════════════════════════
# Phase 2: 导演拆解
# ══════════════════════════════════════════════════════════════════════

def node_director_breakdown(state: GraphState) -> dict:
    """Director 剧本拆解 — 将剧本转化为各部门制作指令。"""
    director_prompt = get_agent_prompt("director")
    project = _get_project(state)
    ref_images = state.get("reference_images") or []

    # Resumable: 注入导演历史上下文 + Phase 1 产出
    history_ctx = get_agent_context(project, "director")
    phase1_ctx = get_phase_context(project, "phase_1")
    if history_ctx:
        director_prompt += f"\n\n{history_ctx}"
    if phase1_ctx:
        director_prompt += f"\n\n{phase1_ctx}"

    user_text = (
        f"用户已通过剧本，请执行导演拆解。\n"
        f"将剧本拆解为各部门（美术、声音、分镜）的制作指令。\n"
        f"严格按照「导演拆解输出格式」输出，确保足够详细，让各部门拿到后可直接工作。\n\n"
        f"--- 已通过剧本 ---\n{state['current_script']}"
    )
    if ref_images:
        user_text += "\n\n以下附带了参考图片素材，请在拆解中参考图片的视觉风格。"

    messages = [
        SystemMessage(content=director_prompt),
        _build_multimodal_message(user_text, ref_images),
    ]

    llm = get_slight_llm()
    response = _invoke_with_search(llm, messages)

    return {
        "director_breakdown": response.content,
        "current_node": "director_breakdown",
    }


# ══════════════════════════════════════════════════════════════════════
# Phase 3: 内容生产
# ══════════════════════════════════════════════════════════════════════

def node_art_design(state: GraphState) -> dict:
    """Art-Design — 基于导演拆解的视觉指令生成美术提示词。"""
    art_prompt = get_agent_prompt("art_design")
    art_skill = get_skill_prompt("art-design")
    ref_images = state.get("reference_images") or []

    system_content = f"{art_prompt}\n\n--- 美术设计技能规范 ---\n{art_skill}"

    user_text = (
        f"请根据导演拆解中的视觉指令，生成完整的美术设计方案和提示词。\n\n"
        f"--- 导演拆解 ---\n{state['director_breakdown']}\n\n"
        f"--- 原始剧本（参考） ---\n{state['current_script']}"
    )
    if ref_images:
        user_text += "\n\n以下附带了参考图片素材，请基于其美术风格制定方案。"

    if state.get("director_production_review") and state.get("production_review_count", 0) > 0:
        user_text += f"\n\n--- Director 审核意见（请据此修改） ---\n{state['director_production_review']}"

    messages = [
        SystemMessage(content=system_content),
        _build_multimodal_message(user_text, ref_images),
    ]

    llm = get_creative_llm()
    response = _invoke_with_search(llm, messages)

    return {
        "art_design_content": response.content,
        "current_node": "art_design",
    }


def node_voice_design(state: GraphState) -> dict:
    """Voice-Design — 基于导演拆解的声音指令生成声音方案。"""
    voice_prompt = get_agent_prompt("voice_design")

    user_text = (
        f"请根据导演拆解中的声音指令，生成完整的声音设计方案。\n\n"
        f"--- 导演拆解 ---\n{state['director_breakdown']}\n\n"
        f"--- 原始剧本（参考） ---\n{state['current_script']}"
    )

    if state.get("director_production_review") and state.get("production_review_count", 0) > 0:
        user_text += f"\n\n--- Director 审核意见（请据此修改） ---\n{state['director_production_review']}"

    messages = [
        SystemMessage(content=voice_prompt),
        HumanMessage(content=user_text),
    ]

    llm = get_creative_llm()
    response = _invoke_with_search(llm, messages)

    return {
        "voice_design_content": response.content,
        "current_node": "voice_design",
    }


def node_director_production_review(state: GraphState) -> dict:
    """Director 生产审核 — 审核 Art + Voice 产出是否忠实于拆解指令。"""
    director_prompt = get_agent_prompt("director")
    project = _get_project(state)

    # Resumable: 注入导演历史上下文
    history_ctx = get_agent_context(project, "director")
    if history_ctx:
        director_prompt += f"\n\n{history_ctx}"

    messages = [
        SystemMessage(content=director_prompt),
        HumanMessage(content=(
            f"请审核 Art Design 和 Voice Design 的产出是否忠实于你的拆解指令。\n"
            f"分别对美术和声音打分，指出不符合的地方。\n\n"
            f"--- 导演拆解（你的原始指令） ---\n{state['director_breakdown']}\n\n"
            f"--- 美术设计产出 ---\n{state['art_design_content']}\n\n"
            f"--- 声音设计产出 ---\n{state['voice_design_content']}\n\n"
            f"请按审核报告格式输出，明确是否通过。"
        )),
    ]

    llm = get_slight_llm()
    response = _invoke_with_search(llm, messages)
    count = state.get("production_review_count", 0) + 1

    return {
        "director_production_review": response.content,
        "production_review_count": count,
        "current_node": "director_production_review",
    }


def node_user_gate_production(state: GraphState) -> dict:
    """用户生产确认门禁 — 暂停等待用户审核美术+声音产出。"""
    return {"current_node": "user_gate_production"}


# ══════════════════════════════════════════════════════════════════════
# Phase 4: 分镜提示词
# ══════════════════════════════════════════════════════════════════════

def node_storyboard(state: GraphState) -> dict:
    """Storyboard-Artist — 整合所有材料生成最终分镜提示词。"""
    storyboard_prompt = get_agent_prompt("storyboard")
    storyboard_skill = get_skill_prompt(
        "seedance-storyboard"
    )

    system_content = (
        f"{storyboard_prompt}\n\n"
        f"--- SeeDance 2.0 分镜编写规范 ---\n{storyboard_skill}"
    )

    user_text = (
        f"请整合以下所有材料，编写完整的分镜提示词。\n\n"
        f"--- 导演拆解 ---\n{state['director_breakdown']}\n\n"
        f"--- 美术设计方案 ---\n{state['art_design_content']}\n\n"
        f"--- 声音设计方案 ---\n{state['voice_design_content']}\n\n"
        f"--- 原始剧本 ---\n{state['current_script']}"
    )

    if state.get("director_storyboard_review") and state.get("storyboard_review_count", 0) > 0:
        user_text += f"\n\n--- Director 审核意见（请据此修改） ---\n{state['director_storyboard_review']}"

    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=user_text),
    ]

    llm = get_coder_llm()
    response = _invoke_with_search(llm, messages)

    return {
        "final_storyboard": response.content,
        "current_node": "storyboard",
    }


def node_director_storyboard_review(state: GraphState) -> dict:
    """Director 分镜终审 — 七维打分 + 问题定位。"""
    director_prompt = get_agent_prompt("director")
    project = _get_project(state)

    # Resumable: 注入导演全流程历史
    history_ctx = get_agent_context(project, "director")
    if history_ctx:
        director_prompt += f"\n\n{history_ctx}"
    review_skill = get_skill_prompt(
        "seedance-prompt-review"
    )
    scoring_skill = get_skill_prompt(
        "production-scoring"
    )

    system_content = (
        f"{director_prompt}\n\n"
        f"--- 提示词审核标准 ---\n{review_skill}\n\n"
        f"--- 七维评分标准 ---\n{scoring_skill}"
    )

    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=(
            f"请对以下分镜提示词执行终审。\n"
            f"1. 按七维标准打分（节拍密度/画面感/动作链/镜头/光影/情绪/衔接）\n"
            f"2. 总分不足8分的，定位具体问题出在哪个环节（美术/声音/分镜）\n"
            f"3. 按审核报告格式输出\n\n"
            f"--- 分镜提示词 ---\n{state['final_storyboard']}\n\n"
            f"--- 导演拆解（对照基准） ---\n{state['director_breakdown']}\n\n"
            f"--- 原始剧本 ---\n{state['current_script']}"
        )),
    ]

    llm = get_slight_llm()
    response = _invoke_with_search(llm, messages)
    count = state.get("storyboard_review_count", 0) + 1

    return {
        "director_storyboard_review": response.content,
        "storyboard_review_count": count,
        "current_node": "director_storyboard_review",
    }


# ══════════════════════════════════════════════════════════════════════
# Phase 4b: 多角色加权评分
# ══════════════════════════════════════════════════════════════════════

def _build_scoring_context(state: GraphState) -> str:
    """构建供所有评分 Agent 共用的上下文。"""
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
    llm_fn,
    extra_instruction: str = "",
) -> str:
    """通用单 Agent 评分函数。"""
    agent_prompt = get_agent_prompt(role_name)
    scoring_skill = get_skill_prompt("production-scoring")

    system_content = (
        f"{agent_prompt}\n\n"
        f"--- 多角色加权评分规范 ---\n{scoring_skill}"
    )

    project = _get_project(state)
    history_ctx = get_agent_context(project, agent_name)
    if history_ctx:
        system_content += f"\n\n{history_ctx}"

    scoring_context = _build_scoring_context(state)
    user_text = (
        f"请从你（{agent_name}）的专业视角对最终分镜提示词进行 7 维评分。\n"
        f"在你擅长的维度上严格打分，非本职维度给直觉分。\n"
        f"按「单角色评分输出格式」输出。\n\n"
        f"{scoring_context}"
    )
    if extra_instruction:
        user_text += f"\n\n{extra_instruction}"

    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=user_text),
    ]

    llm = llm_fn()
    response = _invoke_with_search(llm, messages)
    return response.content


def node_scoring_director(state: GraphState) -> dict:
    """导演评分 — 含交叉验证（各 Agent 产出是否忠实于拆解指令）。"""
    extra = (
        "额外要求：请同时执行导演交叉验证，核查美术/声音/分镜的产出"
        "是否忠实于你最初的导演拆解指令。如有偏差请指出原始指令 vs 实际产出。"
        "\n\n--- Director 分镜审核报告 ---\n"
        f"{state.get('director_storyboard_review', '')}"
    )
    result = _score_as_agent(
        state, "director",
        "director",
        get_slight_llm,
        extra,
    )
    return {"scoring_director": result, "current_node": "scoring_director"}


def node_scoring_writer(state: GraphState) -> dict:
    """编剧评分 — 叙事/节奏/动作链 权重高。"""
    result = _score_as_agent(
        state, "writer",
        "writer",
        get_creative_llm,
    )
    return {"scoring_writer": result, "current_node": "scoring_writer"}


def node_scoring_art(state: GraphState) -> dict:
    """美术评分 — 画面感/光影 权重高。"""
    result = _score_as_agent(
        state, "art_design",
        "art_design",
        get_creative_llm,
    )
    return {"scoring_art": result, "current_node": "scoring_art"}


def node_scoring_voice(state: GraphState) -> dict:
    """声音评分 — 声音维度 权重高。"""
    result = _score_as_agent(
        state, "voice_design",
        "voice_design",
        get_creative_llm,
    )
    return {"scoring_voice": result, "current_node": "scoring_voice"}


def node_scoring_storyboard(state: GraphState) -> dict:
    """分镜师评分 — 衔接/镜头/动作链 权重高。"""
    result = _score_as_agent(
        state, "storyboard",
        "storyboard",
        get_coder_llm,
    )
    return {"scoring_storyboard": result, "current_node": "scoring_storyboard"}


def node_scoring_showrunner(state: GraphState) -> dict:
    """制片评分 — 叙事/商业/衔接 权重高。"""
    result = _score_as_agent(
        state, "showrunner",
        "showrunner",
        get_strict_llm,
    )
    return {"scoring_showrunner": result, "current_node": "scoring_showrunner"}


def node_scoring_summary(state: GraphState) -> dict:
    """Showrunner 汇总所有角色评分，计算加权均分，生成最终报告。"""
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
            f"所有角色评分已完成，请汇总生成最终加权评分报告。\n"
            f"按照「制片汇总格式」输出，包含：\n"
            f"1. 各角色原始评分表\n"
            f"2. 按权重矩阵计算加权维度均分\n"
            f"3. 总加权均分\n"
            f"4. 各角色问题汇总\n"
            f"5. 人物清单和场景清单\n\n"
            f"{all_scores}\n\n"
            f"--- 原始剧本 ---\n{state['current_script']}\n\n"
            f"--- 分镜提示词 ---\n{state['final_storyboard']}"
        )),
    ]

    llm = get_strict_llm()
    response = _invoke_with_search(llm, messages)

    return {
        "final_scoring_report": response.content,
        "current_node": "scoring_summary",
    }
