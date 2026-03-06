"""Compatibility exports for media group node functions.

The concrete implementations live under ``src.agents.media_group.phases``.
"""

from .phases.breakdown_phase import node_director_breakdown
from .phases.production_phase import (
    node_art_design,
    node_director_production_review,
    node_user_gate_production,
    node_voice_design,
)
from .phases.scoring_phase import (
    node_scoring_art,
    node_scoring_director,
    node_scoring_showrunner,
    node_scoring_storyboard,
    node_scoring_summary,
    node_scoring_voice,
    node_scoring_writer,
)
from .phases.script_phase import (
    node_director_script_review,
    node_showrunner_script_review,
    node_user_gate_script,
    node_writer,
)
from .phases.storyboard_phase import (
    node_director_storyboard_review,
    node_storyboard,
)
from .phases.helpers import (
    build_multimodal_message as _build_multimodal_message,
    save_output as _save_output,
)

__all__ = [
    "_build_multimodal_message",
    "_save_output",
    "node_writer",
    "node_director_script_review",
    "node_showrunner_script_review",
    "node_user_gate_script",
    "node_director_breakdown",
    "node_art_design",
    "node_voice_design",
    "node_director_production_review",
    "node_user_gate_production",
    "node_storyboard",
    "node_director_storyboard_review",
    "node_scoring_director",
    "node_scoring_writer",
    "node_scoring_art",
    "node_scoring_voice",
    "node_scoring_storyboard",
    "node_scoring_showrunner",
    "node_scoring_summary",
]
