"""LLM 配置模块 — 温度由全局 Agent 注册表驱动

所有角色的温度设定统一在 registry.py 中管理，
本模块只负责构建 LLM 实例。
"""

import os
import logging
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

logger = logging.getLogger(__name__)

_MODEL = "gemini-3.1-pro-preview"

from src.core.registry import get_temperature  # noqa: E402


# ── 核心构建函数 ─────────────────────────────────────────────────────

def _build_llm(temperature: float) -> ChatGoogleGenerativeAI:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.error(
            "GEMINI_API_KEY 或 GOOGLE_API_KEY 未设置，请在 .env 文件或环境变量中配置"
        )
        raise ValueError(
            "GEMINI_API_KEY 或 GOOGLE_API_KEY 未设置，请在 .env 文件或环境变量中配置"
        )
    return ChatGoogleGenerativeAI(
        model=_MODEL,
        google_api_key=api_key,
        temperature=temperature,
        convert_system_message_to_human=True,
    )


def get_llm(role: str) -> ChatGoogleGenerativeAI:
    """根据角色名获取对应温度的 LLM 实例（温度由 registry 驱动）。"""
    temp = get_temperature(role)
    return _build_llm(temperature=temp)
