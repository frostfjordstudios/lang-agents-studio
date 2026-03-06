"""多机器人架构模块 (Multi-Bot Architecture)

每个 Agent 对应一个独立的飞书应用/机器人，
在群聊中以各自身份发送消息，增强沉浸感。

环境变量格式（多机器人模式）：
  FEISHU_BOT_WRITER_APP_ID=cli_xxx
  FEISHU_BOT_WRITER_APP_SECRET=xxx
  ... 以此类推

Bot 配置从 registry.py 自动生成，新增 Agent 无需手动维护此文件。
"""

import os
import json
import logging
from typing import Optional
from dataclasses import dataclass, field

from dotenv import load_dotenv
import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
)

from src.core.registry import get_all_agents

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class BotConfig:
    """单个机器人的配置。"""
    agent_name: str
    display_name: str
    emoji: str
    app_id: str = ""
    app_secret: str = ""


# ── Agent -> Bot 映射配置（从 registry 自动生成）─────────────────────

AGENT_BOTS: dict[str, BotConfig] = {
    a.name: BotConfig(a.name, a.display_name, a.emoji)
    for a in get_all_agents()
}


def _load_bot_credentials():
    """从环境变量加载各 Agent 的独立 bot 凭证（如果配置了的话）。"""
    loaded = []
    for agent_name, config in AGENT_BOTS.items():
        env_prefix = f"FEISHU_BOT_{agent_name.upper()}"
        app_id = os.environ.get(f"{env_prefix}_APP_ID", "")
        app_secret = os.environ.get(f"{env_prefix}_APP_SECRET", "")
        if app_id and app_secret:
            config.app_id = app_id
            config.app_secret = app_secret
            loaded.append(agent_name)
        else:
            logger.debug("No credentials for %s (env: %s_APP_ID)", agent_name, env_prefix)

    if loaded:
        logger.info("Multi-bot mode: loaded %d bots — %s", len(loaded), ", ".join(loaded))
    else:
        logger.info("Single-bot mode: no independent bot credentials found")


# 模块加载时尝试读取
_load_bot_credentials()


# ── Bot Client 缓存 ─────────────────────────────────────────────────

_bot_clients: dict[str, lark.Client] = {}


def get_bot_client(agent_name: str) -> Optional[lark.Client]:
    """获取指定 Agent 的飞书 Client。"""
    config = AGENT_BOTS.get(agent_name)
    if not config or not config.app_id or not config.app_secret:
        return None

    if agent_name not in _bot_clients:
        _bot_clients[agent_name] = (
            lark.Client.builder()
            .app_id(config.app_id)
            .app_secret(config.app_secret)
            .log_level(lark.LogLevel.INFO)
            .build()
        )

    return _bot_clients[agent_name]


def get_agent_prefix(agent_name: str) -> str:
    """获取 Agent 的消息前缀（emoji + 名称）。"""
    config = AGENT_BOTS.get(agent_name)
    if config:
        return f"{config.emoji} {config.display_name} | "
    # 回退到 registry（覆盖新增但未重启的 Agent）
    from src.core.registry import get_display_name
    dn = get_display_name(agent_name)
    return f"{dn} | " if dn != agent_name else ""


def is_multi_bot_enabled(agent_name: str) -> bool:
    """检查指定 Agent 是否启用了独立 bot。"""
    config = AGENT_BOTS.get(agent_name)
    return bool(config and config.app_id and config.app_secret)


def send_as_agent(agent_name: str, chat_id: str, text: str) -> Optional[str]:
    """以指定 Agent 身份发送消息。

    如果该 Agent 有独立 bot，使用独立 bot 发送；
    否则使用默认 bot 发送，消息前加 Agent 身份前缀。
    """
    from .messaging import send_text, _strip_markdown

    client = get_bot_client(agent_name)

    if client:
        # Multi-bot mode: send via agent's own bot
        text = _strip_markdown(text)
        if len(text) > 30000:
            text = text[:30000] + "\n\n... (内容过长，已截断)"

        body = CreateMessageRequestBody.builder() \
            .receive_id(chat_id) \
            .msg_type("text") \
            .content(json.dumps({"text": text}, ensure_ascii=False)) \
            .build()
        request = CreateMessageRequest.builder() \
            .receive_id_type("chat_id") \
            .request_body(body) \
            .build()
        response = client.im.v1.message.create(request)

        if not response.success():
            logger.error(
                "Agent %s send failed: code=%s, msg=%s",
                agent_name, response.code, response.msg,
            )
            return None
        return response.data.message_id
    else:
        # Single-bot mode: housekeeper IS the main bot, no prefix needed;
        # other agents add prefix to identify themselves.
        if agent_name == "housekeeper":
            return send_text(chat_id, text)
        prefix = get_agent_prefix(agent_name)
        return send_text(chat_id, prefix + text)
