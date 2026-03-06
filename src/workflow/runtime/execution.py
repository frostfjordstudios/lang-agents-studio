"""Workflow run/resume orchestration."""

import logging

from src.tools.lark.msg.messaging import send_text
from src.tools.lark.msg.multi_bot import send_as_agent
from src.workflow.state_factory import build_initial_state, default_project_name

from .constants import NODE_ACK_AGENTS, NODE_TO_AGENT
from .final_output import send_final_output
from .messaging import format_node_message
from .status_updates import format_task_received
from .tracking import track_node

logger = logging.getLogger(__name__)


def _handle_node_completion(
    *,
    node_name: str,
    node_output: dict,
    chat_id: str,
    thread_id: str,
    thread_state: dict,
    project_name: str,
    state_values: dict,
    input_summary: str,
):
    current = node_output.get("current_node", node_name)
    thread_state[thread_id]["last_node"] = current
    logger.info("Node completed: %s (thread=%s)", current, thread_id)

    for ack_agent in NODE_ACK_AGENTS.get(current, []):
        send_as_agent(ack_agent, chat_id, format_task_received(project_name, current))

    message = format_node_message(current, node_output, state_values or {})
    if message:
        agent = NODE_TO_AGENT.get(current, "housekeeper")
        send_as_agent(agent, chat_id, message)

    track_node(project_name, current, node_output, input_summary)


def _finalize_flow_status(graph_app, config: dict, thread_id: str, thread_state: dict, chat_id: str):
    state = graph_app.get_state(config)
    if state.next:
        thread_state[thread_id]["status"] = "paused"
        logger.info("Workflow paused before: %s (thread=%s)", state.next, thread_id)
        return

    thread_state[thread_id]["status"] = "finished"
    logger.info("Workflow finished (thread=%s)", thread_id)
    send_final_output(graph_app, chat_id, config)


def run_workflow(graph_app, chat_id: str, thread_id: str, user_request: str, thread_refs: dict, thread_state: dict):
    """Start a new workflow run."""
    refs = thread_refs.pop(thread_id, {"text": "", "images": []})
    project_name = thread_state.get(thread_id, {}).get("project", default_project_name(thread_id))
    thread_state[thread_id] = {
        "status": "running",
        "chat_id": chat_id,
        "last_node": "",
        "project": project_name,
    }

    send_as_agent("housekeeper", chat_id, "🚀 创作工作流已启动\n\n管家正在协调各 Agent 执行任务。")
    initial_state = build_initial_state(
        user_request,
        reference_images=refs.get("images", []),
        reference_text=refs.get("text", ""),
        project_name=project_name,
        target_group="media",
    )
    config = {"configurable": {"thread_id": thread_id}}

    try:
        accumulated_state = dict(initial_state)
        for event in graph_app.stream(initial_state, config):
            if thread_state.get(thread_id, {}).get("status") == "stopped":
                logger.info("Workflow stopped by user (thread=%s)", thread_id)
                send_text(chat_id, "⏹️ 工作流已停止。")
                return

            for node_name, node_output in event.items():
                if not isinstance(node_output, dict):
                    continue
                accumulated_state.update(node_output)
                _handle_node_completion(
                    node_name=node_name,
                    node_output=node_output,
                    chat_id=chat_id,
                    thread_id=thread_id,
                    thread_state=thread_state,
                    project_name=project_name,
                    state_values=accumulated_state,
                    input_summary=user_request[:200],
                )

        _finalize_flow_status(graph_app, config, thread_id, thread_state, chat_id)

    except GeneratorExit:
        logger.warning("Workflow GeneratorExit (thread=%s)", thread_id)
        thread_state[thread_id]["status"] = "error"
        send_text(chat_id, "⚠️ 工作流被中断，请重新发送需求。")
    except Exception as exc:
        logger.error("Workflow error (thread=%s): %s", thread_id, exc, exc_info=True)
        thread_state[thread_id]["status"] = "error"
        send_text(chat_id, f"❌ 工作流执行出错: {type(exc).__name__}: {str(exc)[:200]}")


def _apply_user_feedback(graph_app, config: dict, user_feedback: str):
    state = graph_app.get_state(config)
    next_nodes = state.next if state.next else ()
    if "user_gate_script" in next_nodes:
        graph_app.update_state(config, {"user_script_feedback": user_feedback})
    elif "user_gate_production" in next_nodes:
        graph_app.update_state(config, {"user_production_feedback": user_feedback})
    else:
        graph_app.update_state(config, {"user_script_feedback": user_feedback})


def resume_workflow(graph_app, chat_id: str, thread_id: str, user_feedback: str, thread_state: dict):
    """Resume a paused workflow."""
    config = {"configurable": {"thread_id": thread_id}}
    _apply_user_feedback(graph_app, config, user_feedback)

    project_name = thread_state.get(thread_id, {}).get("project", default_project_name(thread_id))
    thread_state[thread_id] = {
        "status": "running",
        "chat_id": chat_id,
        "last_node": "",
        "project": project_name,
    }

    send_as_agent("housekeeper", chat_id, "🔄 收到反馈，工作流恢复中...")

    try:
        for event in graph_app.stream(None, config):
            if thread_state.get(thread_id, {}).get("status") == "stopped":
                logger.info("Workflow stopped by user (thread=%s)", thread_id)
                send_text(chat_id, "⏹️ 工作流已停止。")
                return

            for node_name, node_output in event.items():
                if not isinstance(node_output, dict):
                    continue

                full_state = graph_app.get_state(config).values or {}
                _handle_node_completion(
                    node_name=node_name,
                    node_output=node_output,
                    chat_id=chat_id,
                    thread_id=thread_id,
                    thread_state=thread_state,
                    project_name=project_name,
                    state_values=full_state,
                    input_summary=f"resume: {user_feedback[:100]}",
                )

        _finalize_flow_status(graph_app, config, thread_id, thread_state, chat_id)

    except GeneratorExit:
        logger.warning("Resume GeneratorExit (thread=%s)", thread_id)
        thread_state[thread_id]["status"] = "error"
        send_text(chat_id, "⚠️ 工作流被中断，请重新发送需求。")
    except Exception as exc:
        logger.error("Resume workflow error (thread=%s): %s", thread_id, exc, exc_info=True)
        thread_state[thread_id]["status"] = "error"
        send_text(chat_id, f"❌ 工作流恢复出错: {type(exc).__name__}: {str(exc)[:200]}")
