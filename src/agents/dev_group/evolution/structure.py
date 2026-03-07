"""列出项目目录结构"""

import os
from pathlib import Path
from langchain_core.tools import tool

from src.agents.dev_group.evolution.permissions_guard import check_evolve_permission, BASE_DIR


@tool("list_project_structure")
def list_project_structure(caller: str, directory: str = "src") -> str:
    """列出项目目录结构（用于架构分析）。"""
    err = check_evolve_permission(caller)
    if err:
        return err

    target_dir = BASE_DIR / directory
    if not target_dir.is_dir():
        return f"目录不存在: {directory}"

    lines = []
    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        rel = Path(root).relative_to(BASE_DIR)
        level = len(rel.parts) - len(Path(directory).parts)
        indent = "  " * level
        lines.append(f"{indent}{Path(root).name}/")
        for f in sorted(files):
            lines.append(f"{indent}  {f}")

    result = "\n".join(lines)
    if len(result) > 10000:
        result = result[:10000] + "\n\n[...截断]"
    return result
