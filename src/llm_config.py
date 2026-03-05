"""LLM 配置模块 - 使用 Google Gemini 作为基础大模型

所有 LLM 实例通过工厂函数延迟创建（Lazy Initialization），
确保应用启动时不会因环境变量缺失而崩溃。
"""

import os
import logging
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

logger = logging.getLogger(__name__)

_MODEL = "gemini-3.1-pro-preview"


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


# ── 工厂函数（按角色分配） ───────────────────────────────────────────

def get_creative_llm() -> ChatGoogleGenerativeAI:
    """Writer, Art-Design, Voice-Design 使用 (temperature=0.7)"""
    return _build_llm(temperature=0.7)


def get_slight_llm() -> ChatGoogleGenerativeAI:
    """Director 使用 (temperature=0.15)"""
    return _build_llm(temperature=0.15)


def get_strict_llm() -> ChatGoogleGenerativeAI:
    """Showrunner 使用 (temperature=0.1)"""
    return _build_llm(temperature=0.1)


def get_coder_llm() -> ChatGoogleGenerativeAI:
    """Storyboard-Artist 使用 (temperature=0.05)"""
    return _build_llm(temperature=0.05)


def get_housekeeper_llm() -> ChatGoogleGenerativeAI:
    """Housekeeper（项目管家）使用 (temperature=0.9)"""
    return _build_llm(temperature=0.9)
