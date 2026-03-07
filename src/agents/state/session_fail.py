"""会话失败与重试处理"""

from src.agents.state.session import finish_session
from src.agents.state.persistence import load_state, save_state


def fail_session(project: str, session_id: str, error: str) -> None:
    finish_session(project, session_id, output_summary=f"ERROR: {error}", status="failed")


def increment_retry(project: str, session_id: str) -> int:
    state = load_state(project)
    session = state["sessions"].get(session_id)
    if not session:
        return 0
    session["retry_count"] = session.get("retry_count", 0) + 1
    save_state(project, state)
    return session["retry_count"]
