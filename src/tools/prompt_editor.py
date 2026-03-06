"""Prompt 文件编辑工具 - 管家专用

让管家 Agent 具备读取、修改、创建 system_prompts/ 下 agents 和 skills 文件的能力。
所有路径限制在 system_prompts/ 目录内，防止越权操作。
"""

import logging
from pathlib import Path
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
PROMPTS_DIR = BASE_DIR / "system_prompts"


def _safe_path(relative_path: str) -> Path:
    """确保路径在 system_prompts/ 内，防止路径遍历攻击。"""
    resolved = (PROMPTS_DIR / relative_path).resolve()
    if not str(resolved).startswith(str(PROMPTS_DIR.resolve())):
        raise ValueError(f"路径越权：{relative_path}")
    return resolved


@tool
def list_prompt_files(directory: str = "") -> str:
    """列出 system_prompts/ 下指定目录的所有文件。

    Args:
        directory: 相对于 system_prompts/ 的子目录路径，如 "agents/writer" 或 "skills"。
                   留空则列出根目录。
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


@tool
def read_prompt_file(file_path: str) -> str:
    """读取 system_prompts/ 下的文件内容。

    Args:
        file_path: 相对于 system_prompts/ 的文件路径，如 "agents/writer/writer.md"。
    """
    target = _safe_path(file_path)
    if not target.exists():
        return f"文件不存在: {file_path}"
    if not target.is_file():
        return f"不是文件: {file_path}"
    return target.read_text(encoding="utf-8", errors="replace")


@tool
def write_prompt_file(file_path: str, content: str) -> str:
    """创建或覆写 system_prompts/ 下的文件。

    Args:
        file_path: 相对于 system_prompts/ 的文件路径，如 "agents/new_agent/new_agent.md"。
        content: 文件内容。
    """
    target = _safe_path(file_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    # 清除 prompt 缓存，确保下次使用新内容
    from .prompt_manager import clear_cache
    clear_cache()
    logger.info("Prompt cache cleared after write: %s", file_path)
    return f"已写入: system_prompts/{file_path} ({len(content)} 字符)"


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
        return f"未找到匹配文本，替换失败。请检查 old_text 是否精确。"

    count = current.count(old_text)
    updated = current.replace(old_text, new_text)
    target.write_text(updated, encoding="utf-8")
    # 清除 prompt 缓存，确保下次使用新内容
    from .prompt_manager import clear_cache
    clear_cache()
    logger.info("Prompt cache cleared after edit: %s", file_path)
    return f"已替换 {count} 处: system_prompts/{file_path}"


PROMPT_EDITOR_TOOLS = [list_prompt_files, read_prompt_file, write_prompt_file, edit_prompt_file]
