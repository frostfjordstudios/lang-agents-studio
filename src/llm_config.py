"""LLM 配置模块 - 使用 Google Gemini 作为基础大模型"""

import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()


_MODEL = "gemini-3.1-pro-preview"


def _build_llm(temperature: float) -> ChatGoogleGenerativeAI:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY 未设置，请在 .env 文件中配置")
    return ChatGoogleGenerativeAI(
        model=_MODEL,
        google_api_key=api_key,
        temperature=temperature,
        convert_system_message_to_human=True,
    )


# ── 预置实例（按角色分配） ───────────────────────────────────────────
# Writer, Art-Design, Voice-Design
llm_creative = _build_llm(temperature=0.7)
# Director
llm_slight = _build_llm(temperature=0.15)
# Showrunner
llm_strict = _build_llm(temperature=0.1)
# Storyboard-Artist
llm_coder = _build_llm(temperature=0.05)
