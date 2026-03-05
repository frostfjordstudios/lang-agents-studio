"""FastAPI + Feishu WebSocket Long-Connection Server

Uses lark-oapi SDK's WebSocket client to receive Feishu events
via long connection (no public URL or webhook needed).
FastAPI only serves a /health endpoint for cloud platform probes.

Supported user commands (in Feishu chat):
  /read_folder <folder_token_or_url>  - Read all docs & images from a Feishu folder
  /read_doc <document_id>             - Read a single Feishu Docx document
  /stop                               - Stop the current workflow
  /status                             - Show current workflow status
  /help                               - List available commands
  (image/file messages)               - Auto-saved as reference materials
  (any other text)                    - Housekeeper chat or workflow resume
"""

import os
import re
import json
import uuid
import base64
import asyncio
import logging
import threading
from pathlib import Path

import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
from fastapi import FastAPI
from langchain_core.messages import SystemMessage, HumanMessage

from src.graph import build_graph
from src.llm_config import get_housekeeper_llm
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent
SYSTEM_PROMPTS_DIR = BASE_DIR / "system_prompts"

# ── LangGraph app ─────────────────────────────────────────────────────

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

# ── Command patterns ──────────────────────────────────────────────────

_CMD_READ_FOLDER = re.compile(
    r"^/read_folder\s+"
    r"(?:https?://[a-zA-Z0-9.-]*feishu\.cn/drive/folder/)?([a-zA-Z0-9]+)\s*$",
    re.IGNORECASE,
)
_CMD_READ_DOC = re.compile(
    r"^/read_doc\s+"
    r"(?:https?://[a-zA-Z0-9.-]*feishu\.cn/docx/)?([a-zA-Z0-9]+)\s*$",
    re.IGNORECASE,
)
_CMD_STOP = re.compile(r"^/stop\s*$", re.IGNORECASE)
_CMD_STATUS = re.compile(r"^/status\s*$", re.IGNORECASE)
_CMD_HELP = re.compile(r"^/help\s*$", re.IGNORECASE)


# ── Helpers ───────────────────────────────────────────────────────────

def _ensure_thread_refs(thread_id: str) -> dict:
    if thread_id not in _thread_refs:
        _thread_refs[thread_id] = {"text": "", "images": []}
    return _thread_refs[thread_id]


def _load_housekeeper_prompt() -> str:
    filepath = SYSTEM_PROMPTS_DIR / "agents" / "housekeeper" / "housekeeper.md"
    return filepath.read_text(encoding="utf-8")


# ── Node message templates ────────────────────────────────────────────

_NODE_MESSAGES = {
    "writer": "✍️ Writer | 编剧完成\n\n{summary}\n\n⏳ 进入 Director 审核...",
    "director_review": "🎬 Director | 审核完成\n\n{summary}",
    "user_gate": "🔔 需要你的确认\n\n{summary}\n\n请回复「通过」继续，或发送修改意见。",
    "parallel_design": "🎨 美术设计 + 🔊 声音设计 | 完成\n\n⏳ 进入分镜编写...",
    "storyboard": "📐 Storyboard | 分镜提示词完成\n\n{summary}\n\n⏳ 进入终审...",
    "director_final_review": "🎬 Director | 终审完成\n\n{summary}",
    "save_outputs": "📦 所有产出物已保存",
}


def _format_node_message(node_name: str, node_output: dict, state_values: dict) -> str:
    """Format the push message for a completed node."""
    template = _NODE_MESSAGES.get(node_name)
    if not template:
        return ""

    summary = ""
    if node_name == "writer":
        script = node_output.get("current_script", "")
        summary = script[:800] + ("..." if len(script) > 800 else "")
    elif node_name == "director_review":
        review = node_output.get("director_review", "")
        summary = review[:600] + ("..." if len(review) > 600 else "")
    elif node_name == "user_gate":
        review = state_values.get("director_review", "")
        script_preview = state_values.get("current_script", "")[:300]
        summary = f"📋 剧本摘要:\n{script_preview}...\n\n📝 审核意见:\n{review[:500]}"
    elif node_name == "storyboard":
        sb = node_output.get("final_storyboard", "")
        summary = sb[:600] + ("..." if len(sb) > 600 else "")
    elif node_name == "director_final_review":
        review = node_output.get("director_review", "")
        summary = review[:600] + ("..." if len(review) > 600 else "")

    return template.format(summary=summary)


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

    msg = (
        f"📊 当前状态\n\n"
        f"🔄 工作流: {status}\n"
        f"📍 最后节点: {last_node}{paused_at}\n"
        f"📎 已加载素材: {len(refs['images'])} 张图片, {len(refs['text'])} 字符文本"
    )
    send_text(chat_id, msg)


def _handle_help(chat_id: str):
    """Show available commands."""
    send_text(chat_id, (
        "📖 可用命令\n\n"
        "/read_folder <token或链接>\n"
        "　　读取飞书文件夹中的文档和图片\n\n"
        "/read_doc <文档ID或链接>\n"
        "　　读取单个飞书文档\n\n"
        "/stop\n"
        "　　停止当前工作流\n\n"
        "/status\n"
        "　　查看当前状态和已加载素材\n\n"
        "/help\n"
        "　　显示此帮助信息\n\n"
        "💡 直接发送图片或文件会自动存入参考素材\n"
        "💡 发送文字直接与管家对话"
    ))


# ── Housekeeper Agent ─────────────────────────────────────────────────

def _handle_housekeeper(chat_id: str, message_id: str, text: str, thread_id: str):
    """Housekeeper direct conversation (not through LangGraph workflow)."""
    try:
        prompt = _load_housekeeper_prompt()

        # Maintain conversation history
        if thread_id not in _housekeeper_history:
            _housekeeper_history[thread_id] = []
        history = _housekeeper_history[thread_id]

        # Build messages
        messages = [SystemMessage(content=prompt)]

        # Add context about current state
        refs = _thread_refs.get(thread_id, {"text": "", "images": []})
        state_info = _thread_state.get(thread_id, {})
        context = (
            f"[系统上下文] 当前已加载素材: {len(refs['images'])} 张图片, "
            f"{len(refs['text'])} 字符文本。"
            f"工作流状态: {state_info.get('status', 'idle')}。"
        )
        messages.append(HumanMessage(content=context))

        # Add conversation history
        for msg in history[-_HOUSEKEEPER_MAX_HISTORY:]:
            messages.append(msg)

        # Add current message
        messages.append(HumanMessage(content=text))

        llm = get_housekeeper_llm()
        response = llm.invoke(messages)

        # Extract text: response.content may be str or list of content parts
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

        logger.info("Housekeeper reply (len=%d): %s", len(reply_content), reply_content[:100])

        # Save to history
        history.append(HumanMessage(content=text))
        history.append(response)

        # Trim history
        if len(history) > _HOUSEKEEPER_MAX_HISTORY * 2:
            _housekeeper_history[thread_id] = history[-_HOUSEKEEPER_MAX_HISTORY:]

        # Check if housekeeper wants to start a workflow
        if "[ACTION:START_WORKFLOW]" in reply_content:
            clean_reply = reply_content.replace("[ACTION:START_WORKFLOW]", "").strip()
            send_text(chat_id, clean_reply)
            logger.info("Housekeeper triggered workflow: thread=%s", thread_id)
            _run_workflow(chat_id, thread_id, text)
        else:
            send_text(chat_id, reply_content)

    except Exception as e:
        logger.error("Housekeeper error: %s", e, exc_info=True)
        send_text(chat_id, f"❌ 管家暂时无法回复: {e}")


# ── Workflow helpers ──────────────────────────────────────────────────

def _run_workflow(chat_id: str, thread_id: str, user_request: str):
    """Start a new workflow, injecting any preloaded references."""
    refs = _thread_refs.pop(thread_id, {"text": "", "images": []})

    _thread_state[thread_id] = {"status": "running", "chat_id": chat_id, "last_node": ""}

    send_text(chat_id, "🚀 创作工作流已启动\n\n✍️ Writer 正在编写剧本...")

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
        "reference_images": refs["images"],
        "reference_text": refs["text"],
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

                # Push message for key nodes
                msg = _format_node_message(current, node_output, accumulated_state)
                if msg:
                    send_text(chat_id, msg)

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
    graph_app.update_state(config, {"user_feedback": user_feedback})

    _thread_state[thread_id] = {"status": "running", "chat_id": chat_id, "last_node": ""}

    send_text(chat_id, "🔄 收到反馈，工作流恢复中...")

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

                # Get full state for message formatting
                full_state = graph_app.get_state(config).values
                msg = _format_node_message(current, node_output, full_state)
                if msg:
                    send_text(chat_id, msg)

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
    """Download image from message and store as reference."""
    try:
        image_key = content.get("image_key", "")
        if not image_key:
            return

        image_bytes = download_message_image(message_id, image_key)
        if image_bytes:
            refs = _ensure_thread_refs(thread_id)
            b64 = image_bytes_to_base64(image_bytes)
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
    """Download file from message and store appropriately."""
    try:
        file_key = content.get("file_key", "")
        file_name = content.get("file_name", "unknown")

        if not file_key:
            return

        # Check if it's an image file
        image_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
        ext = os.path.splitext(file_name)[1].lower()

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
        else:
            # Non-image files: acknowledge receipt, store token for future use
            send_text(
                chat_id,
                f"📎 文件 {file_name} 已收到\n\n"
                f"ℹ️ 当前支持图片类文件自动存入参考素材。\n"
                f"文档类文件请使用 /read_doc 命令读取飞书文档。",
            )
    except Exception as e:
        logger.error("Handle file message failed: %s", e, exc_info=True)
        send_text(chat_id, "❌ 文件处理失败，请重试。")


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
        if not text_content:
            return

        # --- Command dispatch ---

        # /help
        if _CMD_HELP.match(text_content):
            _handle_help(chat_id)
            return

        # /stop
        if _CMD_STOP.match(text_content):
            _handle_stop(chat_id, thread_id)
            return

        # /status
        if _CMD_STATUS.match(text_content):
            _handle_status(chat_id, thread_id)
            return

        # /read_folder <token_or_url>
        m = _CMD_READ_FOLDER.match(text_content)
        if m:
            folder_token = m.group(1)
            t = threading.Thread(
                target=_handle_read_folder,
                args=(chat_id, thread_id, folder_token),
                daemon=True,
            )
            t.start()
            return

        # /read_doc <doc_id_or_url>
        m = _CMD_READ_DOC.match(text_content)
        if m:
            doc_id = m.group(1)
            t = threading.Thread(
                target=_handle_read_doc,
                args=(chat_id, thread_id, doc_id),
                daemon=True,
            )
            t.start()
            return

        # --- Workflow resume (if paused) ---

        config = {"configurable": {"thread_id": thread_id}}
        try:
            state = graph_app.get_state(config)
            if state.next:
                logger.info("Resuming thread=%s with feedback: %s", thread_id, text_content[:50])
                t = threading.Thread(
                    target=_resume_workflow,
                    args=(chat_id, thread_id, text_content),
                    daemon=True,
                )
                t.start()
                return
        except Exception:
            pass

        # --- Default: Housekeeper Agent ---

        logger.info("Housekeeper handling: thread=%s, text=%s", thread_id, text_content[:50])
        t = threading.Thread(
            target=_handle_housekeeper,
            args=(chat_id, message_id, text_content, thread_id),
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
