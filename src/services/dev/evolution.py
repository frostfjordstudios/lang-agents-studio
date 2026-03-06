"""开发组自我进化工具箱 (Evolution Toolbox)

仅限拥有 can_evolve 权限的 Agent（dev_group）使用。
提供以下能力：
  1. 更新 Agent System Prompt
  2. 读取项目源代码
  3. 修改项目源代码（补丁式）
  4. 创建新文件
  5. 列出项目结构

所有写操作都有权限守卫 + 安全校验。
"""

import logging
import os
from pathlib import Path
from langchain_core.tools import tool

from src.core.prompt_manager import safe_write_md, safe_read_md, clear_cache
from src.core.registry import AGENT_REGISTRY, get_agent

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
PROMPTS_DIR = BASE_DIR / "system_prompts"
SRC_DIR = BASE_DIR / "src"

# 禁止修改的路径模式（安全红线）
_FORBIDDEN_PATTERNS = {".env", "credentials", "secret", "__pycache__", ".git"}


# ── 权限守卫 ──────────────────────────────────────────────────────────

def _check_evolve_permission(caller: str) -> str | None:
    """检查调用者是否有进化权限。返回 None 表示通过，否则返回错误信息。"""
    agent = get_agent(caller)
    if not agent:
        return f"未知的调用者: {caller}，拒绝执行。"
    if not agent.can_evolve:
        return f"{agent.display_name}({caller}) 没有自我进化权限（can_evolve=False），仅 dev_group 可执行此操作。"
    return None


def _is_safe_path(file_path: str) -> bool:
    """校验路径是否安全（在项目目录内且不命中禁止模式）。"""
    try:
        resolved = Path(file_path).resolve()
        if not str(resolved).startswith(str(BASE_DIR)):
            return False
        path_lower = str(resolved).lower()
        return not any(p in path_lower for p in _FORBIDDEN_PATTERNS)
    except Exception:
        return False


# ── 工具 1: 更新 Agent System Prompt ─────────────────────────────────

@tool("update_agent_system_prompt")
def update_agent_system_prompt(caller: str, agent_name: str, new_rules_content: str) -> str:
    """更新指定 Agent 的 System Prompt 文件。

    Args:
        caller: 调用者的 agent name（用于权限校验）。
        agent_name: 目标 Agent 名称。
        new_rules_content: 新的完整 Markdown 内容。
    """
    err = _check_evolve_permission(caller)
    if err:
        return err

    target_agent = get_agent(agent_name)
    if not target_agent or not target_agent.prompt_path:
        available = [a.name for a in AGENT_REGISTRY.values() if a.prompt_path]
        return f"未知或无 prompt 的 Agent: {agent_name}。可选: {', '.join(available)}"

    if not new_rules_content or not new_rules_content.strip():
        return "内容不能为空，拒绝写入。"

    target = PROMPTS_DIR / target_agent.prompt_path

    if target.exists():
        old_len = len(safe_read_md(str(target)))
        logger.info("Evolution: overwriting %s prompt (old=%d, new=%d chars)",
                     agent_name, old_len, len(new_rules_content))
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Evolution: creating new prompt for %s", agent_name)

    ok = safe_write_md(str(target), new_rules_content)
    if not ok:
        return f"写入失败: {target_agent.prompt_path}"

    clear_cache()
    return f"已更新 {agent_name} 的 System Prompt ({len(new_rules_content)} 字符)，缓存已清除。"


# ── 工具 2: 读取项目源代码 ───────────────────────────────────────────

@tool("read_project_file")
def read_project_file(caller: str, file_path: str) -> str:
    """读取项目内的源代码文件。

    Args:
        caller: 调用者的 agent name。
        file_path: 相对于项目根目录的路径，如 "src/core/registry.py"。
    """
    err = _check_evolve_permission(caller)
    if err:
        return err

    full_path = BASE_DIR / file_path
    if not _is_safe_path(str(full_path)):
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


# ── 工具 3: 修改项目源代码（补丁式） ────────────────────────────────

@tool("patch_project_file")
def patch_project_file(caller: str, file_path: str, old_text: str, new_text: str) -> str:
    """对项目文件进行补丁式修改（查找替换）。

    Args:
        caller: 调用者的 agent name。
        file_path: 相对于项目根目录的路径。
        old_text: 要替换的原始文本片段（必须唯一匹配）。
        new_text: 替换后的新文本。
    """
    err = _check_evolve_permission(caller)
    if err:
        return err

    full_path = BASE_DIR / file_path
    if not _is_safe_path(str(full_path)):
        return f"路径不安全或超出项目范围: {file_path}"

    if not full_path.exists():
        return f"文件不存在: {file_path}"

    try:
        content = full_path.read_text(encoding="utf-8")
    except Exception as e:
        return f"读取失败: {e}"

    count = content.count(old_text)
    if count == 0:
        return "未找到要替换的文本片段，请确认 old_text 完全匹配。"
    if count > 1:
        return f"old_text 匹配了 {count} 处，请提供更多上下文使其唯一。"

    new_content = content.replace(old_text, new_text, 1)

    try:
        full_path.write_text(new_content, encoding="utf-8")
        logger.info("Evolution: patched %s (-%d/+%d chars)",
                     file_path, len(old_text), len(new_text))
        return f"已修改 {file_path}（替换 {len(old_text)} -> {len(new_text)} 字符）。"
    except Exception as e:
        return f"写入失败: {e}"


# ── 工具 4: 创建新文件 ──────────────────────────────────────────────

@tool("create_project_file")
def create_project_file(caller: str, file_path: str, content: str) -> str:
    """在项目中创建新文件。

    Args:
        caller: 调用者的 agent name。
        file_path: 相对于项目根目录的路径。
        content: 文件内容。
    """
    err = _check_evolve_permission(caller)
    if err:
        return err

    full_path = BASE_DIR / file_path
    if not _is_safe_path(str(full_path)):
        return f"路径不安全或超出项目范围: {file_path}"

    if full_path.exists():
        return f"文件已存在: {file_path}。如需修改请使用 patch_project_file。"

    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        logger.info("Evolution: created %s (%d chars)", file_path, len(content))
        return f"已创建 {file_path}（{len(content)} 字符）。"
    except Exception as e:
        return f"创建失败: {e}"


# ── 工具 5: 列出项目结构 ────────────────────────────────────────────

@tool("list_project_structure")
def list_project_structure(caller: str, directory: str = "src") -> str:
    """列出项目目录结构（用于架构分析）。

    Args:
        caller: 调用者的 agent name。
        directory: 相对于项目根目录的子目录，默认 "src"。
    """
    err = _check_evolve_permission(caller)
    if err:
        return err

    target_dir = BASE_DIR / directory
    if not target_dir.is_dir():
        return f"目录不存在: {directory}"

    lines = []
    for root, dirs, files in os.walk(target_dir):
        # 跳过 __pycache__
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


# ── 工具集合导出 ──────────────────────────────────────────────────────

EVOLUTION_TOOLS = [
    update_agent_system_prompt,
    read_project_file,
    patch_project_file,
    create_project_file,
    list_project_structure,
]
