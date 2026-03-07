"""Workflow state factory helpers."""

from src.agents.media_group.state import GraphState


def default_project_name(thread_id: str | None = None) -> str:
    """Build a stable project name from thread id or use default."""
    if thread_id:
        return f"proj_{thread_id[-8:]}"
    return "default_project"


def build_initial_state(
    user_request: str,
    *,
    reference_images: list[str] | None = None,
    reference_text: str = "",
    project_name: str | None = None,
    target_group: str = "media",
    direct_assignee: str = "",
) -> GraphState:
    """Create the full initial GraphState with consistent defaults."""
    return {
        "user_request": user_request,
        "reference_images": list(reference_images or []),
        "reference_text": reference_text,
        "current_script": "",
        "director_script_review": "",
        "showrunner_script_review": "",
        "script_review_count": 0,
        "user_script_feedback": "",
        "director_breakdown": "",
        "art_design_content": "",
        "voice_design_content": "",
        "director_production_review": "",
        "production_review_count": 0,
        "user_production_feedback": "",
        "final_storyboard": "",
        "director_storyboard_review": "",
        "storyboard_review_count": 0,
        "scoring_director": "",
        "scoring_writer": "",
        "scoring_art": "",
        "scoring_voice": "",
        "scoring_storyboard": "",
        "scoring_showrunner": "",
        "final_scoring_report": "",
        "art_feedback_images": [],
        "art_feedback_result": "",
        "refined_storyboard": "",
        "target_group": target_group,
        "direct_assignee": direct_assignee,
        "review_count": 0,
        "project_name": project_name or "default_project",
        "current_node": "",
    }
