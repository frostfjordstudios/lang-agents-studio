"""读取 system_prompts/ 下的文件"""

from pathlib import Path
from langchain_core.tools import tool

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
PROMPTS_DIR = BASE_DIR / "system_prompts"


def _safe_path(relative_path: str) -> Path:
    resolved = (PROMPTS_DIR / relative_path).resolve()
    if not str(resolved).startswith(str(PROMPTS_DIR.resolve())):
        raise ValueError(f"路径越权：{relative_path}")
    return resolved


@tool
def read_prompt_file(file_path: str) -> str:
    """读取 system_prompts/ 下的文件内容。

    Args:
        file_path: 相对于 system_prompts/ 的文件路径。
    """
    target = _safe_path(file_path)
    if not target.exists():
        return f"文件不存在: {file_path}"
    if not target.is_file():
        return f"不是文件: {file_path}"
    return target.read_text(encoding="utf-8", errors="replace")
