"""获取用户的所有长期记忆"""

import logging
from src.services.memory.client import get_memory

logger = logging.getLogger(__name__)


def get_all_memories(user_id: str) -> list[str]:
    try:
        mem = get_memory()
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
