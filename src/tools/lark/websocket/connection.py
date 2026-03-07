"""飞书 WebSocket 长连接启动

管家 bot 在独立线程中运行。
在线程中先设置新的 event loop，再 import lark SDK 构建 Client，
确保 SDK 的模块级 loop 变量绑定到线程自己的 loop。
"""

import asyncio
import logging
import os
import sys
import threading

logger = logging.getLogger(__name__)


def _run_bot(app_id: str, app_secret: str, bot_name: str, dispatcher):
    """管家 bot 的 WebSocket 运行循环。"""
    # 1. 创建并设置线程独立的 event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # 2. 强制 lark SDK ws 模块重新初始化，绑定到当前线程的 loop
    import importlib
    import lark_oapi.ws.client as ws_mod
    importlib.reload(ws_mod)

    import lark_oapi as lark

    # 3. 用 reload 后的模块创建 Client
    event_handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(dispatcher.handle)
        .build()
    )

    cli = ws_mod.Client(
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

    t = threading.Thread(
        target=_run_bot,
        args=(main_id, main_secret, "housekeeper", dispatcher),
        daemon=True,
        name="ws-housekeeper",
    )
    t.start()
    logger.info("Housekeeper WebSocket thread launched.")
