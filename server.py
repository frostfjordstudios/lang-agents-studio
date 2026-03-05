"""FastAPI Feishu Webhook Server

Receive Feishu event callbacks, route messages to LangGraph workflow.
"""

import uuid
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, BackgroundTasks
from pydantic import BaseModel

from src.graph import build_graph

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── LangGraph app (singleton) ───────────────────────────────────────

graph_app = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global graph_app
    graph_app = build_graph()
    logger.info("LangGraph workflow compiled and ready.")
    yield


app = FastAPI(title="Feishu LangGraph Agent", lifespan=lifespan)


# ── Schemas ──────────────────────────────────────────────────────────

class FeishuChallenge(BaseModel):
    challenge: str


# ── Background task: run / resume workflow ───────────────────────────

def _run_workflow(thread_id: str, user_request: str):
    """Start a new workflow in a background thread."""
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


# ── Feishu Webhook Endpoint ──────────────────────────────────────────

@app.post("/feishu/webhook")
async def feishu_webhook(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()

    # 1. URL Challenge verification
    if body.get("type") == "url_verification":
        return {"challenge": body["challenge"]}

    # 2. Extract message from Feishu event callback (v2.0 schema)
    event = body.get("event", {})
    message = event.get("message", {})
    msg_type = message.get("message_type", "")
    chat_id = message.get("chat_id", "")

    if msg_type != "text":
        return {"code": 0, "msg": "ignored non-text message"}

    import json as _json
    text_content = _json.loads(message.get("content", "{}")).get("text", "").strip()
    if not text_content:
        return {"code": 0, "msg": "empty message"}

    # Use chat_id as thread_id for conversation continuity.
    # If no chat_id, generate a new thread.
    thread_id = chat_id or str(uuid.uuid4())

    # Check if there is an existing paused workflow for this thread
    config = {"configurable": {"thread_id": thread_id}}
    try:
        state = graph_app.get_state(config)
        if state.next:
            # Workflow is paused at user_gate, treat message as feedback
            logger.info("Resuming thread=%s with feedback: %s", thread_id, text_content[:50])
            background_tasks.add_task(_resume_workflow, thread_id, text_content)
            return {"code": 0, "msg": "resuming workflow"}
    except Exception:
        pass

    # No paused workflow, start a new one
    logger.info("Starting new workflow thread=%s: %s", thread_id, text_content[:50])
    background_tasks.add_task(_run_workflow, thread_id, text_content)
    return {"code": 0, "msg": "workflow started"}


# ── Health check ─────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}
