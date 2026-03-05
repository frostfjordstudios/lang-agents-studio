"""LangGraph 计算图编排 - 实现 workflow.md 定义的完整工作流。

核心流程：
  Writer → Director Review → (条件分支: 通过/退回)
  → 用户门禁点 (Human-in-the-Loop)
  → Art-Design + Voice-Design (并行)
  → Storyboard → Director Final Review → 交付
"""

import os
from pathlib import Path

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

from .state import GraphState
from .nodes import (
    node_writer,
    node_director_review,
    node_user_gate,
    node_art_design,
    node_voice_design,
    node_storyboard,
    node_director_final_review,
    _save_output,
)


# ── 条件分支函数 ─────────────────────────────────────────────────────

def should_continue_after_review(state: GraphState) -> str:
    """Director 剧本审核后的条件分支。

    - 审核通过 → 进入用户门禁点
    - 审核不通过且 review_count < 3 → 退回 Writer
    - 审核不通过且 review_count >= 3 → 进入用户门禁点（报告僵局）
    """
    review = state.get("director_review", "")
    review_count = state.get("review_count", 0)

    # 检查审核结论中是否包含"全部通过"标识
    if "全部通过" in review or "✅" in review.split("综合结论")[-1] if "综合结论" in review else False:
        return "user_gate"

    if review_count < 3:
        return "writer"

    # 超过 3 次循环，进入门禁让用户裁决
    return "user_gate"


def should_continue_after_user(state: GraphState) -> str:
    """用户门禁点后的条件分支。

    - 用户确认通过 → 进入并行设计阶段
    - 用户要求修改 → 退回 Writer
    """
    feedback = state.get("user_feedback", "")

    if feedback and ("修改" in feedback or "不通过" in feedback or "重写" in feedback):
        return "writer"

    return "parallel_design"


# ── 并行节点包装 ─────────────────────────────────────────────────────

def node_parallel_design(state: GraphState) -> dict:
    """并行执行 Art-Design 和 Voice-Design。

    LangGraph 原生支持通过 fan-out/fan-in 实现并行，
    这里用顺序调用模拟，后续可替换为真正的并行子图。
    """
    art_result = node_art_design(state)
    voice_result = node_voice_design(state)

    return {
        "art_design_content": art_result["art_design_content"],
        "voice_design_content": voice_result["voice_design_content"],
        "current_node": "parallel_design",
    }


# ── 保存节点 ─────────────────────────────────────────────────────────

def node_save_outputs(state: GraphState) -> dict:
    """将所有产出物保存到 output_projects/ 目录。"""
    # 从 user_request 中提取项目名和集数（简化处理）
    project_name = "default_project"
    episode = 1

    if state.get("current_script"):
        _save_output(project_name, episode, "剧本",
                     f"第{episode}集_文字剧本.md", state["current_script"])

    if state.get("art_design_content"):
        _save_output(project_name, episode, "美术设计",
                     f"第{episode}集_美术方案.md", state["art_design_content"])

    if state.get("voice_design_content"):
        _save_output(project_name, episode, "声音设计",
                     f"第{episode}集_声音方案.md", state["voice_design_content"])

    if state.get("final_storyboard"):
        _save_output(project_name, episode, "分镜",
                     f"第{episode}集_分镜提示词.md", state["final_storyboard"])

    if state.get("director_review"):
        _save_output(project_name, episode, "审核记录",
                     "分镜终审.md", state["director_review"])

    return {"current_node": "save_outputs"}


# ── 构建计算图 ───────────────────────────────────────────────────────

def build_graph():
    """构建并返回完整的 LangGraph 工作流。

    流程：
      writer → director_review → (条件) → user_gate → (条件)
      → parallel_design → storyboard → director_final_review
      → save_outputs → END
    """
    workflow = StateGraph(GraphState)

    # ── 添加节点 ──
    workflow.add_node("writer", node_writer)
    workflow.add_node("director_review", node_director_review)
    workflow.add_node("user_gate", node_user_gate)
    workflow.add_node("parallel_design", node_parallel_design)
    workflow.add_node("storyboard", node_storyboard)
    workflow.add_node("director_final_review", node_director_final_review)
    workflow.add_node("save_outputs", node_save_outputs)

    # ── 设置入口 ──
    workflow.set_entry_point("writer")

    # ── 添加边 ──
    workflow.add_edge("writer", "director_review")

    # Director 审核后的条件分支
    workflow.add_conditional_edges(
        "director_review",
        should_continue_after_review,
        {
            "user_gate": "user_gate",
            "writer": "writer",
        },
    )

    # 用户门禁后的条件分支
    workflow.add_conditional_edges(
        "user_gate",
        should_continue_after_user,
        {
            "parallel_design": "parallel_design",
            "writer": "writer",
        },
    )

    # 并行设计 → 分镜 → 终审 → 保存 → 结束
    workflow.add_edge("parallel_design", "storyboard")
    workflow.add_edge("storyboard", "director_final_review")
    workflow.add_edge("director_final_review", "save_outputs")
    workflow.add_edge("save_outputs", END)

    # ── 持久化检查点（SQLite） ──
    # 云端: /app/data/checkpoints.sqlite
    # 本地: data/checkpoints.sqlite（相对于项目根）
    if os.path.exists("/app"):
        db_path = "/app/data/checkpoints.sqlite"
    else:
        db_path = str(Path(__file__).resolve().parent.parent / "data" / "checkpoints.sqlite")

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    checkpointer = SqliteSaver.from_conn_string(db_path)

    # interrupt_before="user_gate" 会在进入门禁节点前暂停，
    # 等待外部输入 user_feedback 后 resume
    app = workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=["user_gate"],
    )

    return app


# ── 运行入口 ─────────────────────────────────────────────────────────

def run_interactive(user_request: str):
    """交互式运行工作流，在门禁点等待用户终端输入。

    Args:
        user_request: 用户的创作需求描述
    """
    app = build_graph()

    # 初始状态
    initial_state = {
        "user_request": user_request,
        "current_script": "",
        "director_review": "",
        "review_count": 0,
        "user_feedback": "",
        "art_design_content": "",
        "voice_design_content": "",
        "final_storyboard": "",
        "current_node": "",
    }

    config = {"configurable": {"thread_id": "session-1"}}

    print("=" * 60)
    print("  影视动态提示词生成系统 - LangGraph Studio")
    print("=" * 60)
    print(f"\n📝 用户需求：{user_request}\n")
    print("🚀 开始执行工作流...\n")

    # 第一轮运行：Writer → Director Review → (暂停在 user_gate 前)
    for event in app.stream(initial_state, config):
        for node_name, node_output in event.items():
            current = node_output.get("current_node", node_name)
            print(f"  ✅ 节点完成：{current}")

    # 获取当前状态，展示审核结果
    current_state = app.get_state(config)
    state_values = current_state.values

    print("\n" + "=" * 60)
    print("  ⏳ 用户确认门禁点 (GATE)")
    print("=" * 60)
    print(f"\n📋 剧本摘要：\n{state_values.get('current_script', '')[:500]}...\n")
    print(f"🎬 Director 审核意见：\n{state_values.get('director_review', '')[:500]}...\n")

    # Human-in-the-Loop：等待用户终端输入
    while True:
        user_input = input("\n请输入您的反馈（输入 '通过' 继续，或输入修改意见）：\n> ").strip()
        if user_input:
            break
        print("⚠️ 请输入有效内容")

    # 更新状态并恢复执行
    app.update_state(config, {"user_feedback": user_input})

    print(f"\n📌 用户反馈：{user_input}")
    print("🔄 恢复工作流执行...\n")

    # 第二轮运行：从 user_gate 恢复
    for event in app.stream(None, config):
        for node_name, node_output in event.items():
            current = node_output.get("current_node", node_name)
            print(f"  ✅ 节点完成：{current}")

    print("\n" + "=" * 60)
    print("  🎉 工作流执行完毕！产出物已保存至 projects/")
    print("=" * 60)
