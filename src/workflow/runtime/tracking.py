"""Node execution tracking helpers."""

import logging

from src.agents.agent_state import begin_session, finish_session

from .constants import NODE_OUTPUT_FIELD, NODE_PHASE, NODE_TO_AGENT
from .utils import normalize_output_text

logger = logging.getLogger(__name__)


def track_node(project: str, node_name: str, node_output: dict, input_summary: str = ""):
    """Record node execution into .agent-state.json."""
    agent = NODE_TO_AGENT.get(node_name)
    phase = NODE_PHASE.get(node_name, "")
    output_field = NODE_OUTPUT_FIELD.get(node_name, "")

    if not agent or not output_field:
        return

    key_output = normalize_output_text(node_output.get(output_field, ""))
    summary = key_output[:300] if key_output else "(no output)"

    try:
        session_id = begin_session(project, agent, phase, input_summary or node_name)
        finish_session(project, session_id, output_summary=summary, key_output=key_output)
    except Exception as exc:
        logger.warning("Agent state tracking failed for %s: %s", node_name, exc)
