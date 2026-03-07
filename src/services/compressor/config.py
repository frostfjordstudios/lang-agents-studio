"""压缩器配置数据 — 字段限制和阶段裁剪规则"""

FIELD_LIMITS: dict[str, int] = {
    "current_script": 8000,
    "director_breakdown": 6000,
    "final_storyboard": 8000,
    "art_design_content": 5000,
    "voice_design_content": 5000,
    "director_script_review": 2000,
    "showrunner_script_review": 2000,
    "director_production_review": 2000,
    "director_storyboard_review": 2000,
    "scoring_director": 1500,
    "scoring_writer": 1500,
    "scoring_art": 1500,
    "scoring_voice": 1500,
    "scoring_storyboard": 1500,
    "scoring_showrunner": 1500,
    "final_scoring_report": 3000,
    "user_script_feedback": 2000,
    "user_production_feedback": 2000,
    "user_request": 3000,
    "reference_text": 5000,
}

_SCORING_FIELDS = [
    "scoring_director", "scoring_writer", "scoring_art",
    "scoring_voice", "scoring_storyboard", "scoring_showrunner",
    "final_scoring_report",
]

PHASE_IRRELEVANT: dict[str, list[str]] = {
    "writer": _SCORING_FIELDS + ["art_feedback_images", "art_feedback_result", "refined_storyboard"],
    "director_script_review": _SCORING_FIELDS,
    "showrunner_script_review": _SCORING_FIELDS,
    "director_breakdown": ["director_script_review", "showrunner_script_review"] + _SCORING_FIELDS,
    "art_design": ["showrunner_script_review"] + _SCORING_FIELDS,
    "voice_design": ["showrunner_script_review"] + _SCORING_FIELDS,
    "storyboard": ["director_script_review", "showrunner_script_review"] + _SCORING_FIELDS,
}
