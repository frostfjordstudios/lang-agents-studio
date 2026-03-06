"""FastAPI + Feishu WebSocket Server

纯通讯层：FastAPI /health + 飞书 WebSocket 长连接。
所有消息分发逻辑在 src/tools/lark/dispatcher.py 中。
"""

import os
import asyncio
import logging
import threading
from pathlib import Path

import lark_oapi as lark
from fastapi import FastAPI

from src.agents.media_group.workflow import build_graph
from src.core.prompt_manager import preload_all
from src.tools.lark.msg.dispatcher import Dispatcher
from src.tools.lark.msg.multi_bot import AGENT_BOTS

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

# ── LangGraph app + Dispatcher ────────────────────────────────────────

preload_all()
graph_app = build_graph()
logger.info("LangGraph workflow compiled and ready.")

dispatcher = Dispatcher(graph_app)

# ── Feishu WebSocket（多机器人模式）──────────────────────────────────

def _start_bot_ws(app_id: str, app_secret: str, bot_name: str):
    """为单个机器人启动 WebSocket 长连接。"""
    import lark_oapi.ws.client as _ws_mod
    _ws_mod.loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_ws_mod.loop)

    event_handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(dispatcher.handle)
        .build()
    )

    cli = lark.ws.Client(
        app_id, app_secret,
        event_handler=event_handler,
        log_level=lark.LogLevel.INFO,
    )

    logger.info("Starting WebSocket for bot [%s]...", bot_name)
    cli.start()


def _launch_all_bots():
    """启动所有有凭证的机器人的 WebSocket 连接。"""
    launched = []

    # 主机器人（管家）
    main_id = os.environ.get("FEISHU_APP_ID", "")
    main_secret = os.environ.get("FEISHU_APP_SECRET", "")
    if main_id and main_secret:
        t = threading.Thread(target=_start_bot_ws, args=(main_id, main_secret, "main/housekeeper"), daemon=True)
        t.start()
        launched.append("main/housekeeper")

    # 各 Agent 独立机器人
    for name, config in AGENT_BOTS.items():
        if config.app_id and config.app_secret:
            # 跳过与主机器人相同凭证的（避免重复连接）
            if config.app_id == main_id:
                continue
            t = threading.Thread(target=_start_bot_ws, args=(config.app_id, config.app_secret, name), daemon=True)
            t.start()
            launched.append(name)

    if launched:
        logger.info("Launched %d bot WebSocket(s): %s", len(launched), ", ".join(launched))
    else:
        logger.error("No bot credentials found — no WebSocket connections started.")


_launch_all_bots()

# ── FastAPI ──────────────────────────────────────────────────────────

app = FastAPI(title="Feishu LangGraph Agent")


@app.get("/health")
async def health():
    return {"status": "ok"}
