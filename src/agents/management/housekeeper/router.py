"""管家路由节点 — 联邦制入口分流器"""

import logging

from src.agents.management.housekeeper.keywords import MEDIA_KEYWORDS, DEV_KEYWORDS
from src.agents.management.housekeeper.classify import classify_intent
from src.services.memory.retrieve import retrieve_memory

logger = logging.getLogger(__name__)


def node_housekeeper_router(state: dict) -> dict:
    """管家分析用户意图并设置 target_group。"""
    user_request = state.get("user_request", "")

    # 检索长期记忆
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
    for kw in MEDIA_KEYWORDS:
        if kw in lower_req:
            logger.info("Housekeeper router: keyword '%s' -> media", kw)
            return {"target_group": "media", "current_node": "housekeeper_router"}

    for kw in DEV_KEYWORDS:
        if kw in lower_req:
            logger.info("Housekeeper router: keyword '%s' -> dev", kw)
            return {"target_group": "dev", "current_node": "housekeeper_router"}

    # LLM 分类
    target = classify_intent(user_request)
    logger.info("Housekeeper router: LLM classified -> %s", target)

    result = {"target_group": target, "current_node": "housekeeper_router"}
    if memory_context:
        existing_ref = state.get("reference_text", "")
        result["reference_text"] = (existing_ref + "\n\n" + memory_context).strip()
    return result
