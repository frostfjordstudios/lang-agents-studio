"""长期记忆模块 — 基于 Mem0 + Qdrant 的跨 Session 个性化记忆

提供 add_memory / retrieve_memory / get_all_memories 三个核心函数，
供管家或其他 Agent 在对话中存取用户的长期偏好与设定。

使用方式:
    from src.core.long_term_memory import add_memory, retrieve_memory
    add_memory("user_001", "所有反派都要穿黑衣服")
    results = retrieve_memory("user_001", "反派角色的着装要求")
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_memory_instance = None


def _get_memory():
    """延迟初始化 Mem0 Memory 实例（单例）。"""
    global _memory_instance
    if _memory_instance is not None:
        return _memory_instance

    try:
        from mem0 import Memory
    except ImportError:
        logger.error("mem0ai 未安装，请运行: pip install mem0ai>=0.1.29")
        raise

    host = os.environ.get("QDRANT_HOST", "localhost")
    port = int(os.environ.get("QDRANT_PORT", "6333"))

    config = {
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": "langgraph_agent_memory",
                "host": host,
                "port": port,
            },
        },
    }

    _memory_instance = Memory.from_config(config)
    logger.info("Long-term memory initialized (Qdrant @ %s:%d)", host, port)
    return _memory_instance


def add_memory(user_id: str, content: str) -> bool:
    """将内容存入用户的长期记忆库。

    Args:
        user_id: 用户标识（如飞书 chat_id）
        content: 要记住的内容

    Returns:
        是否成功
    """
    try:
        mem = _get_memory()
        mem.add(content, user_id=user_id)
        logger.info("Memory added for user=%s: %s", user_id, content[:100])
        return True
    except Exception as e:
        logger.warning("Failed to add memory for user=%s: %s", user_id, e)
        return False


def retrieve_memory(user_id: str, query: str, limit: int = 5) -> list[str]:
    """根据查询从用户的长期记忆库检索相关记忆。

    Args:
        user_id: 用户标识
        query: 查询文本
        limit: 最大返回条数

    Returns:
        相关记忆文本列表
    """
    try:
        mem = _get_memory()
        results = mem.search(query=query, user_id=user_id, limit=limit)

        texts = []
        if isinstance(results, list):
            for item in results:
                text = item.get("text") or item.get("memory", "")
                if text:
                    texts.append(text)
        elif isinstance(results, dict) and "results" in results:
            for item in results["results"]:
                text = item.get("text") or item.get("memory", "")
                if text:
                    texts.append(text)

        logger.info("Retrieved %d memories for user=%s, query=%s", len(texts), user_id, query[:50])
        return texts
    except Exception as e:
        logger.warning("Failed to retrieve memory for user=%s: %s", user_id, e)
        return []


def get_all_memories(user_id: str) -> list[str]:
    """获取用户的所有长期记忆。"""
    try:
        mem = _get_memory()
        results = mem.get_all(user_id=user_id)

        texts = []
        if isinstance(results, dict) and "results" in results:
            for item in results["results"]:
                text = item.get("memory") or item.get("text", "")
                if text:
                    texts.append(text)
        elif isinstance(results, list):
            for item in results:
                text = item.get("memory") or item.get("text", "")
                if text:
                    texts.append(text)

        return texts
    except Exception as e:
        logger.warning("Failed to get all memories for user=%s: %s", user_id, e)
        return []
