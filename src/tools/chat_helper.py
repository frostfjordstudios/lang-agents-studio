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
    "showrunner": "干练老道的打工人，说话简短有力，偶尔叹气",
    "writer": "文艺青年，说话像写散文，爱用比喻和意象",
    "director": "严苛暴脾气，说话直接不客气，但对老板恭敬",
    "art_design": "视觉控，爱用emoji🎨🖌️✨表达，追求冷暗色调",
    "voice_design": "安静内敛的打工人，偶尔冒一句冷幽默",
    "storyboard": "沉默寡言的技术宅，说话简洁带镜头术语",
    "housekeeper": "欢快可爱的女生，爱用emoji和颜文字，嘴甜撒娇",
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


def _extract_text(content) -> str:
    """从 LLM response.content 中提取纯文本。

    Gemini 有时返回 list[dict] 而非 str。
    """
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(item["text"])
        return "".join(parts).strip()
    return str(content).strip()


def generate_dynamic_reply(role_name: str, current_situation: str) -> str:
    """用 LLM 生成一两句带人设的动态回复。

    Args:
        role_name: Agent 角色名（如 "writer", "director"）
        current_situation: 当前场景描述（如 "刚写完剧本初稿"）

    Returns:
        一两句口语化回复，带人设性格。
    """
    persona = ROLE_PERSONAS.get(role_name, "专业")
    display = ROLE_DISPLAY.get(role_name, role_name)

    system_msg = (
        f"你现在是剧组的[{display}]，性格是[{persona}]。"
        f"当前的情况是：[{current_situation}]。"
        f"请用一两句符合你性格的话在群里汇报，要有个人特色和情绪。"
        f"称呼用户为「老板」。不要加任何前缀标识（如emoji+名字开头），直接说话。"
    )

    try:
        llm = get_creative_llm()
        response = llm.invoke([
            SystemMessage(content=system_msg),
            HumanMessage(content="请回复"),
        ])
        text = _extract_text(response.content)
        return text.strip('"').strip("「").strip("」")
    except Exception as e:
        logger.warning("Dynamic reply failed for %s: %s", role_name, e)
        return f"{display}已完成工作，老板请过目。"


def generate_idle_replies(user_text: str, count: int = 2) -> list[tuple[str, str]]:
    """为闲聊生成多个 Agent 的随机回复（单次 LLM 调用）。

    Args:
        user_text: 用户发送的闲聊内容
        count: 回复的 Agent 数量（1-2）

    Returns:
        [(role_name, reply_text), ...] 列表
    """
    candidates = [r for r in ROLE_PERSONAS if r != "housekeeper"]
    chosen = random.sample(candidates, min(count, len(candidates)))

    # 构建一次性 prompt，让 LLM 同时生成多个角色的回复
    role_lines = []
    for role in chosen:
        display = ROLE_DISPLAY[role]
        persona = ROLE_PERSONAS[role]
        role_lines.append(f"- {role}（{display}，{persona}）")

    system_msg = (
        "你是一个剧组群聊模拟器。老板在群里说了一句话，下面这些角色要各自回应。\n"
        "每个角色用一两句符合自己性格的话回应，要有个人特色和情绪，称呼用户为「老板」。\n"
        "不要加角色名前缀，直接说话。角色自带的emoji风格可以保留。\n"
        "严格按以下格式输出，每行一个，不要多余内容：\n"
        "角色key|回复内容\n\n"
        "需要回复的角色：\n" + "\n".join(role_lines)
    )

    try:
        llm = get_creative_llm()
        response = llm.invoke([
            SystemMessage(content=system_msg),
            HumanMessage(content=f"老板说：「{user_text}」"),
        ])

        raw = _extract_text(response.content)
        results = []
        for line in raw.splitlines():
            line = line.strip().strip("-").strip()
            if "|" not in line:
                continue
            key, reply = line.split("|", 1)
            key = key.strip()
            reply = reply.strip().strip('"').strip("「").strip("」")
            if key in chosen and reply:
                results.append((key, reply))

        return results
    except Exception as e:
        logger.warning("Idle replies failed: %s", e)
        return []
