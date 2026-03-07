"""飞书 WebSocket 长连接启动

管家 bot 在独立线程中运行。
通过 importlib 重新加载 lark SDK 的 ws.client 模块，
让它在新线程的 event loop 上初始化，避免与 uvicorn loop 冲突。
"""

import asyncio
import importlib
import logging
import os
import threading

import lark_oapi as lark

logger = logging.getLogger(__name__)


def _run_bot(app_id: str, app_secret: str, bot_name: str, event_handler):
    """管家 bot 的 WebSocket 运行循环。

    重新加载 lark ws.client 模块，使其模块级 loop 绑定到当前线程的新 loop。
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # 重新加载让 SDK 用当前线程的 loop
    import lark_oapi.ws.client as ws_client
    importlib.reload(ws_client)

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
    finally:
        loop.close()


def start_websocket(dispatcher) -> None:
    """启动管家 bot 的 WebSocket 线程。"""
    main_id = os.environ.get("FEISHU_APP_ID", "")
    main_secret = os.environ.get("FEISHU_APP_SECRET", "")

    if not main_id or not main_secret:
        logger.error("FEISHU_APP_ID/SECRET not set — no WebSocket connection started.")
        return

    event_handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(dispatcher.handle)
        .build()
    )

    t = threading.Thread(
        target=_run_bot,
        args=(main_id, main_secret, "housekeeper", event_handler),
        daemon=True,
        name="ws-housekeeper",
    )
    t.start()
    logger.info("Housekeeper WebSocket thread launched.")
