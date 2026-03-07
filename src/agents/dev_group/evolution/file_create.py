"""在项目中创建新文件"""

import logging
from langchain_core.tools import tool

from src.agents.dev_group.evolution.permissions_guard import check_evolve_permission, is_safe_path, BASE_DIR

logger = logging.getLogger(__name__)


@tool("create_project_file")
def create_project_file(caller: str, file_path: str, content: str) -> str:
    """在项目中创建新文件。"""
    err = check_evolve_permission(caller)
    if err:
        return err

    full_path = BASE_DIR / file_path
    if not is_safe_path(str(full_path)):
        return f"路径不安全或超出项目范围: {file_path}"
    if full_path.exists():
        return f"文件已存在: {file_path}。如需修改请使用 patch_project_file。"

    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        logger.info("Evolution: created %s (%d chars)", file_path, len(content))
        return f"已创建 {file_path}（{len(content)} 字符）"
    except Exception as e:
        return f"创建失败: {e}"
