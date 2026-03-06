"""System Prompt 内存预加载管理器 (Memory Pre-loading)

使用 lru_cache 实现：整个进程生命周期内，每个 prompt 文件只发生一次磁盘 I/O。
后续所有调用直接从内存返回，零磁盘延迟。

支持两种加载方式：
  get_agent_prompt("writer")       -> agents/writer/writer.md
  get_skill_prompt("art-design")   -> skills/art-design-skill/art-design-skill.md
  get_prompt("agents", "director", "director.md")  -> 任意路径组合

安全读写：
  safe_read_md(file_path)   -> 绝对安全的 MD 文件读取（errors='replace'）
  safe_write_md(file_path, content) -> 安全写入

缓存失效：
  调用 clear_cache() 可手动清除缓存（管家修改 prompt 文件后需要触发）。
"""

import logging
from pathlib import Path
from functools import lru_cache

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SYSTEM_PROMPTS_DIR = BASE_DIR / "system_prompts"


# ── 绝对安全的文件读写 ────────────────────────────────────────────────

def safe_read_md(file_path: str) -> str:
    """绝对安全的 MD 文件读取，任何异常都不会崩溃。"""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except Exception as e:
        logger.error("safe_read_md failed: %s — %s", file_path, e)
        return f"读取失败: {e}"


def safe_write_md(file_path: str, content: str) -> bool:
    """安全写入 MD 文件，失败返回 False。"""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    except Exception as e:
        logger.error("safe_write_md failed: %s — %s", file_path, e)
        return False


# ── Prompt 加载（带缓存） ─────────────────────────────────────────────

@lru_cache(maxsize=None)
def get_prompt(*path_parts: str) -> str:
    """通用加载：按路径片段拼接并缓存。

    Example:
        get_prompt("agents", "writer", "writer.md")
        get_prompt("skills", "art-design-skill", "art-design-skill.md")
    """
    filepath = SYSTEM_PROMPTS_DIR.joinpath(*path_parts)
    if not filepath.exists():
        raise FileNotFoundError(f"System Prompt not found: {filepath}")
    content = safe_read_md(str(filepath))
    logger.debug("Loaded prompt into cache: %s (%d chars)", filepath.name, len(content))
    return content


@lru_cache(maxsize=None)
def get_agent_prompt(role_name: str) -> str:
    """加载 Agent 角色提示词。

    role_name 映射规则：
      "writer"      -> agents/writer/writer.md
      "director"    -> agents/director/director.md
      "showrunner"  -> agents/showrunner/showrunner.md
      "art_design"  -> agents/art-design/art-design.md
      "voice_design"-> agents/voice-design/voice-design.md
      "storyboard"  -> agents/storyboard-artist/storyboard-artist.md
      "housekeeper" -> agents/housekeeper/housekeeper.md
    """
    _AGENT_PATH_MAP = {
        "writer": ("agents", "writer", "writer.md"),
        "director": ("agents", "director", "director.md"),
        "showrunner": ("agents", "showrunner", "showrunner.md"),
        "art_design": ("agents", "art-design", "art-design.md"),
        "voice_design": ("agents", "voice-design", "voice-design.md"),
        "storyboard": ("agents", "storyboard-artist", "storyboard-artist.md"),
        "housekeeper": ("agents", "housekeeper", "housekeeper.md"),
    }
    parts = _AGENT_PATH_MAP.get(role_name)
    if not parts:
        raise ValueError(f"Unknown agent role: {role_name}")
    return get_prompt(*parts)


@lru_cache(maxsize=None)
def get_skill_prompt(skill_name: str) -> str:
    """加载 Skill 技能提示词。

    skill_name 映射规则：
      "art-design"          -> skills/art-design-skill/art-design-skill.md
      "compliance-review"   -> skills/compliance-review-skill/compliance-review-skill.md
      "seedance-storyboard" -> skills/seedance-storyboard-skill/seedance-storyboard-skill.md
      "seedance-prompt-review" -> skills/seedance-prompt-review-skill/seedance-prompt-review-skill.md
      "production-scoring"  -> skills/production-scoring-skill/production-scoring-skill.md
    """
    _SKILL_PATH_MAP = {
        "art-design": ("skills", "art-design-skill", "art-design-skill.md"),
        "compliance-review": ("skills", "compliance-review-skill", "compliance-review-skill.md"),
        "seedance-storyboard": ("skills", "seedance-storyboard-skill", "seedance-storyboard-skill.md"),
        "seedance-prompt-review": ("skills", "seedance-prompt-review-skill", "seedance-prompt-review-skill.md"),
        "production-scoring": ("skills", "production-scoring-skill", "production-scoring-skill.md"),
    }
    parts = _SKILL_PATH_MAP.get(skill_name)
    if not parts:
        raise ValueError(f"Unknown skill: {skill_name}")
    return get_prompt(*parts)


def clear_cache():
    """清除所有缓存（管家修改 prompt 文件后调用）。"""
    get_prompt.cache_clear()
    get_agent_prompt.cache_clear()
    get_skill_prompt.cache_clear()
    logger.info("Prompt cache cleared")


def preload_all():
    """预加载所有已知的 agent 和 skill prompt 到内存。

    在服务启动时调用，避免首次请求时的磁盘 I/O。
    """
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

    # Also load gate-rules and workflow
    for extra in [("agents", "showrunner", "gate-rules.md"),
                  ("agents", "workflow.md")]:
        try:
            get_prompt(*extra)
            loaded += 1
        except FileNotFoundError:
            pass

    logger.info("Preloaded %d prompt files into memory", loaded)
