"""System Prompt 加载（带 lru_cache 缓存）"""

import logging
from pathlib import Path
from functools import lru_cache

from src.services.prompt.file_io import safe_read_md

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
SYSTEM_PROMPTS_DIR = BASE_DIR / "system_prompts"

_AGENT_PATH_MAP = {
    "housekeeper": ("agents", "management", "housekeeper", "housekeeper.md"),
    "writer": ("agents", "media_group", "writer", "writer.md"),
    "director": ("agents", "media_group", "director", "director.md"),
    "showrunner": ("agents", "media_group", "showrunner", "showrunner.md"),
    "art_design": ("agents", "media_group", "art-design", "art-design.md"),
    "voice_design": ("agents", "media_group", "voice-design", "voice-design.md"),
    "storyboard": ("agents", "media_group", "storyboard-artist", "storyboard-artist.md"),
}

_SKILL_PATH_MAP = {
    "art-design": ("skills", "art-design-skill", "art-design-skill.md"),
    "compliance-review": ("skills", "compliance-review-skill", "compliance-review-skill.md"),
    "seedance-storyboard": ("skills", "seedance-storyboard-skill", "seedance-storyboard-skill.md"),
    "seedance-prompt-review": ("skills", "seedance-prompt-review-skill", "seedance-prompt-review-skill.md"),
    "production-scoring": ("skills", "production-scoring-skill", "production-scoring-skill.md"),
}


@lru_cache(maxsize=None)
def get_prompt(*path_parts: str) -> str:
    filepath = SYSTEM_PROMPTS_DIR.joinpath(*path_parts)
    if not filepath.exists():
        raise FileNotFoundError(f"System Prompt not found: {filepath}")
    content = safe_read_md(str(filepath))
    logger.debug("Loaded prompt: %s (%d chars)", filepath.name, len(content))
    return content


@lru_cache(maxsize=None)
def get_agent_prompt(role_name: str) -> str:
    parts = _AGENT_PATH_MAP.get(role_name)
    if not parts:
        raise ValueError(f"Unknown agent role: {role_name}")
    return get_prompt(*parts)


@lru_cache(maxsize=None)
def get_skill_prompt(skill_name: str) -> str:
    parts = _SKILL_PATH_MAP.get(skill_name)
    if not parts:
        raise ValueError(f"Unknown skill: {skill_name}")
    return get_prompt(*parts)
