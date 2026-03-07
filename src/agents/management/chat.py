"""Agent 对话服务 — @Agent 对话

职责：
  - handle_agent_chat: 被 @提及 时，Agent 以自己的 System Prompt 回复
"""

import logging
from langchain_core.messages import SystemMessage, HumanMessage

from src.tools.llm import get_llm, extract_text
from src.services.prompt.loader import get_agent_prompt
from src.tools.lark.msg.multi_bot import send_as_agent
from src.agents.organization import get_temperature
from src.agents.management.housekeeper.test_mode import is_test_mode, test_reply_as_agent

logger = logging.getLogger(__name__)


def handle_agent_chat(agent_name: str, chat_id: str, message_id: str,
                      text: str, thread_id: str):
    """被 @提及 的 Agent 用自己的 System Prompt 回复用户。"""
    try:
        if is_test_mode():
            test_reply_as_agent(agent_name, chat_id, text)
            return

        try:
            sys_prompt = get_agent_prompt(agent_name)
        except (ValueError, FileNotFoundError):
            sys_prompt = f"你是{agent_name}。"

        llm = get_llm(temperature=get_temperature(agent_name))
        response = llm.invoke([
            SystemMessage(content=sys_prompt),
            HumanMessage(content=text),
        ])
        reply = extract_text(response.content)
        send_as_agent(agent_name, chat_id, reply or "收到。")
    except Exception as e:
        logger.error("Agent %s chat error: %s", agent_name, e, exc_info=True)
        send_as_agent(agent_name, chat_id, "收到。")
