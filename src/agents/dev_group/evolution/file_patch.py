"""补丁式修改项目源代码"""

import logging
from langchain_core.tools import tool

from src.agents.dev_group.evolution.permissions_guard import check_evolve_permission, is_safe_path, BASE_DIR

logger = logging.getLogger(__name__)


@tool("patch_project_file")
def patch_project_file(caller: str, file_path: str, old_text: str, new_text: str) -> str:
    """对项目文件进行补丁式修改（查找替换）。"""
    err = check_evolve_permission(caller)
    if err:
        return err

    full_path = BASE_DIR / file_path
    if not is_safe_path(str(full_path)):
        return f"路径不安全或超出项目范围: {file_path}"
    if not full_path.exists():
        return f"文件不存在: {file_path}"

    try:
        content = full_path.read_text(encoding="utf-8")
    except Exception as e:
        return f"读取失败: {e}"

    count = content.count(old_text)
    if count == 0:
        return "未找到要替换的文本片段。"
    if count > 1:
        return f"old_text 匹配了 {count} 处，请提供更多上下文使其唯一。"

    new_content = content.replace(old_text, new_text, 1)
    try:
        full_path.write_text(new_content, encoding="utf-8")
        logger.info("Evolution: patched %s (-%d/+%d)", file_path, len(old_text), len(new_text))
        return f"已修改 {file_path}（{len(old_text)} -> {len(new_text)} 字符）"
    except Exception as e:
        return f"写入失败: {e}"
