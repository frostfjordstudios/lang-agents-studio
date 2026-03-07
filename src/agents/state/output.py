"""Agent 产出查询 — 获取最新会话和完整产出"""

from typing import Optional
from src.agents.state.persistence import load_state


def get_latest_session(project: str, agent: str) -> Optional[dict]:
    state = load_state(project)
    session_id = state.get("agent_latest", {}).get(agent)
    if not session_id:
        return None
    return state["sessions"].get(session_id)


def get_full_output(project: str, agent: str) -> str:
    session = get_latest_session(project, agent)
    if not session:
        return ""
    return session.get("key_output", "")
