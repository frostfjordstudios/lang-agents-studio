"""存入长期记忆"""

import logging
from src.services.memory.client import get_memory

logger = logging.getLogger(__name__)


def add_memory(user_id: str, content: str) -> bool:
    try:
        mem = get_memory()
        mem.add(content, user_id=user_id)
        logger.info("Memory added for user=%s: %s", user_id, content[:100])
        return True
    except Exception as e:
        logger.warning("Failed to add memory for user=%s: %s", user_id, e)
        return False
