"""飞书 SDK Client 初始化

提供全局共享的飞书 Client 构建函数。
所有飞书模块（message, drive, multi_bot）统一从此处获取 Client。
"""

import os
import logging

import lark_oapi as lark

logger = logging.getLogger(__name__)


def get_client() -> lark.Client:
    """构建飞书 SDK Client（延迟创建，每次调用时读取环境变量）。"""
    app_id = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")
    if not app_id or not app_secret:
        raise ValueError("FEISHU_APP_ID 或 FEISHU_APP_SECRET 未设置")
    return lark.Client.builder() \
        .app_id(app_id) \
        .app_secret(app_secret) \
        .log_level(lark.LogLevel.INFO) \
        .build()
