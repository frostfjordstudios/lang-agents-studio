"""Static workflow runtime mappings."""

NODE_SITUATIONS: dict[str, str] = {
    "writer": "剧本初稿完成",
    "director_script_review": "导演剧本审核完成",
    "showrunner_script_review": "制片剧本审核完成",
    "director_breakdown": "导演拆解完成",
    "parallel_production": "美术与声音产出完成",
    "director_production_review": "导演生产审核完成",
    "storyboard": "分镜提示词完成",
    "director_storyboard_review": "导演分镜终审完成",
    "parallel_scoring": "多角色评分完成",
    "scoring_summary": "评分汇总完成",
    "save_outputs": "产出保存完成",
}

USER_GATE_TEMPLATES = {
    "user_gate_script": "🔔 剧本需要你的确认\n\n{summary}\n\n请回复「通过」继续，或发送修改意见。",
    "user_gate_production": "🔔 美术+声音需要你的确认\n\n{summary}\n\n请回复「通过」继续，或发送修改意见。",
}

NODE_TO_AGENT = {
    "writer": "writer",
    "director_script_review": "director",
    "showrunner_script_review": "showrunner",
    "user_gate_script": "housekeeper",
    "director_breakdown": "director",
    "parallel_production": "showrunner",
    "director_production_review": "director",
    "user_gate_production": "housekeeper",
    "storyboard": "storyboard",
    "director_storyboard_review": "director",
    "parallel_scoring": "showrunner",
    "scoring_summary": "showrunner",
    "save_outputs": "showrunner",
}

NODE_OUTPUT_FIELD = {
    "writer": "current_script",
    "director_script_review": "director_script_review",
    "showrunner_script_review": "showrunner_script_review",
    "director_breakdown": "director_breakdown",
    "parallel_production": "art_design_content",
    "director_production_review": "director_production_review",
    "storyboard": "final_storyboard",
    "director_storyboard_review": "director_storyboard_review",
    "parallel_scoring": "scoring_director",
    "scoring_summary": "final_scoring_report",
}

NODE_ACK_AGENTS: dict[str, list[str]] = {
    "writer": ["writer"],
    "director_script_review": ["director"],
    "showrunner_script_review": ["showrunner"],
    "user_gate_script": [],
    "director_breakdown": ["director"],
    "parallel_production": ["art_design", "voice_design"],
    "director_production_review": ["director"],
    "user_gate_production": [],
    "storyboard": ["storyboard"],
    "director_storyboard_review": ["director"],
    "parallel_scoring": ["director", "writer", "art_design", "voice_design", "storyboard", "showrunner"],
    "scoring_summary": ["showrunner"],
    "save_outputs": [],
}

NODE_PHASE = {
    "writer": "phase_1",
    "director_script_review": "phase_1",
    "showrunner_script_review": "phase_1",
    "user_gate_script": "phase_1",
    "director_breakdown": "phase_2",
    "parallel_production": "phase_3",
    "director_production_review": "phase_3",
    "user_gate_production": "phase_3",
    "storyboard": "phase_4",
    "director_storyboard_review": "phase_4",
    "parallel_scoring": "phase_4",
    "scoring_summary": "phase_4",
    "save_outputs": "phase_4",
}
