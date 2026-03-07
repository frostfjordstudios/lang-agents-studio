"""联邦制主图 — 管家路由 -> media_group / dev_group

入口: housekeeper_router 分析意图
  -> media: 转入影视组完整工作流
  -> dev: 转入开发组架构分析
"""

import os
import sqlite3
from pathlib import Path

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

from src.agents.media_group.state import GraphState
from src.agents.management.housekeeper.router import node_housekeeper_router
from src.agents.media_group.workflow import (
    build_graph as build_media_graph,
)
from src.agents.dev_group.workflow import build_dev_graph


# ── 路由函数 ─────────────────────────────────────────────────────────

def _route_after_housekeeper(state: GraphState) -> str:
    """根据 target_group 路由到对应子图。"""
    target = state.get("target_group", "dev")
    if target in ("studio", "media"):
        return "media_workflow"
    elif target == "dev":
        return "dev_workflow"
    return END


# ── 子图节点包装 ─────────────────────────────────────────────────────

_media_app = None
_dev_app = None


def _get_media_app():
    global _media_app
    if _media_app is None:
        _media_app = build_media_graph()
    return _media_app


def _get_dev_app():
    global _dev_app
    if _dev_app is None:
        _dev_app = build_dev_graph()
    return _dev_app


def node_media_workflow(state: GraphState) -> dict:
    """影视组子图包装节点 — 调用完整的四阶段工作流。"""
    # 注意：实际使用时 server.py 会直接调用 build_media_graph 进行 streaming，
    # 此节点用于 main_graph 的结构完整性和未来自动化场景。
    return {"current_node": "media_workflow_entry"}


def node_dev_workflow(state: GraphState) -> dict:
    """开发组子图包装节点。"""
    app = _get_dev_app()
    result = app.invoke(state)
    return {"current_node": result.get("current_node", "dev_complete")}


# ── 构建主图 ─────────────────────────────────────────────────────────

def build_main_graph():
    """构建联邦制主图: housekeeper -> media/dev。"""
    workflow = StateGraph(GraphState)

    workflow.add_node("housekeeper_router", node_housekeeper_router)
    workflow.add_node("media_workflow", node_media_workflow)
    workflow.add_node("dev_workflow", node_dev_workflow)

    workflow.set_entry_point("housekeeper_router")

    workflow.add_conditional_edges(
        "housekeeper_router",
        _route_after_housekeeper,
        {
            "media_workflow": "media_workflow",
            "dev_workflow": "dev_workflow",
            END: END,
        },
    )

    workflow.add_edge("media_workflow", END)
    workflow.add_edge("dev_workflow", END)

    # ── 持久化 ──
    if os.path.exists("/app"):
        db_path = "/app/data/main_checkpoints.sqlite"
    else:
        db_path = str(Path(__file__).resolve().parent.parent / "data" / "main_checkpoints.sqlite")

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    memory = SqliteSaver(conn)

    return workflow.compile(checkpointer=memory)
