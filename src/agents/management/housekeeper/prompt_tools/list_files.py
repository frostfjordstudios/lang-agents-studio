"""列出 system_prompts/ 下的文件"""

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
def list_prompt_files(directory: str = "") -> str:
    """列出 system_prompts/ 下指定目录的所有文件。

    Args:
        directory: 相对于 system_prompts/ 的子目录路径，留空则列出根目录。
    """
    target = _safe_path(directory)
    if not target.exists():
        return f"目录不存在: {directory}"
    if not target.is_dir():
        return f"不是目录: {directory}"

    items = []
    for item in sorted(target.rglob("*")):
        if item.is_file():
            rel = item.relative_to(PROMPTS_DIR)
            size = item.stat().st_size
            items.append(f"  {rel}  ({size} bytes)")

    return f"system_prompts/{directory} 下的文件:\n" + "\n".join(items) if items else "目录为空"
