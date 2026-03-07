"""飞书 WebSocket 长连接启动

每个 bot 在独立线程中运行，使用 SDK 自带的 start() 方法，
内置心跳和自动重连机制。

lark SDK 使用模块级 event loop，与 uvicorn 的运行中 loop 冲突，
通过 nest_asyncio 允许嵌套 run_until_complete 来解决。
"""

import logging
import threading

import nest_asyncio
import lark_oapi as lark

from src.tools.lark.websocket.bot_manager import collect_bot_configs

nest_asyncio.apply()

logger = logging.getLogger(__name__)


def _run_bot(app_id: str, app_secret: str, bot_name: str, event_handler):
    """单个 bot 的 WebSocket 运行循环。"""
    cli = lark.ws.Client(
        app_id, app_secret,
        event_handler=event_handler,
        log_level=lark.LogLevel.INFO,
    )
    logger.info("Starting bot [%s] WebSocket...", bot_name)
    try:
        cli.start()
    except Exception as e:
        logger.error("Bot [%s] WebSocket exited: %s", bot_name, e, exc_info=True)


def start_websocket(dispatcher) -> list[threading.Thread]:
    """为每个 bot 启动独立的 WebSocket 线程，返回线程列表。"""
    bot_configs = collect_bot_configs()
    if not bot_configs:
        logger.error("No bot credentials found — no WebSocket connections started.")
        return []

    event_handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(dispatcher.handle)
        .build()
    )

    threads = []
    for app_id, app_secret, bot_name in bot_configs:
        t = threading.Thread(
            target=_run_bot,
            args=(app_id, app_secret, bot_name, event_handler),
            daemon=True,
            name=f"ws-{bot_name}",
        )
        t.start()
        threads.append(t)

    logger.info("Launched %d bot WebSocket thread(s).", len(threads))
    return threads
