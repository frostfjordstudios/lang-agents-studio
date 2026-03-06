"""管家路由节点 — 联邦制入口分流器

管家分析用户意图，决定路由到:
  - media: 影视创作工作流
  - dev: 开发/架构/进化工作流
  - chat: 日常闲聊，直接回复
"""

import logging
from langchain_core.messages import SystemMessage, HumanMessage

from src.core.llm_config import get_llm
from src.core.state import GraphState
from src.core.prompt_manager import get_agent_prompt
from src.core.long_term_memory import retrieve_memory

logger = logging.getLogger(__name__)

# 路由关键词（快速匹配，避免不必要的 LLM 调用）
_MEDIA_KEYWORDS = {"剧本", "拍摄", "分镜", "美术", "声音", "创作", "影视", "视频", "短片", "故事"}
_DEV_KEYWORDS = {"架构", "优化", "进化", "升级", "系统", "prompt", "提示词修改"}


def node_housekeeper_router(state: GraphState) -> dict:
    """管家分析用户意图并设置 target_group。"""
    user_request = state.get("user_request", "")

    # 检索长期记忆，注入 GraphState 上下文
    memory_context = ""
    try:
        memories = retrieve_memory(user_request[:50], user_request, limit=5)
        if memories:
            memory_context = "[长期记忆]\n" + "\n".join(f"- {m}" for m in memories)
            logger.info("Housekeeper injected %d long-term memories", len(memories))
    except Exception as e:
        logger.debug("Long-term memory retrieval skipped: %s", e)

    # 快速关键词匹配
    lower_req = user_request.lower()
    for kw in _MEDIA_KEYWORDS:
        if kw in lower_req:
            logger.info("Housekeeper router: keyword '%s' -> media", kw)
            return {"target_group": "media", "current_node": "housekeeper_router"}

    for kw in _DEV_KEYWORDS:
        if kw in lower_req:
            logger.info("Housekeeper router: keyword '%s' -> dev", kw)
            return {"target_group": "dev", "current_node": "housekeeper_router"}

    # 无法快速判断时，用 LLM 分类
    llm = get_llm("housekeeper")
    messages = [
        SystemMessage(content=(
            "你是项目管家。请判断用户的意图属于哪个类别，只回复一个单词：\n"
            "- media: 与影视创作相关（剧本、拍摄、分镜、美术、声音等）\n"
            "- dev: 与系统优化、架构调整、Agent 进化相关\n"
            "- chat: 日常闲聊、问候、与创作无关的问题\n"
            "只回复 media、dev 或 chat，不要解释。"
        )),
        HumanMessage(content=user_request),
    ]

    response = llm.invoke(messages)
    content = response.content.strip().lower() if isinstance(response.content, str) else "chat"

    if "media" in content:
        target = "media"
    elif "dev" in content:
        target = "dev"
    else:
        target = "chat"

    logger.info("Housekeeper router: LLM classified -> %s", target)
    result = {"target_group": target, "current_node": "housekeeper_router"}
    if memory_context:
        # 将记忆注入 reference_text，供下游 Agent 使用
        existing_ref = state.get("reference_text", "")
        result["reference_text"] = (existing_ref + "\n\n" + memory_context).strip()
    return result
