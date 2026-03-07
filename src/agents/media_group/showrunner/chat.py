"""制片人对话 — 编排入口"""

import logging
from langchain_core.messages import SystemMessage, HumanMessage

from src.tools.llm import get_llm
from src.agents.organization import get_temperature
from src.services.prompt.loader import get_agent_prompt
from src.tools.lark.msg.messaging import send_text
from src.tools.lark.msg.multi_bot import send_as_agent
from src.tools.search import SEARCH_TOOLS
from src.tools.llm import extract_text
from src.agents.state.context import get_agent_context
from src.agents.media_group.showrunner.history import get_history, append_and_trim

logger = logging.getLogger(__name__)


def _invoke_with_search(llm, messages):
    from langchain_core.messages import ToolMessage
    llm_with_tools = llm.bind_tools(SEARCH_TOOLS)
    response = llm_with_tools.invoke(messages)
    if response.tool_calls:
        msgs = list(messages) + [response]
        search_tool = SEARCH_TOOLS[0]
        for tc in response.tool_calls:
            result = search_tool.invoke(tc["args"])
            msgs.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
        response = llm_with_tools.invoke(msgs)
    return response


def handle_showrunner(chat_id, message_id, text, thread_id,
                      thread_refs, thread_state, on_start_workflow=None):
    try:
        prompt = get_agent_prompt("showrunner")
        refs = thread_refs.get(thread_id, {"text": "", "images": []})
        state_info = thread_state.get(thread_id, {})
        project = state_info.get("project", f"proj_{thread_id[-8:]}")
        showrunner_ctx = get_agent_context(project, "showrunner")

        context = (
            f"[系统上下文] 已加载素材: {len(refs['images'])} 张图片, "
            f"{len(refs['text'])} 字符文本。"
            f"工作流状态: {state_info.get('status', 'idle')}。\n\n"
            f"你是制片总监，是用户的主要对接人。"
            f"当用户表达明确创作需求时，在回复末尾加 [ACTION:START_WORKFLOW]。"
        )
        if showrunner_ctx:
            context += f"\n\n{showrunner_ctx}"

        history = get_history(thread_id)
        messages = [SystemMessage(content=prompt), HumanMessage(content=context)]
        messages.extend(history[-20:])
        messages.append(HumanMessage(content=text))

        llm = get_llm(temperature=get_temperature("showrunner"))
        response = _invoke_with_search(llm, messages)
        reply_content = extract_text(response.content)

        append_and_trim(thread_id, HumanMessage(content=text), response)

        if "[ACTION:START_WORKFLOW]" in reply_content:
            clean = reply_content.replace("[ACTION:START_WORKFLOW]", "").strip()
            send_as_agent("showrunner", chat_id, clean)
            if on_start_workflow:
                on_start_workflow(chat_id, thread_id, text)
        else:
            send_as_agent("showrunner", chat_id, reply_content)

    except Exception as e:
        logger.error("Showrunner error: %s", e, exc_info=True)
        send_text(chat_id, f"制片暂时无法回复: {e}")
