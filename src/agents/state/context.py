"""Agent 上下文恢复 — 历史摘要查询"""

from src.agents.state.persistence import load_state


def get_agent_context(project: str, agent: str) -> str:
    state = load_state(project)
    sessions = state.get("sessions", {})

    agent_sessions = [
        (sid, s) for sid, s in sessions.items()
        if s["agent"] == agent
    ]
    agent_sessions.sort(key=lambda x: x[1].get("started_at", ""))

    if not agent_sessions:
        return ""

    lines = [f"[{agent} 历史上下文]"]
    for sid, s in agent_sessions[-3:]:
        icon = {"completed": "OK", "failed": "FAIL", "running": "..."}.get(s["status"], "?")
        lines.append(f"\n{icon} Session {sid}")
        if s.get("input_summary"):
            lines.append(f"  输入: {s['input_summary']}")
        if s.get("output_summary"):
            lines.append(f"  产出: {s['output_summary']}")
        if s.get("review_notes"):
            lines.append(f"  审核: {s['review_notes']}")

    return "\n".join(lines)


def get_phase_context(project: str, phase: str) -> str:
    state = load_state(project)
    sessions = state.get("sessions", {})

    phase_sessions = [
        (sid, s) for sid, s in sessions.items()
        if s["phase"] == phase and s["status"] == "completed"
    ]
    phase_sessions.sort(key=lambda x: x[1].get("started_at", ""))

    if not phase_sessions:
        return ""

    lines = [f"[{phase} 阶段产出汇总]"]
    for sid, s in phase_sessions:
        lines.append(f"\n  {s['agent']}: {s.get('output_summary', '(无摘要)')}")

    return "\n".join(lines)
