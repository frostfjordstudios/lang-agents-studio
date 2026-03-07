"""编辑 system_prompts/ 下的文件 — 精确替换"""

import logging
from pathlib import Path
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
PROMPTS_DIR = BASE_DIR / "system_prompts"


def _safe_path(relative_path: str) -> Path:
    resolved = (PROMPTS_DIR / relative_path).resolve()
    if not str(resolved).startswith(str(PROMPTS_DIR.resolve())):
        raise ValueError(f"路径越权：{relative_path}")
    return resolved


@tool
def edit_prompt_file(file_path: str, old_text: str, new_text: str) -> str:
    """编辑 system_prompts/ 下的文件，精确替换指定文本。

    Args:
        file_path: 相对于 system_prompts/ 的文件路径。
        old_text: 要被替换的原始文本（必须精确匹配）。
        new_text: 替换后的新文本。
    """
    target = _safe_path(file_path)
    if not target.exists():
        return f"文件不存在: {file_path}"

    current = target.read_text(encoding="utf-8", errors="replace")
    if old_text not in current:
        return "未找到匹配文本，替换失败。请检查 old_text 是否精确。"

    count = current.count(old_text)
    updated = current.replace(old_text, new_text)
    target.write_text(updated, encoding="utf-8")
    from src.services.prompt.cache import clear_cache
    clear_cache()
    logger.info("Prompt edited: %s", file_path)
    return f"已替换 {count} 处: system_prompts/{file_path}"
