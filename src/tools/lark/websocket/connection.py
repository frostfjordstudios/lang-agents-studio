"""飞书 WebSocket 长连接启动

管家 bot 在独立线程中运行 WebSocket。
"""

import asyncio
import logging
import os
import threading

logger = logging.getLogger(__name__)


def _run_bot(app_id: str, app_secret: str, bot_name: str, dispatcher):
    """管家 bot 的 WebSocket 运行循环 — 在全新的 event loop 上运行。"""
    import lark_oapi as lark

    # 在 import lark 之后，覆盖 SDK 的模块级 loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    import lark_oapi.ws.client as ws_mod
    ws_mod.loop = loop

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
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error("Bot [%s] WebSocket exited: %s", bot_name, e, exc_info=True)


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
