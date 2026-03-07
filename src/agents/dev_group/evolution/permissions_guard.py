"""进化权限守卫 — 校验调用者权限和路径安全"""

from pathlib import Path
from src.agents.organization import get_agent

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
_FORBIDDEN_PATTERNS = {".env", "credentials", "secret", "__pycache__", ".git"}


def check_evolve_permission(caller: str) -> str | None:
    """返回 None 表示通过，否则返回错误信息。"""
    agent = get_agent(caller)
    if not agent:
        return f"未知的调用者: {caller}，拒绝执行。"
    if not agent.can_evolve:
        return f"{agent.display_name}({caller}) 没有自我进化权限，仅 dev_group 可执行。"
    return None


def is_safe_path(file_path: str) -> bool:
    try:
        resolved = Path(file_path).resolve()
        if not str(resolved).startswith(str(BASE_DIR)):
            return False
        path_lower = str(resolved).lower()
        return not any(p in path_lower for p in _FORBIDDEN_PATTERNS)
    except Exception:
        return False
