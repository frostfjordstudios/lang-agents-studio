"""Agent 节点模块 - 所有工作流节点的实现。

System Prompt 从 system_prompts/ 目录下的 Markdown 文件动态加载，
不在代码中硬编码，便于后续 Agent 自动完善 Markdown 时无需改动代码。
"""

import os
import json
from pathlib import Path
from langchain_core.messages import SystemMessage, HumanMessage

from .llm_config import llm_creative, llm_slight, llm_coder
from .state import GraphState

# ── 路径配置 ────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent
SYSTEM_PROMPTS_DIR = BASE_DIR / "system_prompts"
OUTPUT_DIR = BASE_DIR / "projects"


# ── 工具函数 ────────────────────────────────────────────────────────

def _load_prompt(*path_parts: str) -> str:
    """从 system_prompts/ 目录动态加载 Markdown 文件作为 System Prompt。

    Args:
        *path_parts: 相对于 system_prompts/ 的路径片段，
                     例如 ("agents", "writer", "writer.md")

    Returns:
        文件内容字符串
    """
    filepath = SYSTEM_PROMPTS_DIR.joinpath(*path_parts)
    if not filepath.exists():
        raise FileNotFoundError(f"System Prompt 文件不存在: {filepath}")
    return filepath.read_text(encoding="utf-8")


def _load_skill(*path_parts: str) -> str:
    """从 system_prompts/skills/ 目录加载 Skill 文件。"""
    return _load_prompt("skills", *path_parts)


def _save_output(project_name: str, episode: int, subdir: str, filename: str, content: str) -> str:
    """将产出物按规范写入 output_projects/ 对应的集数目录。

    Args:
        project_name: 项目名称
        episode: 集数编号
        subdir: 子目录名（如 "剧本"、"美术设计"、"分镜"）
        filename: 文件名
        content: 文件内容

    Returns:
        保存的文件路径
    """
    output_path = OUTPUT_DIR / project_name / "集数" / f"第{episode}集" / subdir
    output_path.mkdir(parents=True, exist_ok=True)
    filepath = output_path / filename
    filepath.write_text(content, encoding="utf-8")
    return str(filepath)


# ── Agent 节点 ──────────────────────────────────────────────────────

def node_writer(state: GraphState) -> dict:
    """Writer（编剧）节点 - 根据用户需求生成剧本。

    动态加载 writer.md 作为 System Prompt，
    结合用户需求生成专业影视级剧本。
    """
    # 动态加载 System Prompt
    writer_prompt = _load_prompt("agents", "writer", "writer.md")

    messages = [
        SystemMessage(content=writer_prompt),
        HumanMessage(content=(
            f"请根据以下需求编写剧本：\n\n{state['user_request']}\n\n"
            "请严格按照你的角色规范中定义的剧本格式输出。"
        )),
    ]

    # 如果有之前的审核意见（修改循环），附加到消息中
    if state.get("director_review") and state.get("review_count", 0) > 0:
        messages.append(HumanMessage(content=(
            f"Director 审核意见如下，请据此修改剧本：\n\n{state['director_review']}"
        )))

    response = llm_creative.invoke(messages)

    return {
        "current_script": response.content,
        "current_node": "writer",
    }


def node_director_review(state: GraphState) -> dict:
    """Director（导演）节点 - 执行三步审核。

    动态加载 director.md 和 compliance-review-skill.md，
    对 Writer 产出的剧本进行逻辑审核 → 业务审核 → 合规审核。
    """
    # 动态加载 System Prompt 和审核技能
    director_prompt = _load_prompt("agents", "director", "director.md")
    compliance_skill = _load_skill(
        "compliance-review-skill", "compliance-review-skill.md"
    )

    system_content = (
        f"{director_prompt}\n\n"
        f"--- 合规审核详细标准 ---\n{compliance_skill}"
    )

    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=(
            f"请对以下剧本执行三步审核（逻辑审核 → 业务审核 → 合规审核），"
            f"并按照审核报告格式输出结论。\n\n"
            f"--- 剧本内容 ---\n{state['current_script']}"
        )),
    ]

    response = llm_slight.invoke(messages)
    review_count = state.get("review_count", 0) + 1

    return {
        "director_review": response.content,
        "review_count": review_count,
        "current_node": "director_review",
    }


def node_user_gate(state: GraphState) -> dict:
    """用户确认门禁节点 - 仅做状态标记。

    实际的人工中断由 LangGraph 的 interrupt 机制在 graph.py 中实现。
    此节点用于呈现审核结果并记录用户反馈。
    """
    return {
        "current_node": "user_gate",
    }


def node_art_design(state: GraphState) -> dict:
    """Art-Design（美术设计）节点 - 生成角色/场景/道具设计方案。

    动态加载 art-design.md 和 art-design-skill.md。
    """
    art_prompt = _load_prompt("agents", "art-design", "art-design.md")
    art_skill = _load_skill("art-design-skill", "art-design-skill.md")

    system_content = f"{art_prompt}\n\n--- 美术设计技能规范 ---\n{art_skill}"

    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=(
            f"请根据以下已确认的剧本，提取所有视觉元素并编写设计方案。\n\n"
            f"--- 已确认剧本 ---\n{state['current_script']}"
        )),
    ]

    response = llm_creative.invoke(messages)

    return {
        "art_design_content": response.content,
        "current_node": "art_design",
    }


def node_voice_design(state: GraphState) -> dict:
    """Voice-Design（声音设计）节点 - 生成配音/音效/BGM 方案。

    动态加载 voice-design.md。
    """
    voice_prompt = _load_prompt("agents", "voice-design", "voice-design.md")

    messages = [
        SystemMessage(content=voice_prompt),
        HumanMessage(content=(
            f"请根据以下已确认的剧本，提取所有声音需求并编写声音设计方案。\n\n"
            f"--- 已确认剧本 ---\n{state['current_script']}"
        )),
    ]

    response = llm_creative.invoke(messages)

    return {
        "voice_design_content": response.content,
        "current_node": "voice_design",
    }


def node_storyboard(state: GraphState) -> dict:
    """Storyboard-Artist（分镜师）节点 - 整合前置内容生成分镜提示词。

    动态加载 storyboard-artist.md 和 seedance-storyboard-skill.md。
    """
    storyboard_prompt = _load_prompt(
        "agents", "storyboard-artist", "storyboard-artist.md"
    )
    storyboard_skill = _load_skill(
        "seedance-storyboard-skill", "seedance-storyboard-skill.md"
    )

    system_content = (
        f"{storyboard_prompt}\n\n"
        f"--- SeeDance 2.0 分镜编写规范 ---\n{storyboard_skill}"
    )

    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=(
            f"请整合以下材料，编写完整的分镜提示词。\n\n"
            f"--- 已确认剧本 ---\n{state['current_script']}\n\n"
            f"--- 美术设计方案 ---\n{state['art_design_content']}\n\n"
            f"--- 声音设计方案 ---\n{state['voice_design_content']}"
        )),
    ]

    response = llm_coder.invoke(messages)

    return {
        "final_storyboard": response.content,
        "current_node": "storyboard",
    }


def node_director_final_review(state: GraphState) -> dict:
    """Director 终审节点 - 对分镜提示词执行三步终审。

    动态加载 director.md 和 seedance-prompt-review-skill.md。
    """
    director_prompt = _load_prompt("agents", "director", "director.md")
    review_skill = _load_skill(
        "seedance-prompt-review-skill", "seedance-prompt-review-skill.md"
    )

    system_content = (
        f"{director_prompt}\n\n"
        f"--- SeeDance 2.0 提示词审核标准 ---\n{review_skill}"
    )

    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=(
            f"请对以下分镜提示词执行终审三步审核（逻辑 → 业务 → 合规），"
            f"并按审核报告格式输出。\n\n"
            f"--- 分镜提示词 ---\n{state['final_storyboard']}\n\n"
            f"--- 原始剧本 ---\n{state['current_script']}"
        )),
    ]

    response = llm_slight.invoke(messages)

    return {
        "director_review": response.content,
        "current_node": "director_final_review",
    }
