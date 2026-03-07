"""开发组子图 — 架构分析 + Agent 进化

目前仅包含 architect 节点，后续可扩展 evolution 自动化流程。
"""

from langgraph.graph import StateGraph, END

from src.agents.media_group.state import GraphState
from .nodes import node_architect


def build_dev_graph():
    """构建开发组子图。"""
    workflow = StateGraph(GraphState)
    workflow.add_node("architect", node_architect)
    workflow.set_entry_point("architect")
    workflow.add_edge("architect", END)

    return workflow.compile()
