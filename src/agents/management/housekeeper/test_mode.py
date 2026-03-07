"""TEST_MODE 运行时切换 — 支持 /test 和 /work 命令一键切换"""

import os
import logging

from langchain_core.messages import SystemMessage, HumanMessage

from src.tools.lark.msg.multi_bot import send_as_agent
from src.tools.llm import get_llm, extract_text

logger = logging.getLogger(__name__)

_state = {
    "test_mode": os.environ.get("TEST_MODE", "").strip().lower() in ("1", "true", "yes"),
    "all_speak": os.environ.get("TEST_MODE_ALL_AGENTS_SPEAK", "1").strip().lower() in ("1", "true", "yes"),
}

_TEST_PROMPT_TPL = "你是{name}。用一句话简短回复。"
_TEST_AGENTS = ["showrunner", "writer", "director", "art_design", "voice_design", "storyboard"]


def is_test_mode() -> bool:
    return _state["test_mode"]


def is_all_agents_speak() -> bool:
    return _state["all_speak"]


def set_test_mode(enabled: bool):
    _state["test_mode"] = enabled
    logger.info("TEST_MODE switched to: %s", enabled)


def set_all_agents_speak(enabled: bool):
    _state["all_speak"] = enabled


def test_llm_reply(agent_name: str, user_text: str) -> str:
    """Test 模式统一 LLM 调用：极简 prompt + 截断输入 + 短回复。"""
    llm = get_llm(temperature=0.3)
    response = llm.invoke([
        SystemMessage(content=_TEST_PROMPT_TPL.format(name=agent_name)),
        HumanMessage(content=user_text[:100]),
    ])
    return extract_text(response.content) or "在线"


def test_reply_as_agent(agent_name: str, chat_id: str, user_text: str):
    """Test 模式：调用 LLM 并以 agent 身份发送回复。"""
    try:
        reply = test_llm_reply(agent_name, user_text)
        send_as_agent(agent_name, chat_id, reply)
    except Exception as e:
        logger.error("Test reply %s error: %s", agent_name, e)
        send_as_agent(agent_name, chat_id, f"LLM连接失败: {e}")


def broadcast_test_updates(chat_id: str, thread_id: str):
    """所有 Agent 各自调用 LLM 回复，验证全链路连通性。"""
    project = f"test_{thread_id[-6:]}" if thread_id else "test_session"
    user_msg = f"项目：{project}，请报告你的状态。"
    for agent_name in _TEST_AGENTS:
        test_reply_as_agent(agent_name, chat_id, user_msg)
