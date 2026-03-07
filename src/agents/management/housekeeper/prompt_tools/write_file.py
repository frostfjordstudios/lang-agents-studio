"""创建或覆写 system_prompts/ 下的文件"""

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
def write_prompt_file(file_path: str, content: str) -> str:
    """创建或覆写 system_prompts/ 下的文件。

    Args:
        file_path: 相对于 system_prompts/ 的文件路径。
        content: 文件内容。
    """
    target = _safe_path(file_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    from src.services.prompt.cache import clear_cache
    clear_cache()
    logger.info("Prompt written: %s", file_path)
    return f"已写入: system_prompts/{file_path} ({len(content)} 字符)"
