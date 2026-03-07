"""LLM 实例构建 — 纯工具，不依赖 agents 层"""

import os
import logging
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

logger = logging.getLogger(__name__)

_MODEL = "gemini-3.1-pro-preview"


def get_llm(temperature: float = 0.5) -> ChatGoogleGenerativeAI:
    """按温度构建 LLM 实例。调用方自行从 organization 查温度。"""
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY 或 GOOGLE_API_KEY 未设置")
    return ChatGoogleGenerativeAI(
        model=_MODEL,
        google_api_key=api_key,
        temperature=temperature,
        convert_system_message_to_human=True,
    )


def sanitize_input(text: str) -> str:
    """清理传入 LLM 的用户文本，去除可能混入的非文本内容。"""
    if not isinstance(text, str):
        text = str(text)
    # 去除零宽字符
    text = text.replace("\u200b", "").replace("\u200c", "").replace("\u200d", "").replace("\ufeff", "")
    # 只保留可见文本，去除首尾空白
    return text.strip()


def extract_text(content) -> str:
    """从 LLM response.content 中提取纯文本（Gemini 有时返回 list[dict]）。"""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(item["text"])
        return "".join(parts).strip()
    return str(content).strip()
