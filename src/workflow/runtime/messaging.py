"""Message rendering for node completion updates."""

from .constants import NODE_OUTPUT_FIELD, NODE_SITUATIONS, USER_GATE_TEMPLATES
from .status_updates import format_status_update
from .utils import normalize_output_text


def format_node_message(node_name: str, node_output: dict, state_values: dict) -> str:
    """Build a user-facing message after node completion."""
    project_name = str(state_values.get("project_name", "default_project"))
    gate_template = USER_GATE_TEMPLATES.get(node_name)
    if gate_template:
        summary = ""
        if node_name == "user_gate_script":
            director_review = str(state_values.get("director_script_review", ""))[:400]
            showrunner_review = str(state_values.get("showrunner_script_review", ""))[:400]
            script_preview = str(state_values.get("current_script", ""))[:300]
            summary = (
                f"📋 剧本摘要:\n{script_preview}...\n\n"
                f"🎬 Director:\n{director_review}\n\n"
                f"🎯 Showrunner:\n{showrunner_review}"
            )
        elif node_name == "user_gate_production":
            review = str(state_values.get("director_production_review", ""))[:500]
            summary = f"🎬 Director 审核:\n{review}"
        gate_status = "待你确认：剧本" if node_name == "user_gate_script" else "待你确认：美术与声音"
        return (
            f"{format_status_update(project_name, gate_status, node_name=node_name)}\n\n"
            f"{gate_template.format(summary=summary)}"
        )

    situation = NODE_SITUATIONS.get(node_name)
    if not situation:
        return ""

    output_field = NODE_OUTPUT_FIELD.get(node_name, "")
    key_output = normalize_output_text(node_output.get(output_field, "")) if output_field else ""
    excerpt = key_output[:200] if key_output else ""
    return format_status_update(
        project_name,
        situation,
        node_name=node_name,
        summary=excerpt,
    )
