"""Prompt 预加载 — 服务启动时调用，避免首次请求磁盘 I/O"""

import logging
from src.services.prompt.loader import get_agent_prompt, get_skill_prompt, get_prompt

logger = logging.getLogger(__name__)


def preload_all():
    agents = ["writer", "director", "showrunner", "art_design",
              "voice_design", "storyboard", "housekeeper"]
    skills = ["art-design", "compliance-review", "seedance-storyboard",
              "seedance-prompt-review", "production-scoring"]

    loaded = 0
    for agent in agents:
        try:
            get_agent_prompt(agent)
            loaded += 1
        except FileNotFoundError as e:
            logger.warning("Preload skip: %s", e)

    for skill in skills:
        try:
            get_skill_prompt(skill)
            loaded += 1
        except FileNotFoundError as e:
            logger.warning("Preload skip: %s", e)

    for extra in [("agents", "media_group", "showrunner", "gate-rules.md"),
                  ("agents", "workflow.md")]:
        try:
            get_prompt(*extra)
            loaded += 1
        except FileNotFoundError:
            pass

    logger.info("Preloaded %d prompt files into memory", loaded)
