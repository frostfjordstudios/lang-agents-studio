"""FastAPI + Feishu WebSocket Long-Connection Server

Uses lark-oapi SDK's WebSocket client to receive Feishu events
via long connection (no public URL or webhook needed).
FastAPI only serves a /health endpoint for cloud platform probes.

Supported user commands (in Feishu chat):
  /read_folder <folder_token_or_url>  - Read all docs & images from a Feishu folder
  /read_doc <document_id>             - Read a single Feishu Docx document
  (any other text)                    - Start or resume the LangGraph workflow
"""

import os
import re
import json
import uuid
import logging
import threading

import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.graph import build_graph
from src.tools.feishu_integration import (
    read_all_from_folder,
    read_feishu_docx,
    list_folder_files,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── LangGraph app (singleton) ───────────────────────────────────────

graph_app = None

# Per-thread preloaded reference materials (text + images)
# Populated by /read_folder or /read_doc commands before workflow starts
_thread_refs: dict[str, dict] = {}

# ── Command patterns ────────────────────────────────────────────────

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


# ── Command handlers ────────────────────────────────────────────────

def _ensure_thread_refs(thread_id: str) -> dict:
    if thread_id not in _thread_refs:
        _thread_refs[thread_id] = {"text": "", "images": []}
    return _thread_refs[thread_id]


def _handle_read_folder(thread_id: str, folder_token: str):
    """Read a Feishu folder and cache results for this thread."""
    try:
        result = read_all_from_folder(folder_token)
        refs = _ensure_thread_refs(thread_id)
        if result["text_content"]:
            refs["text"] += ("\n\n" if refs["text"] else "") + result["text_content"]
        refs["images"].extend(result["image_list"])
        logger.info(
            "/read_folder %s done: +%d chars text, +%d images (thread=%s)",
            folder_token, len(result["text_content"]), len(result["image_list"]), thread_id,
        )
    except Exception as e:
        logger.error("/read_folder %s failed: %s", folder_token, e, exc_info=True)


def _handle_read_doc(thread_id: str, document_id: str):
    """Read a single Feishu Docx and cache results for this thread."""
    try:
        result = read_feishu_docx(document_id)
        refs = _ensure_thread_refs(thread_id)
        if result["text"]:
            refs["text"] += ("\n\n" if refs["text"] else "") + result["text"]
        refs["images"].extend(result["images"])
        logger.info(
            "/read_doc %s done: +%d chars text, +%d images (thread=%s)",
            document_id, len(result["text"]), len(result["images"]), thread_id,
        )
    except Exception as e:
        logger.error("/read_doc %s failed: %s", document_id, e, exc_info=True)


# ── Workflow helpers ─────────────────────────────────────────────────

def _run_workflow(thread_id: str, user_request: str):
    """Start a new workflow, injecting any preloaded references."""
    refs = _thread_refs.pop(thread_id, {"text": "", "images": []})

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

    for event in graph_app.stream(initial_state, config):
        for node_name, node_output in event.items():
            current = node_output.get("current_node", node_name)
            logger.info("Node completed: %s (thread=%s)", current, thread_id)

    state = graph_app.get_state(config)
    if state.next:
        logger.info("Workflow paused before: %s (thread=%s)", state.next, thread_id)
    else:
        logger.info("Workflow finished (thread=%s)", thread_id)


def _resume_workflow(thread_id: str, user_feedback: str):
    """Resume a paused workflow with user feedback."""
    config = {"configurable": {"thread_id": thread_id}}
    graph_app.update_state(config, {"user_feedback": user_feedback})

    for event in graph_app.stream(None, config):
        for node_name, node_output in event.items():
            current = node_output.get("current_node", node_name)
            logger.info("Node completed: %s (thread=%s)", current, thread_id)

    state = graph_app.get_state(config)
    if state.next:
        logger.info("Workflow paused again before: %s (thread=%s)", state.next, thread_id)
    else:
        logger.info("Workflow finished (thread=%s)", thread_id)


# ── Feishu message handler ──────────────────────────────────────────

def _handle_feishu_message(data: P2ImMessageReceiveV1) -> None:
    """Handle im.message.receive_v1 event from Feishu WebSocket."""
    try:
        message = data.event.message
        msg_type = message.message_type

        if msg_type != "text":
            logger.info("Ignored non-text message type: %s", msg_type)
            return

        text_content = json.loads(message.content).get("text", "").strip()
        if not text_content:
            logger.info("Ignored empty message")
            return

        chat_id = message.chat_id
        thread_id = chat_id or str(uuid.uuid4())

        # --- Command dispatch ---

        # /read_folder <token_or_url>
        m = _CMD_READ_FOLDER.match(text_content)
        if m:
            folder_token = m.group(1)
            logger.info("/read_folder command: %s (thread=%s)", folder_token, thread_id)
            t = threading.Thread(target=_handle_read_folder, args=(thread_id, folder_token), daemon=True)
            t.start()
            return

        # /read_doc <doc_id_or_url>
        m = _CMD_READ_DOC.match(text_content)
        if m:
            doc_id = m.group(1)
            logger.info("/read_doc command: %s (thread=%s)", doc_id, thread_id)
            t = threading.Thread(target=_handle_read_doc, args=(thread_id, doc_id), daemon=True)
            t.start()
            return

        # --- Workflow dispatch ---

        # Check if there is a paused workflow for this thread
        config = {"configurable": {"thread_id": thread_id}}
        try:
            state = graph_app.get_state(config)
            if state.next:
                logger.info("Resuming thread=%s with feedback: %s", thread_id, text_content[:50])
                t = threading.Thread(target=_resume_workflow, args=(thread_id, text_content), daemon=True)
                t.start()
                return
        except Exception:
            pass

        # No paused workflow, start a new one
        logger.info("Starting new workflow thread=%s: %s", thread_id, text_content[:50])
        t = threading.Thread(target=_run_workflow, args=(thread_id, text_content), daemon=True)
        t.start()

    except Exception as e:
        logger.error("Error handling Feishu message: %s", e, exc_info=True)


# ── Feishu WebSocket client ─────────────────────────────────────────

def _start_feishu_ws():
    """Initialize and start the Feishu WebSocket long-connection client.

    Runs in a daemon thread so it does not block FastAPI startup.
    """
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


# ── FastAPI lifespan ─────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global graph_app
    graph_app = build_graph()
    logger.info("LangGraph workflow compiled and ready.")

    # Start Feishu WebSocket client in a background daemon thread
    ws_thread = threading.Thread(target=_start_feishu_ws, daemon=True)
    ws_thread.start()
    logger.info("Feishu WebSocket thread launched.")

    yield


app = FastAPI(title="Feishu LangGraph Agent", lifespan=lifespan)


# ── Health check (for cloud platform probes) ────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}
