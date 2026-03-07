"""读取项目源代码文件"""

from pathlib import Path
from langchain_core.tools import tool

from src.agents.dev_group.evolution.permissions_guard import check_evolve_permission, is_safe_path, BASE_DIR


@tool("read_project_file")
def read_project_file(caller: str, file_path: str) -> str:
    """读取项目内的源代码文件。

    Args:
        caller: 调用者的 agent name。
        file_path: 相对于项目根目录的路径。
    """
    err = check_evolve_permission(caller)
    if err:
        return err

    full_path = BASE_DIR / file_path
    if not is_safe_path(str(full_path)):
        return f"路径不安全或超出项目范围: {file_path}"
    if not full_path.exists():
        return f"文件不存在: {file_path}"

    try:
        content = full_path.read_text(encoding="utf-8", errors="replace")
        if len(content) > 50000:
            content = content[:50000] + "\n\n[...截断，原文超过 50000 字符]"
        return content
    except Exception as e:
        return f"读取失败: {e}"
