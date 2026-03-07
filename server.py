"""FastAPI + Feishu WebSocket Server

纯通讯层：FastAPI /health + 飞书 WebSocket 长连接。
所有消息分发逻辑在 src/tools/lark/dispatcher.py 中。
"""

import logging
from pathlib import Path

from fastapi import FastAPI

from src.agents.media_group.workflow import build_graph
from src.services.prompt.preloader import preload_all
from src.tools.lark.dispatcher import Dispatcher
from src.tools.lark.websocket.connection import start_websocket

# ── 日志 ─────────────────────────────────────────────────────────────

_log_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")

_console = logging.StreamHandler()
_console.setLevel(logging.WARNING)
_console.setFormatter(_log_fmt)

_log_dir = Path(__file__).resolve().parent / "logs"
_log_dir.mkdir(exist_ok=True)
_file_handler = logging.FileHandler(_log_dir / "server.log", encoding="utf-8")
_file_handler.setLevel(logging.INFO)
_file_handler.setFormatter(_log_fmt)

logging.basicConfig(level=logging.INFO, handlers=[_console, _file_handler])
logger = logging.getLogger(__name__)

# ── 初始化 ────────────────────────────────────────────────────────────

preload_all()

from src.tools.lark.msg.multi_bot import fetch_all_bot_open_ids
fetch_all_bot_open_ids()

from src.tools.lark.docs.permissions import ensure_department_folders
ensure_department_folders()

graph_app = build_graph()
logger.info("LangGraph workflow compiled and ready.")

dispatcher = Dispatcher(graph_app)
start_websocket(dispatcher)

# ── FastAPI ──────────────────────────────────────────────────────────

app = FastAPI(title="Feishu LangGraph Agent")


@app.get("/health")
async def health():
    return {"status": "ok"}
