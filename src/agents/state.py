"""LangGraph 状态定义 - 定义整个工作流的共享状态

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
    user_request: str               # 用户初始需求
    reference_images: list[str]     # 参考图片 Base64 Data URI 列表
    reference_text: str             # 参考文本资料

    # ── Phase 1: 剧本 ──
    current_script: str             # Writer 生成的剧本
    director_script_review: str     # Director 对剧本的专业审核 + 打分
    showrunner_script_review: str   # Showrunner 业务审核 + 合规审核
    script_review_count: int        # 剧本审核循环计数器（最大 3 次）
    user_script_feedback: str       # 用户对剧本的反馈

    # ── Phase 2: 导演拆解 ──
    director_breakdown: str         # 导演拆解产出（运镜/光线/风格/人物/道具/音效指令）

    # ── Phase 3: 内容生产 ──
    art_design_content: str         # 美术设计提示词
    voice_design_content: str       # 声音设计提示词
    director_production_review: str # Director 对美术+声音产出的审核
    production_review_count: int    # 生产审核循环计数器
    user_production_feedback: str   # 用户对生产内容的反馈

    # ── Phase 4: 分镜 ──
    final_storyboard: str           # 分镜师生成的最终提示词
    director_storyboard_review: str # Director 对分镜的审核 + 打分
    storyboard_review_count: int    # 分镜审核循环计数器

    # ── 终审：多角色加权评分 ──
    scoring_director: str           # 导演评分（含交叉验证）
    scoring_writer: str             # 编剧评分
    scoring_art: str                # 美术评分
    scoring_voice: str              # 声音评分
    scoring_storyboard: str         # 分镜师评分
    scoring_showrunner: str         # 制片评分
    final_scoring_report: str       # Showrunner 汇总的加权评分报告

    # ── 效果图反馈（工作流外） ──
    art_feedback_images: list[str]  # 用户回传的美术效果图
    art_feedback_result: str        # 美术效果图反馈/优化建议
    refined_storyboard: str         # 基于效果图优化后的分镜提示词

    # ── 元数据 ──
    project_name: str               # 项目名称（用于文件持久化）
    current_node: str               # 当前所处节点
