"""Prompt 缓存清除"""

import logging
from src.services.prompt.loader import get_prompt, get_agent_prompt, get_skill_prompt

logger = logging.getLogger(__name__)


def clear_cache():
    get_prompt.cache_clear()
    get_agent_prompt.cache_clear()
    get_skill_prompt.cache_clear()
    logger.info("Prompt cache cleared")
