"""Micro-Persona Chat 模块 — 轻量级人设动态回复

为每个 Agent 定义极短人设标签，通过 LLM 生成口语化、带性格的群聊回复，
替代硬编码的节点消息模板。所有 Agent 称呼用户为"老板"。
"""

import random
import logging
from langchain_core.messages import SystemMessage, HumanMessage

from src.llm_config import get_creative_llm

logger = logging.getLogger(__name__)

# ── 角色人设（每条 ≤20 字）──────────────────────────────────────────

ROLE_PERSONAS: dict[str, str] = {
    "showrunner": "统筹全盘，干练",
    "writer": "脑洞大开，关注剧情",
    "director": "严苛，抓物理细节，暴脾气",
    "art_design": "追求极致视觉和冷暗色调",
    "voice_design": "对听觉极其敏感",
    "storyboard": "沉浸于镜头语言",
    "housekeeper": "优雅，贴心处理后勤与飞书文档归档",
}

# 角色显示名
ROLE_DISPLAY: dict[str, str] = {
    "showrunner": "制片",
    "writer": "编剧",
    "director": "导演",
    "art_design": "美术",
    "voice_design": "声音",
    "storyboard": "分镜师",
    "housekeeper": "管家",
}


def generate_dynamic_reply(role_name: str, current_situation: str) -> str:
    """用 LLM 生成一句带人设的动态回复。

    Args:
        role_name: Agent 角色名（如 "writer", "director"）
        current_situation: 当前场景描述（如 "刚写完剧本初稿"）

    Returns:
        一句口语化回复（≤30 字），已包含 Emoji + 角色名前缀。
    """
    persona = ROLE_PERSONAS.get(role_name, "专业")
    display = ROLE_DISPLAY.get(role_name, role_name)

    system_msg = (
        f"你现在是剧组的[{display}]，性格是[{persona}]。"
        f"当前的情况是：[{current_situation}]。"
        f"请用一句简短、口语化的话在群里汇报或吐槽，字数控制在30字以内。"
        f"称呼用户为「老板」。不要加任何前缀标识，直接说话。"
    )

    try:
        llm = get_creative_llm()
        response = llm.invoke([
            SystemMessage(content=system_msg),
            HumanMessage(content="请回复"),
        ])
        return response.content.strip().strip('"').strip("「").strip("」")
    except Exception as e:
        logger.warning("Dynamic reply failed for %s: %s", role_name, e)
        return f"{display}已完成工作，老板请过目。"


def generate_idle_replies(user_text: str, count: int = 2) -> list[tuple[str, str]]:
    """为闲聊生成多个 Agent 的随机回复。

    Args:
        user_text: 用户发送的闲聊内容
        count: 回复的 Agent 数量（1-2）

    Returns:
        [(role_name, reply_text), ...] 列表
    """
    # 随机选 count 个非管家 Agent
    candidates = [r for r in ROLE_PERSONAS if r != "housekeeper"]
    chosen = random.sample(candidates, min(count, len(candidates)))

    results = []
    for role in chosen:
        persona = ROLE_PERSONAS[role]
        display = ROLE_DISPLAY[role]

        system_msg = (
            f"你现在是剧组的[{display}]，性格是[{persona}]。"
            f"老板在群里说了一句闲聊：「{user_text}」。"
            f"请用一句简短、口语化的话回应，字数控制在30字以内。"
            f"称呼用户为「老板」。不要加任何前缀标识，直接说话。"
        )

        try:
            llm = get_creative_llm()
            response = llm.invoke([
                SystemMessage(content=system_msg),
                HumanMessage(content="请回复"),
            ])
            reply = response.content.strip().strip('"').strip("「").strip("」")
            results.append((role, reply))
        except Exception as e:
            logger.warning("Idle reply failed for %s: %s", role, e)

    return results
