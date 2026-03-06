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

def _collect_bot_configs() -> list[tuple[str, str, str]]:
    """收集所有有凭证的机器人配置，返回 [(app_id, app_secret, name), ...]。"""
    bots = []
    main_id = os.environ.get("FEISHU_APP_ID", "")
    main_secret = os.environ.get("FEISHU_APP_SECRET", "")
    seen_ids = set()

    if main_id and main_secret:
        bots.append((main_id, main_secret, "main/housekeeper"))
        seen_ids.add(main_id)

    for name, config in AGENT_BOTS.items():
        if config.app_id and config.app_secret and config.app_id not in seen_ids:
            bots.append((config.app_id, config.app_secret, name))
            seen_ids.add(config.app_id)

    return bots


def _run_all_bots_ws():
    """在单个线程 + 单个 event loop 中运行所有机器人的 WebSocket。"""
    import lark_oapi.ws.client as _ws_mod

    bot_configs = _collect_bot_configs()
    if not bot_configs:
        logger.error("No bot credentials found — no WebSocket connections started.")
        return

    # 创建共享 event loop，替换模块级 loop
    shared_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(shared_loop)
    _ws_mod.loop = shared_loop

    event_handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(dispatcher.handle)
        .build()
    )

    async def _start_one(app_id, app_secret, bot_name):
        cli = lark.ws.Client(
            app_id, app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO,
        )
        logger.info("Connecting bot [%s]...", bot_name)
        try:
            await cli._connect()
        except Exception as e:
            logger.error("Bot [%s] connect failed: %s", bot_name, e)
            await cli._disconnect()
            if cli._auto_reconnect:
                await cli._reconnect()
            else:
                return
        shared_loop.create_task(cli._ping_loop())
        logger.info("Bot [%s] connected.", bot_name)

    async def _main():
        tasks = [_start_one(aid, asec, name) for aid, asec, name in bot_configs]
        await asyncio.gather(*tasks)
        logger.info("All %d bot(s) connected, entering event loop.", len(bot_configs))
        # 永久阻塞，保持 WebSocket 连接
        await _ws_mod._select()

    shared_loop.run_until_complete(_main())


_ws_thread = threading.Thread(target=_run_all_bots_ws, daemon=True)
_ws_thread.start()
logger.info("Feishu multi-bot WebSocket thread launched.")

# ── FastAPI ──────────────────────────────────────────────────────────

app = FastAPI(title="Feishu LangGraph Agent")


@app.get("/health")
async def health():
    return {"status": "ok"}
