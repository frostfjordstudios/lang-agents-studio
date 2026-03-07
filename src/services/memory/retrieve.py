"""从长期记忆检索"""

import logging
from src.services.memory.client import get_memory

logger = logging.getLogger(__name__)


def retrieve_memory(user_id: str, query: str, limit: int = 5) -> list[str]:
    try:
        mem = get_memory()
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

        logger.info("Retrieved %d memories for user=%s", len(texts), user_id)
        return texts
    except Exception as e:
        logger.warning("Failed to retrieve memory for user=%s: %s", user_id, e)
        return []
