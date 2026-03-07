"""飞书多机器人凭证收集"""

import os

from src.tools.lark.msg.multi_bot import AGENT_BOTS


def collect_bot_configs() -> list[tuple[str, str, str]]:
    """收集所有有凭证的机器人配置，返回 [(app_id, app_secret, name), ...]。"""
    bots = []
    main_id = os.environ.get("FEISHU_APP_ID", "")
    main_secret = os.environ.get("FEISHU_APP_SECRET", "")
    seen_ids: set[str] = set()

    if main_id and main_secret:
        bots.append((main_id, main_secret, "main/housekeeper"))
        seen_ids.add(main_id)

    for name, config in AGENT_BOTS.items():
        if config.app_id and config.app_secret and config.app_id not in seen_ids:
            bots.append((config.app_id, config.app_secret, name))
            seen_ids.add(config.app_id)

    return bots
