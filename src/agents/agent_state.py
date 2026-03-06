"""Resumable Subagents — 持久化 Agent 交互状态

每个项目维护一份 .agent-state.json，记录 Showrunner 与各 Agent
之间的每次交互。当服务重启、上下文清除或 token 耗尽时，
Agent 可通过 session_id 恢复上下文继续工作。
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
PROJECTS_DIR = BASE_DIR / "projects"

_STATE_FILENAME = ".agent-state.json"

# 产出摘要最大长度（避免 JSON 过大）
_SUMMARY_MAX = 500
# 完整产出最大长度
_KEY_OUTPUT_MAX = 50000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate(text: str, max_len: int) -> str:
    if not text:
        return ""
    return text[:max_len] + ("..." if len(text) > max_len else "")


# ── State File I/O ──────────────────────────────────────────────────

def _state_path(project: str) -> Path:
    return PROJECTS_DIR / project / _STATE_FILENAME


def load_state(project: str) -> dict:
    """加载项目的 agent state，不存在则返回空骨架。"""
    path = _state_path(project)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load agent state for %s: %s", project, e)

    return {
        "project": project,
        "created_at": _now(),
        "updated_at": _now(),
        "current_phase": "",
        "sessions": {},
        "agent_latest": {},
    }


def save_state(project: str, state: dict) -> None:
    """持久化 agent state 到 JSON 文件。"""
    path = _state_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = _now()
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── Session 管理 ───────────────────────────────────────────────────

def begin_session(
    project: str,
    agent: str,
    phase: str,
    input_summary: str,
    parent_session: Optional[str] = None,
) -> str:
    """开始一个新的 Agent 会话，返回 session_id。"""
    state = load_state(project)
    session_id = f"{agent}_{uuid.uuid4().hex[:8]}"

    state["sessions"][session_id] = {
        "agent": agent,
        "phase": phase,
        "status": "running",
        "started_at": _now(),
        "finished_at": None,
        "input_summary": _truncate(input_summary, _SUMMARY_MAX),
        "output_summary": "",
        "key_output": "",
        "review_notes": "",
        "retry_count": 0,
        "parent_session": parent_session,
    }
    state["current_phase"] = phase
    state["agent_latest"][agent] = session_id

    save_state(project, state)
    logger.info("Session started: %s (agent=%s, project=%s)", session_id, agent, project)
    return session_id


def finish_session(
    project: str,
    session_id: str,
    output_summary: str,
    key_output: str = "",
    review_notes: str = "",
    status: str = "completed",
) -> None:
    """完成一个 Agent 会话。"""
    state = load_state(project)
    session = state["sessions"].get(session_id)
    if not session:
        logger.warning("Session %s not found in project %s", session_id, project)
        return

    session["status"] = status
    session["finished_at"] = _now()
    session["output_summary"] = _truncate(output_summary, _SUMMARY_MAX)
    session["key_output"] = _truncate(key_output, _KEY_OUTPUT_MAX)
    if review_notes:
        session["review_notes"] = _truncate(review_notes, _SUMMARY_MAX)

    save_state(project, state)
    logger.info("Session finished: %s (status=%s)", session_id, status)


def fail_session(project: str, session_id: str, error: str) -> None:
    """标记会话失败。"""
    finish_session(project, session_id, output_summary=f"ERROR: {error}", status="failed")


def increment_retry(project: str, session_id: str) -> int:
    """增加重试计数并返回新值。"""
    state = load_state(project)
    session = state["sessions"].get(session_id)
    if not session:
        return 0
    session["retry_count"] = session.get("retry_count", 0) + 1
    save_state(project, state)
    return session["retry_count"]


# ── 上下文恢复 ─────────────────────────────────────────────────────

def get_latest_session(project: str, agent: str) -> Optional[dict]:
    """获取某 Agent 最近一次会话的完整信息。"""
    state = load_state(project)
    session_id = state.get("agent_latest", {}).get(agent)
    if not session_id:
        return None
    return state["sessions"].get(session_id)


def get_agent_context(project: str, agent: str) -> str:
    """为 Agent 生成恢复上下文摘要。"""
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
        status_icon = {"completed": "✅", "failed": "❌", "running": "🔄"}.get(s["status"], "❓")
        lines.append(f"\n{status_icon} Session {sid}")
        if s.get("input_summary"):
            lines.append(f"  输入: {s['input_summary']}")
        if s.get("output_summary"):
            lines.append(f"  产出: {s['output_summary']}")
        if s.get("review_notes"):
            lines.append(f"  审核: {s['review_notes']}")

    return "\n".join(lines)


def get_phase_context(project: str, phase: str) -> str:
    """获取某个阶段所有 Agent 的产出摘要。"""
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
        lines.append(f"\n🔹 {s['agent']}: {s.get('output_summary', '(无摘要)')}")

    return "\n".join(lines)


def get_full_output(project: str, agent: str) -> str:
    """获取某 Agent 最新一次完整产出（key_output）。"""
    session = get_latest_session(project, agent)
    if not session:
        return ""
    return session.get("key_output", "")


def list_sessions(project: str) -> list[dict]:
    """列出项目所有 session 的摘要信息。"""
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
