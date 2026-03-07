"""Agent 会话生命周期 — 开始与完成"""

import uuid
import logging

from src.agents.state.persistence import (
    load_state, save_state, now_iso, truncate,
    _SUMMARY_MAX, _KEY_OUTPUT_MAX,
)

logger = logging.getLogger(__name__)


def begin_session(project, agent, phase, input_summary, parent_session=None) -> str:
    state = load_state(project)
    session_id = f"{agent}_{uuid.uuid4().hex[:8]}"

    state["sessions"][session_id] = {
        "agent": agent,
        "phase": phase,
        "status": "running",
        "started_at": now_iso(),
        "finished_at": None,
        "input_summary": truncate(input_summary, _SUMMARY_MAX),
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


def finish_session(project, session_id, output_summary,
                   key_output="", review_notes="", status="completed") -> None:
    state = load_state(project)
    session = state["sessions"].get(session_id)
    if not session:
        logger.warning("Session %s not found in project %s", session_id, project)
        return

    session["status"] = status
    session["finished_at"] = now_iso()
    session["output_summary"] = truncate(output_summary, _SUMMARY_MAX)
    session["key_output"] = truncate(key_output, _KEY_OUTPUT_MAX)
    if review_notes:
        session["review_notes"] = truncate(review_notes, _SUMMARY_MAX)

    save_state(project, state)
    logger.info("Session finished: %s (status=%s)", session_id, status)
