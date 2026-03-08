"""本地 WebSocket 测试 — 模拟完整 server.py 启动流程

启动后在飞书群发消息，观察终端输出。
Ctrl+C 退出。
"""

import os
import sys
import json
import logging
import asyncio
import threading

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("test_ws")

# ── 1. 纯 WebSocket 连接测试（不依赖项目代码）──────────────────────

def test_raw_websocket():
    """只测试 WebSocket 能否连接并收到消息。"""
    import lark_oapi as lark

    app_id = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")

    if not app_id or not app_secret:
        logger.error("FEISHU_APP_ID / FEISHU_APP_SECRET 未设置")
        return

    def on_message(data):
        logger.info("=" * 50)
        logger.info("收到消息事件!")
        try:
            msg = data.event.message
            content = json.loads(msg.content) if msg.content else {}
            logger.info("  chat_id: %s", msg.chat_id)
            logger.info("  msg_type: %s", msg.message_type)
            logger.info("  content: %s", content)
            logger.info("  message_id: %s", msg.message_id)
        except Exception as e:
            logger.error("  解析失败: %s", e)
        logger.info("=" * 50)

    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        import lark_oapi.ws.client as ws_mod
        ws_mod.loop = loop

        event_handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(on_message)
            .build()
        )
        cli = ws_mod.Client(
            app_id, app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.DEBUG,
        )
        logger.info("启动 WebSocket...")
        cli.start()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    logger.info("WebSocket 线程已启动，等待飞书消息...")

    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("已退出")


# ── 2. 完整 Dispatcher 测试（测试项目消息处理链路）──────────────────

def test_with_dispatcher():
    """用项目的 Dispatcher 测试完整消息处理链路。"""
    from src.services.prompt.preloader import preload_all
    from src.agents.media_group.workflow import build_graph
    from src.tools.lark.dispatcher import Dispatcher
    from src.tools.lark.websocket.connection import start_websocket
    from src.tools.lark.msg.multi_bot import fetch_all_bot_open_ids

    preload_all()
    fetch_all_bot_open_ids()

    graph_app = build_graph()
    logger.info("LangGraph workflow compiled.")

    dispatcher = Dispatcher(graph_app)
    start_websocket(dispatcher)

    logger.info("完整 Dispatcher 已启动，等待飞书消息...")
    logger.info("发送 @test 切换测试模式，@help 查看帮助")

    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("已退出")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "raw"

    if mode == "raw":
        print("模式: raw — 纯 WebSocket 连接测试")
        print("用法: python test_ws.py [raw|full]")
        print()
        test_raw_websocket()
    elif mode == "full":
        print("模式: full — 完整 Dispatcher 测试")
        print()
        test_with_dispatcher()
    else:
        print(f"未知模式: {mode}")
        print("用法: python test_ws.py [raw|full]")
        sys.exit(1)
