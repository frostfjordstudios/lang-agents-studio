"""管家 ReAct Agent 对话 — 编排入口"""

import logging
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.prebuilt import create_react_agent

from src.tools.llm import get_llm, extract_text
from src.agents.organization import get_temperature
from src.services.prompt.loader import get_agent_prompt
from src.services.memory.retrieve import retrieve_memory
from src.tools.lark.msg.messaging import send_text
from src.tools.lark.msg.multi_bot import send_as_agent
from src.tools.search import get_search_tool
from src.agents.management.housekeeper.prompt_tools import PROMPT_EDITOR_TOOLS
from src.agents.dev_group.evolution import EVOLUTION_TOOLS
from src.agents.management.housekeeper.remember import handle_remember
from src.agents.management.housekeeper.history import get_history, append_and_trim
from src.agents.management.housekeeper.test_mode import (
    is_test_mode, is_all_agents_speak, broadcast_test_updates,
    test_reply_as_agent,
)

logger = logging.getLogger(__name__)


def handle_housekeeper(chat_id, message_id, text, thread_id,
                       thread_refs, thread_state, on_start_workflow=None):
    try:
        # "记住"指令
        if handle_remember(chat_id, thread_id, text):
            return

        # TEST_MODE: 最小 LLM 调用
        if is_test_mode():
            test_reply_as_agent("housekeeper", chat_id, text)
            if is_all_agents_speak():
                broadcast_test_updates(chat_id, thread_id)
            return

        # 构建 prompt
        prompt = get_agent_prompt("housekeeper")
        try:
            memories = retrieve_memory(thread_id, text, limit=5)
            if memories:
                prompt += "\n\n[用户长期记忆]\n" + "\n".join(f"- {m}" for m in memories)
        except Exception:
            pass

        refs = thread_refs.get(thread_id, {"text": "", "images": []})
        state_info = thread_state.get(thread_id, {})
        prompt += (
            f"\n\n[系统上下文] 已加载素材: {len(refs['images'])} 张图片, "
            f"{len(refs['text'])} 字符文本。"
            f"工作流状态: {state_info.get('status', 'idle')}。"
            "\n\n你拥有联网搜索、Prompt 文件管理、Agent 进化能力。"
            "\n当用户表达创作需求时，在回复末尾加 [ACTION:START_WORKFLOW] 启动工作流。"
        )

        history = get_history(thread_id)
        messages = list(history[-20:]) + [HumanMessage(content=text)]

        llm = get_llm(temperature=get_temperature("housekeeper"))
        tools = [get_search_tool()] + PROMPT_EDITOR_TOOLS + EVOLUTION_TOOLS
        agent = create_react_agent(llm, tools, prompt=prompt)
        result = agent.invoke({"messages": messages})

        reply_content = ""
        for msg in reversed(result["messages"]):
            if hasattr(msg, "content") and msg.content:
                if not hasattr(msg, "tool_calls") or not msg.tool_calls:
                    reply_content = extract_text(msg.content)
                    break

        append_and_trim(thread_id, HumanMessage(content=text), AIMessage(content=reply_content))

        if "[ACTION:START_WORKFLOW]" in reply_content:
            clean = reply_content.replace("[ACTION:START_WORKFLOW]", "").strip()
            send_as_agent("housekeeper", chat_id, clean)
            if on_start_workflow:
                on_start_workflow(chat_id, thread_id, text)
        else:
            send_as_agent("housekeeper", chat_id, reply_content)

    except Exception as e:
        logger.error("Housekeeper error: %s", e, exc_info=True)
        send_text(chat_id, f"管家暂时无法回复: {e}")
