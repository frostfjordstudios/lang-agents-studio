"""LangGraph 状态定义 - 影视创作工作流的共享状态

工作流四阶段:
  Phase 1: 剧本创作 (Writer -> Director审核 -> Showrunner审核 -> 用户审核)
  Phase 2: 导演拆解 (Director 将剧本拆解为各部门的制作指令)
  Phase 3: 内容生产 (Art + Voice 基于导演拆解产出 -> Director审核 -> 用户审核)
  Phase 4: 分镜提示词 (Storyboard -> Director审核打分 -> Showrunner终审评分)
"""

from typing import TypedDict


class GraphState(TypedDict):
    """影视动态提示词生成系统的全局状态。"""

    # ── 用户输入 ──
    user_request: str
    reference_images: list[str]
    reference_text: str

    # ── Phase 1: 剧本 ──
    current_script: str
    director_script_review: str
    showrunner_script_review: str
    script_review_count: int
    user_script_feedback: str

    # ── Phase 2: 导演拆解 ──
    director_breakdown: str

    # ── Phase 3: 内容生产 ──
    art_design_content: str
    voice_design_content: str
    director_production_review: str
    production_review_count: int
    user_production_feedback: str

    # ── Phase 4: 分镜 ──
    final_storyboard: str
    director_storyboard_review: str
    storyboard_review_count: int

    # ── 终审：多角色加权评分 ──
    scoring_director: str
    scoring_writer: str
    scoring_art: str
    scoring_voice: str
    scoring_storyboard: str
    scoring_showrunner: str
    final_scoring_report: str

    # ── 效果图反馈（工作流外） ──
    art_feedback_images: list[str]
    art_feedback_result: str
    refined_storyboard: str

    # ── 联邦路由 ──
    target_group: str
    direct_assignee: str
    review_count: int

    # ── 元数据 ──
    project_name: str
    current_node: str
