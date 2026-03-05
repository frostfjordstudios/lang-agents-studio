"""LangGraph 状态定义 - 定义整个工作流的共享状态"""

from typing import TypedDict


class GraphState(TypedDict):
    """影视动态提示词生成系统的全局状态。

    所有节点通过读写此状态进行数据传递。
    """

    user_request: str           # 用户初始需求
    current_script: str         # 编剧生成的剧本
    director_review: str        # 导演的三步审核意见
    review_count: int           # 审核循环计数器（最大 3 次退回）
    user_feedback: str          # 用户门禁点的反馈意见
    art_design_content: str     # 美术设计提示词
    voice_design_content: str   # 声音设计提示词
    final_storyboard: str       # 最终分镜提示词
    current_node: str           # 当前所处节点
