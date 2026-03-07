"""影视组 LangGraph 计算图编排 - 四阶段工作流

Phase 1: Writer -> Director剧本审核 -> Showrunner审核 -> 用户门禁
Phase 2: Director剧本拆解
Phase 3: Art+Voice并行生产 -> Director审核 -> 用户门禁
Phase 4: Storyboard -> Director分镜审核(带重试) -> 多角色并行评分 -> 汇总 -> 保存
"""

import os
import sqlite3
from pathlib import Path

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

from src.agents.media_group.state import GraphState
from .nodes import (
    node_writer,
    node_director_script_review,
    node_showrunner_script_review,
    node_user_gate_script,
    node_director_breakdown,
    node_art_design,
    node_voice_design,
    node_director_production_review,
    node_user_gate_production,
    node_storyboard,
    node_director_storyboard_review,
    node_scoring_director,
    node_scoring_writer,
    node_scoring_art,
    node_scoring_voice,
    node_scoring_storyboard,
    node_scoring_showrunner,
    node_scoring_summary,
    _save_output,
)


# ── 条件分支函数 ─────────────────────────────────────────────────────

def should_continue_after_director_script(state: GraphState) -> str:
    """Director 剧本审核后：通过->Showrunner审核，不通过->退回Writer。

    强制熔断：review_count >= 3 时无论结果如何，强制通过。
    """
    review = state.get("director_script_review", "")
    count = state.get("script_review_count", 0)

    if "全部通过" in review or "✅" in review:
        return "showrunner_script_review"

    if count >= 3:
        return "showrunner_script_review"

    return "writer"


def should_continue_after_showrunner_script(state: GraphState) -> str:
    """Showrunner 剧本审核后：通过->用户门禁，不通过->退回Writer。

    强制熔断：script_review_count >= 3 时无论 Showrunner 意见如何，强制通过。
    """
    review = state.get("showrunner_script_review", "")
    count = state.get("script_review_count", 0)

    if "全部通过" in review or "✅ 全部通过" in review:
        return "user_gate_script"

    # 强制熔断：如果已经循环了 3 次，不再退回 Writer
    if count >= 3:
        return "user_gate_script"

    return "writer"


def should_continue_after_user_script(state: GraphState) -> str:
    """用户剧本审核后：通过->导演拆解，退回->Writer修改。"""
    feedback = state.get("user_script_feedback", "")

    if feedback and ("修改" in feedback or "不通过" in feedback or "重写" in feedback):
        return "writer"

    return "director_breakdown"


def should_continue_after_director_production(state: GraphState) -> str:
    """Director 生产审核后：通过->用户门禁，不通过->退回生产。

    强制熔断：production_review_count >= 3 时强制通过。
    """
    review = state.get("director_production_review", "")
    count = state.get("production_review_count", 0)

    if "全部通过" in review or "✅" in review:
        return "user_gate_production"

    if count >= 3:
        return "user_gate_production"

    return "parallel_production"


def should_continue_after_user_production(state: GraphState) -> str:
    """用户生产审核后：通过->分镜，退回->重新生产。"""
    feedback = state.get("user_production_feedback", "")

    if feedback and ("修改" in feedback or "不通过" in feedback or "重做" in feedback):
        return "parallel_production"

    return "storyboard"


def should_continue_after_director_storyboard(state: GraphState) -> str:
    """Director 分镜审核后：通过->多角色并行评分，不通过->退回Storyboard。

    强制熔断：storyboard_review_count >= 3 时强制通过。
    """
    review = state.get("director_storyboard_review", "")
    count = state.get("storyboard_review_count", 0)

    if "全部通过" in review or "✅" in review:
        return "parallel_scoring"

    if count >= 3:
        return "parallel_scoring"

    return "storyboard"


# ── 并行节点包装 ─────────────────────────────────────────────────────

def node_parallel_production(state: GraphState) -> dict:
    """并行执行 Art-Design 和 Voice-Design。"""
    art_result = node_art_design(state)
    voice_result = node_voice_design(state)

    return {
        "art_design_content": art_result["art_design_content"],
        "voice_design_content": voice_result["voice_design_content"],
        "current_node": "parallel_production",
    }


# ── 多角色并行评分包装 ─────────────────────────────────────────────

def node_parallel_scoring(state: GraphState) -> dict:
    """并行执行 6 个 Agent 的评分。"""
    d = node_scoring_director(state)
    w = node_scoring_writer(state)
    a = node_scoring_art(state)
    v = node_scoring_voice(state)
    sb = node_scoring_storyboard(state)
    sr = node_scoring_showrunner(state)

    return {
        "scoring_director": d["scoring_director"],
        "scoring_writer": w["scoring_writer"],
        "scoring_art": a["scoring_art"],
        "scoring_voice": v["scoring_voice"],
        "scoring_storyboard": sb["scoring_storyboard"],
        "scoring_showrunner": sr["scoring_showrunner"],
        "current_node": "parallel_scoring",
    }


# ── 保存节点 ─────────────────────────────────────────────────────────

def node_save_outputs(state: GraphState) -> dict:
    """将所有产出物保存到 projects/ 目录。"""
    project_name = state.get("project_name") or "default_project"
    episode = 1

    if state.get("current_script"):
        _save_output(project_name, episode, "剧本",
                     f"第{episode}集_文字剧本.md", state["current_script"])

    if state.get("director_breakdown"):
        _save_output(project_name, episode, "导演拆解",
                     f"第{episode}集_导演拆解.md", state["director_breakdown"])

    if state.get("art_design_content"):
        _save_output(project_name, episode, "美术设计",
                     f"第{episode}集_美术方案.md", state["art_design_content"])

    if state.get("voice_design_content"):
        _save_output(project_name, episode, "声音设计",
                     f"第{episode}集_声音方案.md", state["voice_design_content"])

    if state.get("final_storyboard"):
        _save_output(project_name, episode, "分镜",
                     f"第{episode}集_分镜提示词.md", state["final_storyboard"])

    if state.get("director_storyboard_review"):
        _save_output(project_name, episode, "审核记录",
                     "分镜终审.md", state["director_storyboard_review"])

    scoring_fields = {
        "scoring_director": "导演评分.md",
        "scoring_writer": "编剧评分.md",
        "scoring_art": "美术评分.md",
        "scoring_voice": "声音评分.md",
        "scoring_storyboard": "分镜评分.md",
        "scoring_showrunner": "制片评分.md",
    }
    for field, filename in scoring_fields.items():
        if state.get(field):
            _save_output(project_name, episode, "评分记录", filename, state[field])

    if state.get("final_scoring_report"):
        _save_output(project_name, episode, "评分记录",
                     "加权评分汇总.md", state["final_scoring_report"])

    return {"current_node": "save_outputs"}


# ── 构建计算图 ───────────────────────────────────────────────────────

def build_graph():
    """构建并返回完整的四阶段 LangGraph 工作流。"""
    workflow = StateGraph(GraphState)

    # Phase 1: 剧本
    workflow.add_node("writer", node_writer)
    workflow.add_node("director_script_review", node_director_script_review)
    workflow.add_node("showrunner_script_review", node_showrunner_script_review)
    workflow.add_node("user_gate_script", node_user_gate_script)

    # Phase 2: 拆解
    workflow.add_node("director_breakdown", node_director_breakdown)

    # Phase 3: 生产
    workflow.add_node("parallel_production", node_parallel_production)
    workflow.add_node("director_production_review", node_director_production_review)
    workflow.add_node("user_gate_production", node_user_gate_production)

    # Phase 4: 分镜 + 多角色评分
    workflow.add_node("storyboard", node_storyboard)
    workflow.add_node("director_storyboard_review", node_director_storyboard_review)
    workflow.add_node("parallel_scoring", node_parallel_scoring)
    workflow.add_node("scoring_summary", node_scoring_summary)
    workflow.add_node("save_outputs", node_save_outputs)

    # ── 入口 ──
    workflow.set_entry_point("writer")

    # ── Phase 1 ──
    workflow.add_edge("writer", "director_script_review")

    workflow.add_conditional_edges(
        "director_script_review",
        should_continue_after_director_script,
        {"showrunner_script_review": "showrunner_script_review", "writer": "writer"},
    )

    workflow.add_conditional_edges(
        "showrunner_script_review",
        should_continue_after_showrunner_script,
        {"user_gate_script": "user_gate_script", "writer": "writer"},
    )

    workflow.add_conditional_edges(
        "user_gate_script",
        should_continue_after_user_script,
        {"director_breakdown": "director_breakdown", "writer": "writer"},
    )

    # ── Phase 2 -> Phase 3 ──
    workflow.add_edge("director_breakdown", "parallel_production")

    # ── Phase 3 ──
    workflow.add_edge("parallel_production", "director_production_review")

    workflow.add_conditional_edges(
        "director_production_review",
        should_continue_after_director_production,
        {"user_gate_production": "user_gate_production", "parallel_production": "parallel_production"},
    )

    workflow.add_conditional_edges(
        "user_gate_production",
        should_continue_after_user_production,
        {"storyboard": "storyboard", "parallel_production": "parallel_production"},
    )

    # ── Phase 4 ──
    workflow.add_edge("storyboard", "director_storyboard_review")

    workflow.add_conditional_edges(
        "director_storyboard_review",
        should_continue_after_director_storyboard,
        {"parallel_scoring": "parallel_scoring", "storyboard": "storyboard"},
    )

    workflow.add_edge("parallel_scoring", "scoring_summary")
    workflow.add_edge("scoring_summary", "save_outputs")
    workflow.add_edge("save_outputs", END)

    # ── 持久化 ──
    if os.path.exists("/app"):
        db_path = "/app/data/checkpoints.sqlite"
    else:
        db_path = str(Path(__file__).resolve().parent.parent.parent.parent / "data" / "checkpoints.sqlite")

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    memory = SqliteSaver(conn)

    app = workflow.compile(
        checkpointer=memory,
        interrupt_before=["user_gate_script", "user_gate_production"],
    )

    return app
