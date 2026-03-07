"""飞书测试机器人 — 本地运行，打印收到的原始消息数据

用法：
  1. 设置环境变量 TEST_BOT_APP_ID 和 TEST_BOT_APP_SECRET
  2. python test_bot.py
  3. 在飞书给测试机器人发消息，观察控制台输出
"""

import os
import json
import logging
import asyncio
import threading

from dotenv import load_dotenv
import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("test_bot")


def on_message(data: P2ImMessageReceiveV1) -> None:
    """收到消息时，打印完整的原始数据结构。"""
    message = data.event.message
    sender = data.event.sender

    logger.info("=" * 60)
    logger.info("收到消息!")
    logger.info("-" * 60)

    # 打印 sender 信息
    logger.info("[Sender]")
    logger.info("  sender_id : %s", getattr(sender, "sender_id", None))
    logger.info("  sender_type: %s", getattr(sender, "sender_type", None))

    # 打印 message 基本字段
    logger.info("[Message]")
    logger.info("  message_id  : %s", message.message_id)
    logger.info("  msg_type    : %s", message.message_type)
    logger.info("  chat_id     : %s", message.chat_id)
    logger.info("  chat_type   : %s", getattr(message, "chat_type", None))
    logger.info("  create_time : %s", getattr(message, "create_time", None))

    # 打印原始 content（关键：看这里有没有混入 signature 等字段）
    logger.info("[Content RAW]")
    logger.info("  type: %s", type(message.content))
    logger.info("  value: %s", message.content)

    # 尝试 JSON 解析并美化打印
    if message.content:
        try:
            parsed = json.loads(message.content)
            logger.info("[Content PARSED]")
            for key, value in parsed.items():
                val_str = str(value)
                if len(val_str) > 200:
                    val_str = val_str[:200] + "..."
                logger.info("  %s: %s", key, val_str)
        except json.JSONDecodeError as e:
            logger.warning("  Content is not valid JSON: %s", e)

    # 打印 mentions
    mentions = getattr(message, "mentions", None)
    if mentions:
        logger.info("[Mentions]")
        raw_mentions = getattr(mentions, "items", mentions) if not isinstance(mentions, list) else mentions
        for i, m in enumerate(raw_mentions):
            if isinstance(m, dict):
                logger.info("  [%d] %s", i, m)
            else:
                logger.info("  [%d] key=%s name=%s id=%s",
                            i, getattr(m, "key", "?"),
                            getattr(m, "name", "?"),
                            getattr(m, "id", "?"))

    # 打印 data.event 上的其他字段（检查有没有 signature 等）
    logger.info("[Event 其他属性]")
    for attr in dir(data.event):
        if attr.startswith("_"):
            continue
        if attr in ("message", "sender"):
            continue
        val = getattr(data.event, attr, None)
        if val is not None and not callable(val):
            logger.info("  %s: %s", attr, str(val)[:200])

    logger.info("=" * 60)


def main():
    app_id = os.getenv("TEST_BOT_APP_ID", "")
    app_secret = os.getenv("TEST_BOT_APP_SECRET", "")

    if not app_id or not app_secret:
        logger.error("请设置环境变量 TEST_BOT_APP_ID 和 TEST_BOT_APP_SECRET")
        return

    event_handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(on_message)
        .build()
    )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    cli = lark.ws.Client(
        app_id, app_secret,
        event_handler=event_handler,
        log_level=lark.LogLevel.DEBUG,
    )

    logger.info("测试机器人启动中... (Ctrl+C 退出)")
    try:
        cli.start()
    except KeyboardInterrupt:
        logger.info("测试机器人已停止")


if __name__ == "__main__":
    main()
