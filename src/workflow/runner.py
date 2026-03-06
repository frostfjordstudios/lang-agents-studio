"""工作流执行器 — 启动、恢复、跟踪工作流并推送节点消息

职责：
  - _run_workflow: 启动新工作流
  - _resume_workflow: 恢复暂停的工作流
  - _send_final_output: 发送最终产出
  - _track_node: 持久化节点执行记录
  - _format_node_message: 格式化节点推送消息
"""

import logging

from src.tools.lark.msg.messaging import send_text
from src.tools.lark.msg.multi_bot import send_as_agent
from src.agents.persona import generate_work_reply
from src.agents.agent_state import begin_session, finish_session, get_agent_context
from src.core.prompt_manager import get_agent_prompt

logger = logging.getLogger(__name__)


# ── 节点元数据映射 ────────────────────────────────────────────────────

NODE_SITUATIONS: dict[str, str] = {
    "writer": "刚写完剧本初稿，交给导演审核",
    "director_script_review": "剧本审核完成，交给制片确认",
    "showrunner_script_review": "制片审核完成，准备交给老板确认",
    "director_breakdown": "导演拆解完成，运镜/光线/风格/道具/声音指令已生成，进入内容生产",
    "parallel_production": "美术设计和声音设计都完成了，交给导演审核",
    "director_production_review": "导演审核完美术和声音设计，准备交给老板确认",
    "storyboard": "分镜提示词写完了，交给导演终审",
    "director_storyboard_review": "导演分镜终审完成",
    "parallel_scoring": "六角色并行评分全部完成，交给制片汇总",
    "scoring_summary": "多角色加权评分汇总完成",
    "save_outputs": "所有产出物已保存完毕，可以收工了",
}

USER_GATE_TEMPLATES = {
    "user_gate_script": "🔔 剧本需要你的确认\n\n{summary}\n\n请回复「通过」继续，或发送修改意见。",
    "user_gate_production": "🔔 美术+声音需要你的确认\n\n{summary}\n\n请回复「通过」继续，或发送修改意见。",
}

NODE_TO_AGENT = {
    "writer": "writer",
    "director_script_review": "director",
    "showrunner_script_review": "showrunner",
    "user_gate_script": "showrunner",
    "director_breakdown": "director",
    "parallel_production": "showrunner",
    "director_production_review": "director",
    "user_gate_production": "showrunner",
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
    "writer": "phase_1", "director_script_review": "phase_1",
    "showrunner_script_review": "phase_1", "user_gate_script": "phase_1",
    "director_breakdown": "phase_2",
    "parallel_production": "phase_3", "director_production_review": "phase_3",
    "user_gate_production": "phase_3",
    "storyboard": "phase_4", "director_storyboard_review": "phase_4",
    "parallel_scoring": "phase_4", "scoring_summary": "phase_4",
    "save_outputs": "phase_4",
}


# ── 节点跟踪 ─────────────────────────────────────────────────────────

def track_node(project: str, node_name: str, node_output: dict, input_summary: str = ""):
    """记录节点执行到 .agent-state.json。"""
    agent = NODE_TO_AGENT.get(node_name)
    phase = NODE_PHASE.get(node_name, "")
    output_field = NODE_OUTPUT_FIELD.get(node_name, "")

    if not agent or not output_field:
        return

    key_output = node_output.get(output_field, "")
    summary = key_output[:300] if key_output else "(no output)"

    try:
        sid = begin_session(project, agent, phase, input_summary or node_name)
        finish_session(project, sid, output_summary=summary, key_output=key_output)
    except Exception as e:
        logger.warning("Agent state tracking failed for %s: %s", node_name, e)


# ── 节点消息格式化 ───────────────────────────────────────────────────

def format_node_message(node_name: str, node_output: dict, state_values: dict) -> str:
    """格式化节点完成后的推送消息。"""
    gate_template = USER_GATE_TEMPLATES.get(node_name)
    if gate_template:
        summary = ""
        if node_name == "user_gate_script":
            dr = str(state_values.get("director_script_review", ""))[:400]
            sr = str(state_values.get("showrunner_script_review", ""))[:400]
            script_preview = str(state_values.get("current_script", ""))[:300]
            summary = f"📋 剧本摘要:\n{script_preview}...\n\n🎬 Director:\n{dr}\n\n🎯 Showrunner:\n{sr}"
        elif node_name == "user_gate_production":
            review = str(state_values.get("director_production_review", ""))[:500]
            summary = f"🎬 Director 审核:\n{review}"
        return gate_template.format(summary=summary)

    situation = NODE_SITUATIONS.get(node_name)
    if not situation:
        return ""

    agent = NODE_TO_AGENT.get(node_name, "showrunner")
    output_field = NODE_OUTPUT_FIELD.get(node_name, "")
    key_output = node_output.get(output_field, "") if output_field else ""
    if key_output:
        if not isinstance(key_output, str):
            key_output = str(key_output)
        excerpt = key_output[:200] + ("..." if len(key_output) > 200 else "")
        situation += f"。产出摘要：{excerpt}"

    return generate_work_reply(agent, situation)


# ── 工作流执行 ───────────────────────────────────────────────────────

def run_workflow(graph_app, chat_id: str, thread_id: str, user_request: str,
                 thread_refs: dict, thread_state: dict):
    """启动新工作流。"""
    refs = thread_refs.pop(thread_id, {"text": "", "images": []})
    thread_state[thread_id] = {"status": "running", "chat_id": chat_id, "last_node": ""}

    send_as_agent("showrunner", chat_id, "🚀 创作工作流已启动\n\n✍️ Writer 正在编写剧本...")

    project_name = thread_state[thread_id].get("project", f"proj_{thread_id[-8:]}")
    thread_state[thread_id]["project"] = project_name

    initial_state = {
        "user_request": user_request,
        "reference_images": refs["images"],
        "reference_text": refs["text"],
        "project_name": project_name,
        "current_script": "",
        "director_script_review": "",
        "showrunner_script_review": "",
        "script_review_count": 0,
        "user_script_feedback": "",
        "director_breakdown": "",
        "art_design_content": "",
        "voice_design_content": "",
        "director_production_review": "",
        "production_review_count": 0,
        "user_production_feedback": "",
        "final_storyboard": "",
        "director_storyboard_review": "",
        "storyboard_review_count": 0,
        "scoring_director": "",
        "scoring_writer": "",
        "scoring_art": "",
        "scoring_voice": "",
        "scoring_storyboard": "",
        "scoring_showrunner": "",
        "final_scoring_report": "",
        "art_feedback_images": [],
        "art_feedback_result": "",
        "refined_storyboard": "",
        "target_group": "media",
        "direct_assignee": "",
        "review_count": 0,
        "current_node": "",
    }
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

                current = node_output.get("current_node", node_name)
                thread_state[thread_id]["last_node"] = current
                logger.info("Node completed: %s (thread=%s)", current, thread_id)

                accumulated_state.update(node_output)

                for ack_agent in NODE_ACK_AGENTS.get(current, []):
                    send_as_agent(ack_agent, chat_id, "收到👌")

                msg = format_node_message(current, node_output, accumulated_state)
                if msg:
                    agent = NODE_TO_AGENT.get(current, "housekeeper")
                    send_as_agent(agent, chat_id, msg)

                track_node(project_name, current, node_output, user_request[:200])

        state = graph_app.get_state(config)
        if state.next:
            thread_state[thread_id]["status"] = "paused"
            logger.info("Workflow paused before: %s (thread=%s)", state.next, thread_id)
        else:
            thread_state[thread_id]["status"] = "finished"
            logger.info("Workflow finished (thread=%s)", thread_id)
            send_final_output(graph_app, chat_id, config)

    except GeneratorExit:
        logger.warning("Workflow GeneratorExit (thread=%s)", thread_id)
        thread_state[thread_id]["status"] = "error"
        send_text(chat_id, "⚠️ 工作流被中断，请重新发送需求。")
    except Exception as e:
        logger.error("Workflow error (thread=%s): %s", thread_id, e, exc_info=True)
        thread_state[thread_id]["status"] = "error"
        send_text(chat_id, f"❌ 工作流执行出错: {type(e).__name__}: {str(e)[:200]}")


def resume_workflow(graph_app, chat_id: str, thread_id: str, user_feedback: str,
                    thread_state: dict):
    """恢复暂停的工作流。"""
    config = {"configurable": {"thread_id": thread_id}}

    state = graph_app.get_state(config)
    next_nodes = state.next if state.next else ()
    if "user_gate_script" in next_nodes:
        graph_app.update_state(config, {"user_script_feedback": user_feedback})
    elif "user_gate_production" in next_nodes:
        graph_app.update_state(config, {"user_production_feedback": user_feedback})
    else:
        graph_app.update_state(config, {"user_script_feedback": user_feedback})

    project_name = thread_state.get(thread_id, {}).get("project", f"proj_{thread_id[-8:]}")
    thread_state[thread_id] = {"status": "running", "chat_id": chat_id, "last_node": "", "project": project_name}

    send_as_agent("showrunner", chat_id, "🔄 收到反馈，工作流恢复中...")

    try:
        for event in graph_app.stream(None, config):
            if thread_state.get(thread_id, {}).get("status") == "stopped":
                logger.info("Workflow stopped by user (thread=%s)", thread_id)
                send_text(chat_id, "⏹️ 工作流已停止。")
                return

            for node_name, node_output in event.items():
                if not isinstance(node_output, dict):
                    continue

                current = node_output.get("current_node", node_name)
                thread_state[thread_id]["last_node"] = current
                logger.info("Node completed: %s (thread=%s)", current, thread_id)

                for ack_agent in NODE_ACK_AGENTS.get(current, []):
                    send_as_agent(ack_agent, chat_id, "收到👌")

                full_state = graph_app.get_state(config).values
                msg = format_node_message(current, node_output, full_state)
                if msg:
                    agent = NODE_TO_AGENT.get(current, "housekeeper")
                    send_as_agent(agent, chat_id, msg)

                track_node(project_name, current, node_output, f"resume: {user_feedback[:100]}")

        state = graph_app.get_state(config)
        if state.next:
            thread_state[thread_id]["status"] = "paused"
        else:
            thread_state[thread_id]["status"] = "finished"
            send_final_output(graph_app, chat_id, config)

    except GeneratorExit:
        logger.warning("Resume GeneratorExit (thread=%s)", thread_id)
        thread_state[thread_id]["status"] = "error"
        send_text(chat_id, "⚠️ 工作流被中断，请重新发送需求。")
    except Exception as e:
        logger.error("Resume workflow error (thread=%s): %s", thread_id, e, exc_info=True)
        thread_state[thread_id]["status"] = "error"
        send_text(chat_id, f"❌ 工作流恢复出错: {type(e).__name__}: {str(e)[:200]}")


def send_final_output(graph_app, chat_id: str, config: dict):
    """工作流结束后，提取关键产出发送给用户。"""
    try:
        final_state = graph_app.get_state(config).values or {}

        storyboard = final_state.get("final_storyboard", "")
        if storyboard:
            if len(storyboard) > 25000:
                storyboard = storyboard[:25000] + "\n\n... (内容过长，已截断。完整版已保存到 projects/ 目录)"
            send_text(chat_id, f"📐 最终分镜提示词\n\n{storyboard}")

        report = final_state.get("final_scoring_report", "")
        if report:
            if len(report) > 10000:
                report = report[:10000] + "\n\n... (已截断)"
            send_as_agent("showrunner", chat_id, f"📊 评分汇总报告\n\n{report}")

        send_as_agent("housekeeper", chat_id, "🎉 全部完成！所有产出物已保存到 projects/ 目录～")
    except Exception as e:
        logger.error("Failed to send final output: %s", e)
        send_text(chat_id, "✅ 工作流已完成，但发送结果时出错。产出物已保存到 projects/ 目录。")
