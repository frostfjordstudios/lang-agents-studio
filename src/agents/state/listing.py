"""会话列表查询"""

from src.agents.state.persistence import load_state


def list_sessions(project: str) -> list[dict]:
    state = load_state(project)
    result = []
    for sid, s in state.get("sessions", {}).items():
        result.append({
            "session_id": sid,
            "agent": s["agent"],
            "phase": s["phase"],
            "status": s["status"],
            "started_at": s.get("started_at"),
            "finished_at": s.get("finished_at"),
            "output_summary": s.get("output_summary", ""),
        })
    result.sort(key=lambda x: x.get("started_at", ""))
    return result
