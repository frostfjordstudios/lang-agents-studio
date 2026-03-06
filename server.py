"""FastAPI + Feishu WebSocket Long-Connection Server

Uses lark-oapi SDK's WebSocket client to receive Feishu events
via long connection (no public URL or webhook needed).
FastAPI only serves a /health endpoint for cloud platform probes.

All commands use @ prefix (in Feishu group chat):
  @help                               - List available commands
  @stop                               - Stop the current workflow
  @status                             - Show current workflow status
  @review_art                         - Review submitted art images
  @read_folder <token_or_url>         - Read Feishu folder
  @read_doc <doc_id_or_url>           - Read Feishu document
  @agent_name <message>               - Talk to a specific agent
  @all                                - Housekeeper acks, saves to context
  (plain text)                        - Housekeeper handles daily chat
"""

import os
import re
import json
import uuid
import base64
import random
import asyncio
import logging
import threading
from pathlib import Path

import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
from fastapi import FastAPI
from langchain_core.messages import SystemMessage, HumanMessage

from src.graph import build_graph
from src.llm_config import get_housekeeper_llm, get_strict_llm
from src.tools.feishu_integration import (
    read_all_from_folder,
    read_feishu_docx,
    list_folder_files,
)
from src.tools.feishu_message import (
    send_text,
    reply_text,
    download_message_image,
    download_message_file,
    image_bytes_to_base64,
)
from src.tools.doc_extract import extract_text, get_supported_extensions
from src.tools.multi_bot import send_as_agent, AGENT_BOTS
from src.tools.search_helper import SEARCH_TOOLS, get_search_tool
from src.tools.prompt_editor import PROMPT_EDITOR_TOOLS
from src.tools.chat_helper import generate_dynamic_reply, generate_idle_replies
from src.tools.prompt_manager import get_agent_prompt, get_skill_prompt, preload_all, clear_cache as clear_prompt_cache
from langgraph.prebuilt import create_react_agent
from src.agent_state import (
    begin_session,
    finish_session,
    fail_session,
    get_agent_context,
    load_state as load_agent_state,
    list_sessions,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent
SYSTEM_PROMPTS_DIR = BASE_DIR / "system_prompts"

# ── LangGraph app ─────────────────────────────────────────────────────

preload_all()  # 预加载所有 prompt 到内存，消除运行时磁盘 I/O
graph_app = build_graph()
logger.info("LangGraph workflow compiled and ready.")

# ── Per-thread state ──────────────────────────────────────────────────

# Preloaded reference materials (text + images)
_thread_refs: dict[str, dict] = {}

# Workflow tracking: {"oc_xxx": {"status": "running"|"paused"|"stopped", "chat_id": "..."}}
_thread_state: dict[str, dict] = {}

# Housekeeper conversation history (last N turns per thread)
_housekeeper_history: dict[str, list] = {}
_HOUSEKEEPER_MAX_HISTORY = 20

# Showrunner conversation history (last N turns per thread)
_showrunner_history: dict[str, list] = {}
_SHOWRUNNER_MAX_HISTORY = 20

# ── Command patterns (@ prefix) ──────────────────────────────────────
# 支持 @cmd 和 /cmd 两种形式（兼容旧习惯）

_CMD_READ_FOLDER = re.compile(
    r"^[@/]read_folder\s+"
    r"(?:https?://[a-zA-Z0-9.-]*feishu\.cn/drive/folder/)?([a-zA-Z0-9]+)\s*$",
    re.IGNORECASE,
)
_CMD_READ_DOC = re.compile(
    r"^[@/]read_doc\s+"
    r"(?:https?://[a-zA-Z0-9.-]*feishu\.cn/docx/)?([a-zA-Z0-9]+)\s*$",
    re.IGNORECASE,
)
_CMD_STOP = re.compile(r"^[@/]stop\s*$", re.IGNORECASE)
_CMD_STATUS = re.compile(r"^[@/]status\s*$", re.IGNORECASE)
_CMD_HELP = re.compile(r"^[@/]help\s*$", re.IGNORECASE)
_CMD_REVIEW_ART = re.compile(r"^[@/]review_art\s*$", re.IGNORECASE)

# 文本 @agent 路由（用户直接在消息里打 @编剧、@导演 等）
_TEXT_AT_AGENT = re.compile(r"^@(\S+)\s*(.*)", re.DOTALL)


# ── Helpers ───────────────────────────────────────────────────────────

def _ensure_thread_refs(thread_id: str) -> dict:
    if thread_id not in _thread_refs:
        _thread_refs[thread_id] = {"text": "", "images": []}
    return _thread_refs[thread_id]


def _load_housekeeper_prompt() -> str:
    return get_agent_prompt("housekeeper")


def _load_showrunner_prompt() -> str:
    return get_agent_prompt("showrunner")


def _invoke_with_search(llm, messages):
    """Invoke LLM with web search tool capability.

    If the model decides to search, execute the tool call and re-invoke
    with the search results. Returns the final AIMessage response.
    """
    from langchain_core.messages import ToolMessage

    llm_with_tools = llm.bind_tools(SEARCH_TOOLS)
    response = llm_with_tools.invoke(messages)

    if response.tool_calls:
        messages_with_tools = list(messages) + [response]
        search_tool = SEARCH_TOOLS[0]
        for tool_call in response.tool_calls:
            result = search_tool.invoke(tool_call["args"])
            messages_with_tools.append(
                ToolMessage(content=str(result), tool_call_id=tool_call["id"])
            )
        response = llm_with_tools.invoke(messages_with_tools)

    return response


# ── Node message templates ────────────────────────────────────────────

# 节点 → 场景描述（供 LLM 生成动态回复）
_NODE_SITUATIONS: dict[str, str] = {
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

# user_gate 节点仍用结构化模板（需要展示审核详情）
_USER_GATE_TEMPLATES = {
    "user_gate_script": "🔔 剧本需要你的确认\n\n{summary}\n\n请回复「通过」继续，或发送修改意见。",
    "user_gate_production": "🔔 美术+声音需要你的确认\n\n{summary}\n\n请回复「通过」继续，或发送修改意见。",
}

_NODE_TO_AGENT = {
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

# 节点 → 主要输出字段（用于 agent_state 记录）
_NODE_OUTPUT_FIELD = {
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

# 节点 → 开始时哪些 Agent 发"收到👌"（非管家 Agent 接活确认）
_NODE_ACK_AGENTS: dict[str, list[str]] = {
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

# 节点 → 所属阶段
_NODE_PHASE = {
    "writer": "phase_1", "director_script_review": "phase_1",
    "showrunner_script_review": "phase_1", "user_gate_script": "phase_1",
    "director_breakdown": "phase_2",
    "parallel_production": "phase_3", "director_production_review": "phase_3",
    "user_gate_production": "phase_3",
    "storyboard": "phase_4", "director_storyboard_review": "phase_4",
    "parallel_scoring": "phase_4", "scoring_summary": "phase_4",
    "save_outputs": "phase_4",
}


def _track_node(project: str, node_name: str, node_output: dict, input_summary: str = ""):
    """记录节点执行到 .agent-state.json（Resumable Subagents）。"""
    agent = _NODE_TO_AGENT.get(node_name)
    phase = _NODE_PHASE.get(node_name, "")
    output_field = _NODE_OUTPUT_FIELD.get(node_name, "")

    if not agent or not output_field:
        return

    key_output = node_output.get(output_field, "")
    summary = key_output[:300] if key_output else "(no output)"

    try:
        sid = begin_session(project, agent, phase, input_summary or node_name)
        finish_session(project, sid, output_summary=summary, key_output=key_output)
    except Exception as e:
        logger.warning("Agent state tracking failed for %s: %s", node_name, e)


def _format_node_message(node_name: str, node_output: dict, state_values: dict) -> str:
    """Format the push message for a completed node.

    user_gate 节点返回结构化模板（含审核详情），
    其他节点通过 LLM 生成带人设的动态回复。
    """
    # user_gate 节点：仍用结构化模板
    gate_template = _USER_GATE_TEMPLATES.get(node_name)
    if gate_template:
        summary = ""
        if node_name == "user_gate_script":
            dr = state_values.get("director_script_review", "")[:400]
            sr = state_values.get("showrunner_script_review", "")[:400]
            script_preview = state_values.get("current_script", "")[:300]
            summary = f"📋 剧本摘要:\n{script_preview}...\n\n🎬 Director:\n{dr}\n\n🎯 Showrunner:\n{sr}"
        elif node_name == "user_gate_production":
            review = state_values.get("director_production_review", "")[:500]
            summary = f"🎬 Director 审核:\n{review}"
        return gate_template.format(summary=summary)

    # 其他节点：LLM 动态回复
    situation = _NODE_SITUATIONS.get(node_name)
    if not situation:
        return ""

    agent = _NODE_TO_AGENT.get(node_name, "showrunner")

    # 提取该节点的关键产出摘要，附加到 situation
    output_field = _NODE_OUTPUT_FIELD.get(node_name, "")
    key_output = node_output.get(output_field, "") if output_field else ""
    if key_output:
        excerpt = key_output[:200] + ("..." if len(key_output) > 200 else "")
        situation += f"。产出摘要：{excerpt}"

    return generate_dynamic_reply(agent, situation)


# ── Command handlers ──────────────────────────────────────────────────

def _handle_read_folder(chat_id: str, thread_id: str, folder_token: str):
    """Read a Feishu folder and cache results for this thread."""
    try:
        send_text(chat_id, "📂 正在读取文件夹，请稍候...")
        result = read_all_from_folder(folder_token)
        refs = _ensure_thread_refs(thread_id)
        if result["text_content"]:
            refs["text"] += ("\n\n" if refs["text"] else "") + result["text_content"]
        refs["images"].extend(result["image_list"])

        send_text(
            chat_id,
            f"✅ 文件夹读取完成\n\n"
            f"📄 文本: +{len(result['text_content'])} 字符\n"
            f"🖼️ 图片: +{len(result['image_list'])} 张\n\n"
            f"素材已存入参考资料，可以开始创作。",
        )
    except Exception as e:
        logger.error("/read_folder %s failed: %s", folder_token, e, exc_info=True)
        send_text(chat_id, f"❌ 读取文件夹失败: {e}")


def _handle_read_doc(chat_id: str, thread_id: str, document_id: str):
    """Read a single Feishu Docx and cache results for this thread."""
    try:
        send_text(chat_id, "📄 正在读取文档，请稍候...")
        result = read_feishu_docx(document_id)
        refs = _ensure_thread_refs(thread_id)
        if result["text"]:
            refs["text"] += ("\n\n" if refs["text"] else "") + result["text"]
        refs["images"].extend(result["images"])

        send_text(
            chat_id,
            f"✅ 文档读取完成\n\n"
            f"📄 文本: +{len(result['text'])} 字符\n"
            f"🖼️ 图片: +{len(result['images'])} 张\n\n"
            f"素材已存入参考资料，可以开始创作。",
        )
    except Exception as e:
        logger.error("/read_doc %s failed: %s", document_id, e, exc_info=True)
        send_text(chat_id, f"❌ 读取文档失败: {e}")


def _handle_stop(chat_id: str, thread_id: str):
    """Stop the current workflow."""
    if thread_id in _thread_state and _thread_state[thread_id]["status"] == "running":
        _thread_state[thread_id]["status"] = "stopped"
        send_text(chat_id, "⏹️ 工作流已标记停止\n\n发送新消息可继续对话或启动新任务。")
    else:
        send_text(chat_id, "ℹ️ 当前没有正在运行的工作流。")


def _handle_status(chat_id: str, thread_id: str):
    """Show current workflow status."""
    refs = _thread_refs.get(thread_id, {"text": "", "images": []})
    state_info = _thread_state.get(thread_id, {})
    status = state_info.get("status", "idle")
    last_node = state_info.get("last_node", "-")

    # Check if there's a paused workflow in LangGraph
    config = {"configurable": {"thread_id": thread_id}}
    paused_at = ""
    try:
        graph_state = graph_app.get_state(config)
        if graph_state.next:
            paused_at = f"\n⏸️ 暂停于: {graph_state.next}"
    except Exception:
        pass

    art_queue = len(_art_feedback_images.get(thread_id, []))
    msg = (
        f"📊 当前状态\n\n"
        f"🔄 工作流: {status}\n"
        f"📍 最后节点: {last_node}{paused_at}\n"
        f"📎 已加载素材: {len(refs['images'])} 张图片, {len(refs['text'])} 字符文本"
    )
    if art_queue:
        msg += f"\n🎨 效果图队列: {art_queue} 张（发送 /review_art 开始评审）"
    send_text(chat_id, msg)


def _handle_help(chat_id: str):
    """Show available commands."""
    send_as_agent("housekeeper", chat_id, (
        "📖 命令列表\n\n"
        "@help　　　　显示此帮助\n"
        "@stop　　　　停止当前工作流\n"
        "@status　　　查看状态和素材\n"
        "@review_art　评审效果图\n"
        "@read_folder <token或链接>　读取飞书文件夹\n"
        "@read_doc <文档ID或链接>　读取飞书文档\n\n"
        "📣 对话\n"
        "　　直接说话 → 管家接待\n"
        "　　@编剧/导演/美术/声音/分镜/制片 → 对应成员回复\n"
        "　　@所有人 → 管家代收\n\n"
        "💡 发图片/文件自动存入素材\n"
        "💡 支持 PDF, PPTX, DOCX, XLSX, TXT 等"
    ))


# ── Art Feedback (美术效果图反馈) ────────────────────────────────────

# Per-thread art feedback images (accumulated before /review_art)
_art_feedback_images: dict[str, list[str]] = {}


def _handle_review_art(chat_id: str, thread_id: str):
    """Review user-submitted art images against art design spec, refine storyboard."""
    images = _art_feedback_images.get(thread_id, [])
    if not images:
        send_text(chat_id, "⚠️ 还没有收到效果图\n\n请先发送生成的美术效果图，然后再使用 /review_art 命令。")
        return

    # Get the workflow state to find art_design_content and storyboard
    state_info = _thread_state.get(thread_id, {})
    config = {"configurable": {"thread_id": thread_id}}

    art_design = ""
    storyboard = ""
    try:
        graph_state = graph_app.get_state(config)
        state_values = graph_state.values or {}
        art_design = state_values.get("art_design_content", "")
        storyboard = state_values.get("final_storyboard", "")
    except Exception:
        pass

    if not art_design and not storyboard:
        send_text(chat_id, "⚠️ 当前没有美术设计方案或分镜数据\n\n请先完成一次创作工作流，再提交效果图进行反馈。")
        return

    send_text(chat_id, f"🎨 正在分析 {len(images)} 张效果图...\n\n⏳ 对比美术设计方案并生成反馈")

    try:
        _run_art_feedback(chat_id, thread_id, images, art_design, storyboard)
    except Exception as e:
        logger.error("Art feedback error: %s", e, exc_info=True)
        send_text(chat_id, f"❌ 效果图分析出错: {e}")


def _run_art_feedback(
    chat_id: str,
    thread_id: str,
    images: list[str],
    art_design: str,
    storyboard: str,
):
    """Use LLM to compare generated art against design spec and refine storyboard."""
    from src.nodes import _build_multimodal_message

    prompt = (
        "你是一位资深的美术总监和视觉效果评审专家。\n\n"
        "用户已经基于美术设计方案生成了效果图，请你：\n"
        "1. 逐张分析效果图，评估与美术设计方案的符合程度\n"
        "2. 指出效果图中的亮点和不足\n"
        "3. 基于效果图的实际效果，给出优化后的视频分镜提示词\n"
        "4. 提出下一轮效果图生成的改进建议\n\n"
        "输出格式：\n"
        "📊 效果评估\n"
        "（逐张评分和点评）\n\n"
        "✅ 亮点\n"
        "（列出做得好的地方）\n\n"
        "⚠️ 需改进\n"
        "（列出需要调整的地方）\n\n"
        "📐 优化分镜提示词\n"
        "（基于实际效果图优化后的完整分镜提示词）\n\n"
        "💡 下一轮建议\n"
        "（改进建议）"
    )

    user_text = f"以下是用户提交的 {len(images)} 张效果图，请与美术设计方案进行对比。\n\n"
    if art_design:
        user_text += f"--- 美术设计方案 ---\n{art_design[:3000]}\n\n"
    if storyboard:
        user_text += f"--- 当前分镜提示词 ---\n{storyboard[:3000]}\n\n"
    user_text += "请分析以下效果图："

    llm = get_housekeeper_llm()
    messages = [
        SystemMessage(content=prompt),
        _build_multimodal_message(user_text, images),
    ]

    response = llm.invoke(messages)

    raw = response.content
    if isinstance(raw, str):
        reply = raw
    elif isinstance(raw, list):
        reply = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in raw
        )
    else:
        reply = str(raw) if raw else ""

    # Send feedback to chat
    send_text(chat_id, reply)

    # Clear feedback images after review
    _art_feedback_images[thread_id] = []

    logger.info("Art feedback sent (thread=%s, images=%d)", thread_id, len(images))


# ── Showrunner Agent (主对接人) ───────────────────────────────────────

def _handle_showrunner(chat_id: str, message_id: str, text: str, thread_id: str):
    """Showrunner direct conversation — main user interface for creative requests.

    If the user expresses a creative need, Showrunner replies with
    [ACTION:START_WORKFLOW] to trigger the LangGraph workflow.
    """
    try:
        prompt = _load_showrunner_prompt()

        if thread_id not in _showrunner_history:
            _showrunner_history[thread_id] = []
        history = _showrunner_history[thread_id]

        messages = [SystemMessage(content=prompt)]

        # System context + Resumable Subagents 历史
        refs = _thread_refs.get(thread_id, {"text": "", "images": []})
        state_info = _thread_state.get(thread_id, {})
        project = state_info.get("project", f"proj_{thread_id[-8:]}")

        # 加载制片的历史 session 上下文
        showrunner_ctx = get_agent_context(project, "showrunner")

        context = (
            f"[系统上下文] 当前已加载素材: {len(refs['images'])} 张图片, "
            f"{len(refs['text'])} 字符文本。"
            f"工作流状态: {state_info.get('status', 'idle')}。"
            f"\n\n"
            f"你是制片总监 Showrunner，是用户的主要对接人。"
            f"当用户表达了明确的创作需求（如写剧本、制作短剧等），"
            f"请在回复末尾加上 [ACTION:START_WORKFLOW] 来启动工作流。"
            f"如果用户只是在闲聊或提问，正常回复即可，不要加标记。"
        )
        if showrunner_ctx:
            context += f"\n\n{showrunner_ctx}"
        messages.append(HumanMessage(content=context))

        for msg in history[-_SHOWRUNNER_MAX_HISTORY:]:
            messages.append(msg)

        messages.append(HumanMessage(content=text))

        llm = get_strict_llm()
        response = _invoke_with_search(llm, messages)

        raw = response.content
        if isinstance(raw, str):
            reply_content = raw
        elif isinstance(raw, list):
            reply_content = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in raw
            )
        else:
            reply_content = str(raw) if raw else ""

        logger.info("Showrunner reply (len=%d): %s", len(reply_content), reply_content[:100])

        # Save to history
        history.append(HumanMessage(content=text))
        history.append(response)
        if len(history) > _SHOWRUNNER_MAX_HISTORY * 2:
            _showrunner_history[thread_id] = history[-_SHOWRUNNER_MAX_HISTORY:]

        # Check if showrunner wants to start a workflow
        if "[ACTION:START_WORKFLOW]" in reply_content:
            clean_reply = reply_content.replace("[ACTION:START_WORKFLOW]", "").strip()
            send_as_agent("showrunner", chat_id, clean_reply)
            logger.info("Showrunner triggered workflow: thread=%s", thread_id)
            _run_workflow(chat_id, thread_id, text)
        else:
            send_as_agent("showrunner", chat_id, reply_content)

    except Exception as e:
        logger.error("Showrunner error: %s", e, exc_info=True)
        send_text(chat_id, f"❌ 制片暂时无法回复: {e}")


# ── Housekeeper Agent ─────────────────────────────────────────────────

def _handle_housekeeper(chat_id: str, message_id: str, text: str, thread_id: str):
    """Housekeeper — ReAct Agent，具备多轮搜索 + Prompt 文件编辑能力。

    管家可以：
    - 联网搜索资料（Tavily）
    - 读取/修改/创建 system_prompts/ 下的 agents 和 skills 文件
    - 多轮推理→行动→观察循环
    """
    try:
        prompt = _load_housekeeper_prompt()

        # Add context about current state
        refs = _thread_refs.get(thread_id, {"text": "", "images": []})
        state_info = _thread_state.get(thread_id, {})
        prompt += (
            f"\n\n[系统上下文] 当前已加载素材: {len(refs['images'])} 张图片, "
            f"{len(refs['text'])} 字符文本。"
            f"工作流状态: {state_info.get('status', 'idle')}。"
            "\n\n你拥有以下能力："
            "\n1. 联网搜索：查找实时信息、行业资料"
            "\n2. 文件管理：读取、修改、创建 system_prompts/ 下的 agents 和 skills 提示词文件"
            "\n   - list_prompt_files: 列出目录下的文件"
            "\n   - read_prompt_file: 读取文件内容"
            "\n   - write_prompt_file: 创建或覆写文件"
            "\n   - edit_prompt_file: 精确替换文件中的文本"
            "\n当用户要求修改 Agent 提示词或创建新 Agent/Skill 时，请主动使用文件工具。"
            "\n当用户表达创作需求时，在回复末尾加 [ACTION:START_WORKFLOW] 启动工作流。"
        )

        # Build conversation history for the agent
        if thread_id not in _housekeeper_history:
            _housekeeper_history[thread_id] = []
        history = _housekeeper_history[thread_id]

        # Combine history into user message context
        history_text = ""
        if history:
            recent = history[-_HOUSEKEEPER_MAX_HISTORY:]
            parts = []
            for msg in recent:
                role = "用户" if isinstance(msg, HumanMessage) else "管家"
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                parts.append(f"{role}: {content[:500]}")
            history_text = "\n\n[对话历史]\n" + "\n".join(parts) + "\n\n[当前消息]\n"

        user_input = history_text + text

        # Build ReAct Agent with search + prompt editor tools
        llm = get_housekeeper_llm()
        tools = [get_search_tool()] + PROMPT_EDITOR_TOOLS
        housekeeper_agent = create_react_agent(llm, tools, prompt=prompt)

        result = housekeeper_agent.invoke({"messages": [HumanMessage(content=user_input)]})

        # Extract final reply
        reply_content = ""
        for msg in reversed(result["messages"]):
            if hasattr(msg, "content") and isinstance(msg.content, str) and msg.content:
                if not hasattr(msg, "tool_calls") or not msg.tool_calls:
                    reply_content = msg.content
                    break

        logger.info("Housekeeper reply (len=%d): %s", len(reply_content), reply_content[:100])

        # Save to history (simplified — store as HumanMessage/AIMessage pairs)
        from langchain_core.messages import AIMessage
        history.append(HumanMessage(content=text))
        history.append(AIMessage(content=reply_content))
        if len(history) > _HOUSEKEEPER_MAX_HISTORY * 2:
            _housekeeper_history[thread_id] = history[-_HOUSEKEEPER_MAX_HISTORY:]

        # Check if housekeeper wants to start a workflow
        if "[ACTION:START_WORKFLOW]" in reply_content:
            clean_reply = reply_content.replace("[ACTION:START_WORKFLOW]", "").strip()
            send_as_agent("housekeeper", chat_id, clean_reply)
            logger.info("Housekeeper triggered workflow: thread=%s", thread_id)
            _run_workflow(chat_id, thread_id, text)
        else:
            send_as_agent("housekeeper", chat_id, reply_content)

            # Idle chat: 1-2 random agents also chime in
            status = _thread_state.get(thread_id, {}).get("status", "idle")
            if status in ("idle", "finished", "error", "stopped"):
                try:
                    count = random.randint(1, 2)
                    logger.info("Idle chat triggered: status=%s, count=%d", status, count)
                    idle_replies = generate_idle_replies(text, count=count)
                    logger.info("Idle chat got %d replies", len(idle_replies))
                    for role, idle_text in idle_replies:
                        logger.info("Idle reply from %s: %s", role, idle_text[:50])
                        send_as_agent(role, chat_id, idle_text)
                except Exception as idle_err:
                    logger.warning("Idle chat failed: %s", idle_err, exc_info=True)

    except Exception as e:
        logger.error("Housekeeper error: %s", e, exc_info=True)
        send_text(chat_id, f"❌ 管家暂时无法回复: {e}")


# ── Workflow helpers ──────────────────────────────────────────────────

def _run_workflow(chat_id: str, thread_id: str, user_request: str):
    """Start a new workflow, injecting any preloaded references."""
    refs = _thread_refs.pop(thread_id, {"text": "", "images": []})

    _thread_state[thread_id] = {"status": "running", "chat_id": chat_id, "last_node": ""}

    send_as_agent("showrunner", chat_id, "🚀 创作工作流已启动\n\n✍️ Writer 正在编写剧本...")

    # 项目名：用 thread_id 的后 8 位 + 时间戳生成可读名称
    project_name = _thread_state[thread_id].get("project", f"proj_{thread_id[-8:]}")
    _thread_state[thread_id]["project"] = project_name

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
        "current_node": "",
    }
    config = {"configurable": {"thread_id": thread_id}}

    try:
        accumulated_state = dict(initial_state)
        for event in graph_app.stream(initial_state, config):
            # Check for stop signal
            if _thread_state.get(thread_id, {}).get("status") == "stopped":
                logger.info("Workflow stopped by user (thread=%s)", thread_id)
                send_text(chat_id, "⏹️ 工作流已停止。")
                return

            for node_name, node_output in event.items():
                # node_output may be a dict or a tuple depending on LangGraph version
                if not isinstance(node_output, dict):
                    logger.info("Node event: %s (non-dict output, thread=%s)", node_name, thread_id)
                    continue

                current = node_output.get("current_node", node_name)
                _thread_state[thread_id]["last_node"] = current
                logger.info("Node completed: %s (thread=%s)", current, thread_id)

                # Merge output into accumulated state
                accumulated_state.update(node_output)

                # Ack: non-housekeeper agents say "收到👌" when receiving task
                for ack_agent in _NODE_ACK_AGENTS.get(current, []):
                    send_as_agent(ack_agent, chat_id, "收到👌")

                # Push message for key nodes (as the corresponding agent)
                msg = _format_node_message(current, node_output, accumulated_state)
                if msg:
                    agent = _NODE_TO_AGENT.get(current, "housekeeper")
                    send_as_agent(agent, chat_id, msg)

                # Resumable Subagents: 持久化节点产出
                _track_node(project_name, current, node_output, user_request[:200])

        state = graph_app.get_state(config)
        if state.next:
            _thread_state[thread_id]["status"] = "paused"
            logger.info("Workflow paused before: %s (thread=%s)", state.next, thread_id)
        else:
            _thread_state[thread_id]["status"] = "finished"
            logger.info("Workflow finished (thread=%s)", thread_id)

    except Exception as e:
        logger.error("Workflow error (thread=%s): %s", thread_id, e, exc_info=True)
        _thread_state[thread_id]["status"] = "error"
        send_text(chat_id, f"❌ 工作流执行出错: {e}")


def _resume_workflow(chat_id: str, thread_id: str, user_feedback: str):
    """Resume a paused workflow with user feedback."""
    config = {"configurable": {"thread_id": thread_id}}

    # Determine which gate we're paused at and set the right feedback field
    state = graph_app.get_state(config)
    next_nodes = state.next if state.next else ()
    if "user_gate_script" in next_nodes:
        graph_app.update_state(config, {"user_script_feedback": user_feedback})
    elif "user_gate_production" in next_nodes:
        graph_app.update_state(config, {"user_production_feedback": user_feedback})
    else:
        # Fallback
        graph_app.update_state(config, {"user_script_feedback": user_feedback})

    project_name = _thread_state.get(thread_id, {}).get("project", f"proj_{thread_id[-8:]}")
    _thread_state[thread_id] = {"status": "running", "chat_id": chat_id, "last_node": "", "project": project_name}

    send_as_agent("showrunner", chat_id, "🔄 收到反馈，工作流恢复中...")

    try:
        for event in graph_app.stream(None, config):
            if _thread_state.get(thread_id, {}).get("status") == "stopped":
                logger.info("Workflow stopped by user (thread=%s)", thread_id)
                send_text(chat_id, "⏹️ 工作流已停止。")
                return

            for node_name, node_output in event.items():
                if not isinstance(node_output, dict):
                    logger.info("Node event: %s (non-dict output, thread=%s)", node_name, thread_id)
                    continue

                current = node_output.get("current_node", node_name)
                _thread_state[thread_id]["last_node"] = current
                logger.info("Node completed: %s (thread=%s)", current, thread_id)

                # Ack: non-housekeeper agents say "收到👌" when receiving task
                for ack_agent in _NODE_ACK_AGENTS.get(current, []):
                    send_as_agent(ack_agent, chat_id, "收到👌")

                # Get full state for message formatting
                full_state = graph_app.get_state(config).values
                msg = _format_node_message(current, node_output, full_state)
                if msg:
                    agent = _NODE_TO_AGENT.get(current, "housekeeper")
                    send_as_agent(agent, chat_id, msg)

                # Resumable Subagents: 持久化节点产出
                _track_node(project_name, current, node_output, f"resume: {user_feedback[:100]}")

        state = graph_app.get_state(config)
        if state.next:
            _thread_state[thread_id]["status"] = "paused"
            logger.info("Workflow paused again before: %s (thread=%s)", state.next, thread_id)
        else:
            _thread_state[thread_id]["status"] = "finished"
            logger.info("Workflow finished (thread=%s)", thread_id)

    except Exception as e:
        logger.error("Resume workflow error (thread=%s): %s", thread_id, e, exc_info=True)
        _thread_state[thread_id]["status"] = "error"
        send_text(chat_id, f"❌ 工作流恢复出错: {e}")


# ── Image/File message handlers ──────────────────────────────────────

def _handle_image_message(chat_id: str, message_id: str, content: dict, thread_id: str):
    """Download image from message and store as reference or art feedback."""
    try:
        image_key = content.get("image_key", "")
        if not image_key:
            return

        image_bytes = download_message_image(message_id, image_key)
        if not image_bytes:
            return

        b64 = image_bytes_to_base64(image_bytes)

        # If workflow is finished, store as art feedback image
        state_info = _thread_state.get(thread_id, {})
        if state_info.get("status") == "finished":
            if thread_id not in _art_feedback_images:
                _art_feedback_images[thread_id] = []
            _art_feedback_images[thread_id].append(b64)
            count = len(_art_feedback_images[thread_id])
            send_text(
                chat_id,
                f"🎨 效果图已收到 ({count} 张)\n\n"
                f"继续发送更多效果图，或发送 @review_art 开始评审。",
            )
        else:
            # Store as reference material
            refs = _ensure_thread_refs(thread_id)
            refs["images"].append(b64)
            send_text(
                chat_id,
                f"📎 图片已收到并存入参考素材\n\n"
                f"🖼️ 当前共 {len(refs['images'])} 张参考图片",
            )
    except Exception as e:
        logger.error("Handle image message failed: %s", e, exc_info=True)
        send_text(chat_id, "❌ 图片处理失败，请重试。")


def _handle_file_message(chat_id: str, message_id: str, content: dict, thread_id: str):
    """Download file from message and store appropriately.

    - Image files → store as Base64 reference image
    - Documents (PDF/PPTX/DOCX/XLSX/TXT...) → extract text, store as reference text
    - Other files → acknowledge receipt
    """
    try:
        file_key = content.get("file_key", "")
        file_name = content.get("file_name", "unknown")

        if not file_key:
            return

        image_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
        ext = os.path.splitext(file_name)[1].lower()

        # ── Image file → store as reference image
        if ext in image_exts:
            result = download_message_file(message_id, file_key)
            if result:
                file_bytes, _ = result
                refs = _ensure_thread_refs(thread_id)
                mime = "image/png" if ext == ".png" else "image/jpeg"
                b64 = image_bytes_to_base64(file_bytes, mime)
                refs["images"].append(b64)
                send_text(
                    chat_id,
                    f"📎 图片文件 {file_name} 已存入参考素材\n"
                    f"🖼️ 当前共 {len(refs['images'])} 张参考图片",
                )
            return

        # ── Document file → extract text and store
        supported_exts = get_supported_extensions()
        if ext in supported_exts:
            send_text(chat_id, f"📄 正在解析 {file_name}...")
            result = download_message_file(message_id, file_key)
            if not result:
                send_text(chat_id, f"❌ 文件 {file_name} 下载失败")
                return

            file_bytes, _ = result
            text = extract_text(file_bytes, file_name)

            if text and text.strip():
                refs = _ensure_thread_refs(thread_id)
                header = f"--- {file_name} ---\n"
                refs["text"] += ("\n\n" if refs["text"] else "") + header + text.strip()

                # Truncate display for long text
                preview = text.strip()[:200]
                send_text(
                    chat_id,
                    f"✅ {file_name} 解析完成\n\n"
                    f"📄 提取 {len(text)} 字符文本\n"
                    f"📎 已存入参考素材\n\n"
                    f"预览:\n{preview}...",
                )
            else:
                send_text(chat_id, f"⚠️ {file_name} 未能提取到文本内容")
            return

        # ── Other files → acknowledge only
        send_text(
            chat_id,
            f"📎 文件 {file_name} 已收到\n\n"
            f"ℹ️ 暂不支持 {ext} 格式的自动解析。\n"
            f"支持的格式: PDF, PPTX, DOCX, XLSX, TXT, CSV, JSON, MD 等",
        )
    except Exception as e:
        logger.error("Handle file message failed: %s", e, exc_info=True)
        send_text(chat_id, "❌ 文件处理失败，请重试。")


# ── @mention 解析 ────────────────────────────────────────────────────

# Agent 显示名→内部名 映射（飞书群里机器人名称 → agent_name）
_MENTION_NAME_MAP: dict[str, str] = {
    "总管": "showrunner", "showrunner": "showrunner", "制片": "showrunner",
    "管家": "housekeeper", "housekeeper": "housekeeper",
    "编剧": "writer", "writer": "writer",
    "导演": "director", "director": "director",
    "美术": "art_design", "art_design": "art_design", "美术设计": "art_design",
    "声音": "voice_design", "voice_design": "voice_design", "声音设计": "voice_design",
    "分镜": "storyboard", "storyboard": "storyboard", "分镜师": "storyboard",
}


def _parse_mentions(message) -> tuple[list[str], bool]:
    """解析消息中的 @mention，返回 (被@的agent列表, 是否@了所有人)。

    飞书消息 mentions 结构:
      message.mentions = [{"key": "@_user_1", "id": {"open_id": "..."}, "name": "xxx"}, ...]
      @所有人的 id.open_id 通常为 "all"
    """
    mentioned_agents: list[str] = []
    is_at_all = False

    mentions = getattr(message, "mentions", None)
    if not mentions:
        return mentioned_agents, is_at_all

    for mention in mentions:
        # mention 可能是 dict 或对象
        if isinstance(mention, dict):
            name = mention.get("name", "").lower().strip()
            m_id = mention.get("id", {})
            open_id = m_id.get("open_id", "") if isinstance(m_id, dict) else ""
        else:
            name = getattr(mention, "name", "").lower().strip()
            m_id = getattr(mention, "id", None)
            open_id = getattr(m_id, "open_id", "") if m_id else ""

        if open_id == "all" or name == "所有人":
            is_at_all = True
            continue

        agent = _MENTION_NAME_MAP.get(name)
        if agent:
            mentioned_agents.append(agent)

    return mentioned_agents, is_at_all


# ── 通用 Agent 对话 ─────────────────────────────────────────────────

def _handle_agent_chat(agent_name: str, chat_id: str, message_id: str, text: str, thread_id: str):
    """Route chat to a specific agent by name.

    All agents have full conversation ability + web search capability.
    Non-housekeeper agents ack with "收到👌" before responding.
    """
    # Ack first (non-housekeeper agents)
    if agent_name != "housekeeper":
        send_as_agent(agent_name, chat_id, "收到👌")

    if agent_name == "showrunner":
        _handle_showrunner(chat_id, message_id, text, thread_id)
        return
    if agent_name == "housekeeper":
        _handle_housekeeper(chat_id, message_id, text, thread_id)
        return

    # All other agents: full conversation with search capability
    try:
        try:
            sys_prompt = get_agent_prompt(agent_name)
        except (ValueError, FileNotFoundError):
            sys_prompt = f"你是{agent_name}。"

        sys_prompt += "\n\n你可以使用搜索工具查找互联网上的信息来辅助回答。请用你的专业身份回复，保持角色特色。"

        from langchain.agents import AgentExecutor, create_tool_calling_agent
        from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
        from src.llm_config import get_creative_llm, get_slight_llm, get_coder_llm

        # Use the LLM matching the agent's role
        _agent_llm_map = {
            "writer": get_creative_llm,
            "art_design": get_creative_llm,
            "voice_design": get_creative_llm,
            "director": get_slight_llm,
            "storyboard": get_coder_llm,
        }
        llm_factory = _agent_llm_map.get(agent_name, get_creative_llm)
        llm = llm_factory()

        prompt = ChatPromptTemplate.from_messages([
            ("system", sys_prompt),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ])

        agent = create_tool_calling_agent(llm, SEARCH_TOOLS, prompt)
        executor = AgentExecutor(agent=agent, tools=SEARCH_TOOLS, verbose=False, max_iterations=3)

        result = executor.invoke({"input": text})
        reply = result.get("output", "")

        send_as_agent(agent_name, chat_id, reply)
    except Exception as e:
        logger.error("Agent %s chat error: %s", agent_name, e, exc_info=True)
        send_as_agent(agent_name, chat_id, "抱歉，处理时出了点问题，请稍后再试。")


# ── Feishu message handler ────────────────────────────────────────────

def _handle_feishu_message(data: P2ImMessageReceiveV1) -> None:
    """Handle im.message.receive_v1 event from Feishu WebSocket."""
    try:
        message = data.event.message
        msg_type = message.message_type
        chat_id = message.chat_id
        message_id = message.message_id
        thread_id = chat_id or str(uuid.uuid4())
        content = json.loads(message.content) if message.content else {}

        # ── Parse @mentions ──
        mentioned_agents, is_at_all = _parse_mentions(message)

        # ── Image message ──
        if msg_type == "image":
            t = threading.Thread(
                target=_handle_image_message,
                args=(chat_id, message_id, content, thread_id),
                daemon=True,
            )
            t.start()
            return

        # ── File message ──
        if msg_type == "file":
            t = threading.Thread(
                target=_handle_file_message,
                args=(chat_id, message_id, content, thread_id),
                daemon=True,
            )
            t.start()
            return

        # ── Audio / Video ──
        if msg_type in ("audio", "media"):
            send_text(chat_id, f"📎 已收到{msg_type}消息\n\nℹ️ 音视频处理功能即将上线。")
            return

        # ── Text message ──
        if msg_type != "text":
            logger.info("Ignored message type: %s", msg_type)
            return

        text_content = content.get("text", "").strip()
        # Strip Feishu @mention placeholders like @_user_1 from text
        clean_text = re.sub(r"@_user_\d+", "", text_content).strip()
        if not clean_text and not is_at_all:
            return

        # ── @所有人 → 管家代表团队回复"收到"，不浪费 token ──
        if is_at_all:
            refs = _ensure_thread_refs(thread_id)
            if clean_text:
                refs["text"] += ("\n\n" if refs["text"] else "") + f"[全员通知] {clean_text}"
            send_as_agent("housekeeper", chat_id, "收到👌")
            logger.info("@all received, ack sent (thread=%s)", thread_id)
            return

        # ── 飞书原生 @mention（点选机器人）→ 路由到该 Agent ──
        if mentioned_agents:
            target_agent = mentioned_agents[0]
            logger.info("@%s (mention) handling: thread=%s", target_agent, thread_id)
            t = threading.Thread(
                target=_handle_agent_chat,
                args=(target_agent, chat_id, message_id, clean_text, thread_id),
                daemon=True,
            )
            t.start()
            return

        # ── @command 派发（@help, @stop, @read_folder 等） ──

        if _CMD_HELP.match(clean_text):
            _handle_help(chat_id)
            return

        if _CMD_STOP.match(clean_text):
            _handle_stop(chat_id, thread_id)
            return

        if _CMD_STATUS.match(clean_text):
            _handle_status(chat_id, thread_id)
            return

        if _CMD_REVIEW_ART.match(clean_text):
            t = threading.Thread(
                target=_handle_review_art,
                args=(chat_id, thread_id),
                daemon=True,
            )
            t.start()
            return

        m = _CMD_READ_FOLDER.match(clean_text)
        if m:
            folder_token = m.group(1)
            t = threading.Thread(
                target=_handle_read_folder,
                args=(chat_id, thread_id, folder_token),
                daemon=True,
            )
            t.start()
            return

        m = _CMD_READ_DOC.match(clean_text)
        if m:
            doc_id = m.group(1)
            t = threading.Thread(
                target=_handle_read_doc,
                args=(chat_id, thread_id, doc_id),
                daemon=True,
            )
            t.start()
            return

        # ── 文本 @agent 路由（用户打字 @编剧 / @导演 等）──
        at_match = _TEXT_AT_AGENT.match(clean_text)
        if at_match:
            at_name = at_match.group(1).lower().strip()
            at_body = at_match.group(2).strip()
            agent = _MENTION_NAME_MAP.get(at_name)
            if agent:
                logger.info("@%s (text) handling: thread=%s", agent, thread_id)
                t = threading.Thread(
                    target=_handle_agent_chat,
                    args=(agent, chat_id, message_id, at_body or "你好", thread_id),
                    daemon=True,
                )
                t.start()
                return

        # ── Workflow resume (if paused) ──

        config = {"configurable": {"thread_id": thread_id}}
        try:
            state = graph_app.get_state(config)
            if state.next:
                logger.info("Resuming thread=%s with feedback: %s", thread_id, clean_text[:50])
                t = threading.Thread(
                    target=_resume_workflow,
                    args=(chat_id, thread_id, clean_text),
                    daemon=True,
                )
                t.start()
                return
        except Exception:
            pass

        # ── Default: 管家（Housekeeper）处理日常对话 ──

        logger.info("Housekeeper handling (default): thread=%s, text=%s", thread_id, clean_text[:50])
        t = threading.Thread(
            target=_handle_housekeeper,
            args=(chat_id, message_id, clean_text, thread_id),
            daemon=True,
        )
        t.start()

    except Exception as e:
        logger.error("Error handling Feishu message: %s", e, exc_info=True)


# ── Feishu WebSocket client ──────────────────────────────────────────

def _start_feishu_ws():
    """Initialize and start the Feishu WebSocket long-connection client.

    lark_oapi's ws.Client uses a MODULE-LEVEL global `loop` variable
    (created at import time via asyncio.get_event_loop()). When uvicorn
    starts its own event loop on the main thread, that global loop becomes
    "already running", causing cli.start() -> loop.run_until_complete()
    to crash with RuntimeError.

    Fix: Replace the SDK's module-level `loop` with a fresh event loop
    dedicated to this daemon thread.
    """
    import lark_oapi.ws.client as _ws_mod

    # Override the SDK's global loop with a new, thread-local one
    _ws_mod.loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_ws_mod.loop)

    app_id = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")

    if not app_id or not app_secret:
        logger.error(
            "FEISHU_APP_ID or FEISHU_APP_SECRET not set. "
            "Feishu WebSocket client will NOT start."
        )
        return

    event_handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(_handle_feishu_message)
        .build()
    )

    cli = lark.ws.Client(
        app_id,
        app_secret,
        event_handler=event_handler,
        log_level=lark.LogLevel.INFO,
    )

    logger.info("Starting Feishu WebSocket client...")
    cli.start()  # Blocking call — runs inside daemon thread


# ── Start Feishu WS at module level (BEFORE uvicorn's event loop exists) ──

_ws_thread = threading.Thread(target=_start_feishu_ws, daemon=True)
_ws_thread.start()
logger.info("Feishu WebSocket thread launched.")

app = FastAPI(title="Feishu LangGraph Agent")


# ── Health check (for cloud platform probes) ─────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}
