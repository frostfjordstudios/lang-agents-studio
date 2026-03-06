"""Agent 对话服务 — 管家、制片、通用 Agent 对话

职责：
  - handle_housekeeper: 管家 ReAct Agent（搜索 + Prompt 编辑 + 进化工具）
  - handle_showrunner: 制片直接对话（可触发工作流）
  - handle_agent_chat: 通用 Agent 对话（带搜索能力）
"""

import random
import logging
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from src.core.llm_config import get_llm
from src.core.prompt_manager import get_agent_prompt
from src.tools.lark.msg.messaging import send_text
from src.tools.lark.msg.multi_bot import send_as_agent
from src.services.ai.search import SEARCH_TOOLS, get_search_tool
from src.services.dev.prompt_editor import PROMPT_EDITOR_TOOLS
from src.services.dev.evolution import EVOLUTION_TOOLS
from src.agents.persona import generate_idle_replies, _extract_text
from src.agents.agent_state import get_agent_context
from src.core.long_term_memory import add_memory, retrieve_memory
from langgraph.prebuilt import create_react_agent

logger = logging.getLogger(__name__)

# 对话历史上限
_MAX_HISTORY = 20

# 每个线程的对话历史
_housekeeper_history: dict[str, list] = {}
_showrunner_history: dict[str, list] = {}


def _invoke_with_search(llm, messages):
    """LLM + 搜索工具单轮调用。"""
    from langchain_core.messages import ToolMessage

    llm_with_tools = llm.bind_tools(SEARCH_TOOLS)
    response = llm_with_tools.invoke(messages)

    if response.tool_calls:
        messages_with_tools = list(messages) + [response]
        search_tool = SEARCH_TOOLS[0]
        for tool_call in response.tool_calls:
            result = search_tool.invoke(tool_call["args"])
            messages_with_tools.append(
                ToolMessage(content=str(result), tool_call_id=tool_call["id"])
            )
        response = llm_with_tools.invoke(messages_with_tools)

    return response


def handle_housekeeper(chat_id: str, message_id: str, text: str, thread_id: str,
                       thread_refs: dict, thread_state: dict,
                       on_start_workflow=None):
    """管家 ReAct Agent 对话。"""
    try:
        # 检测"记住"指令，存入长期记忆
        _REMEMBER_PREFIXES = ("记住", "记住：", "记住:", "remember", "remember:")
        text_lower = text.strip().lower()
        for prefix in _REMEMBER_PREFIXES:
            if text_lower.startswith(prefix):
                memory_content = text[len(prefix):].strip()
                if memory_content:
                    ok = add_memory(thread_id, memory_content)
                    if ok:
                        send_as_agent("housekeeper", chat_id, f"已记住：{memory_content}")
                    else:
                        send_as_agent("housekeeper", chat_id, "记忆存储失败，但我会在本次对话中记住。")
                    return
                break

        prompt = get_agent_prompt("housekeeper")

        # 检索长期记忆注入上下文
        try:
            memories = retrieve_memory(thread_id, text, limit=5)
            if memories:
                memory_block = "\n".join(f"- {m}" for m in memories)
                prompt += f"\n\n[用户长期记忆]\n{memory_block}"
        except Exception:
            pass

        refs = thread_refs.get(thread_id, {"text": "", "images": []})
        state_info = thread_state.get(thread_id, {})
        prompt += (
            f"\n\n[系统上下文] 当前已加载素材: {len(refs['images'])} 张图片, "
            f"{len(refs['text'])} 字符文本。"
            f"工作流状态: {state_info.get('status', 'idle')}。"
            "\n\n你拥有以下能力："
            "\n1. 联网搜索：查找实时信息、行业资料"
            "\n2. 文件管理：读取、修改、创建 system_prompts/ 下的 agents 和 skills 提示词文件"
            "\n3. Agent 进化：一键更新任意 Agent 的 System Prompt"
            "\n当用户表达创作需求时，在回复末尾加 [ACTION:START_WORKFLOW] 启动工作流。"
        )

        if thread_id not in _housekeeper_history:
            _housekeeper_history[thread_id] = []
        history = _housekeeper_history[thread_id]

        recent = history[-_MAX_HISTORY:]
        messages = list(recent) + [HumanMessage(content=text)]

        llm = get_llm("housekeeper")
        tools = [get_search_tool()] + PROMPT_EDITOR_TOOLS + EVOLUTION_TOOLS
        housekeeper_agent = create_react_agent(llm, tools, prompt=prompt)

        result = housekeeper_agent.invoke({"messages": messages})

        reply_content = ""
        for msg in reversed(result["messages"]):
            if hasattr(msg, "content") and msg.content:
                if not hasattr(msg, "tool_calls") or not msg.tool_calls:
                    reply_content = _extract_text(msg.content)
                    break

        logger.info("Housekeeper reply (len=%d)", len(reply_content))

        history.append(HumanMessage(content=text))
        history.append(AIMessage(content=reply_content))
        if len(history) > _MAX_HISTORY * 2:
            _housekeeper_history[thread_id] = history[-_MAX_HISTORY:]

        if "[ACTION:START_WORKFLOW]" in reply_content:
            clean_reply = reply_content.replace("[ACTION:START_WORKFLOW]", "").strip()
            send_as_agent("housekeeper", chat_id, clean_reply)
            if on_start_workflow:
                on_start_workflow(chat_id, thread_id, text)
        else:
            send_as_agent("housekeeper", chat_id, reply_content)

            # 空闲闲聊：随机 1-2 个 Agent 也参与
            status = thread_state.get(thread_id, {}).get("status", "idle")
            if status in ("idle", "finished", "error", "stopped"):
                try:
                    count = random.randint(1, 2)
                    idle_replies = generate_idle_replies(text, count=count)
                    for role, idle_text in idle_replies:
                        send_as_agent(role, chat_id, idle_text)
                except Exception as idle_err:
                    logger.warning("Idle chat failed: %s", idle_err, exc_info=True)

    except Exception as e:
        logger.error("Housekeeper error: %s", e, exc_info=True)
        send_text(chat_id, f"❌ 管家暂时无法回复: {e}")


def handle_showrunner(chat_id: str, message_id: str, text: str, thread_id: str,
                      thread_refs: dict, thread_state: dict,
                      on_start_workflow=None):
    """制片对话（可触发工作流）。"""
    try:
        prompt = get_agent_prompt("showrunner")

        if thread_id not in _showrunner_history:
            _showrunner_history[thread_id] = []
        history = _showrunner_history[thread_id]

        messages = [SystemMessage(content=prompt)]

        refs = thread_refs.get(thread_id, {"text": "", "images": []})
        state_info = thread_state.get(thread_id, {})
        project = state_info.get("project", f"proj_{thread_id[-8:]}")

        showrunner_ctx = get_agent_context(project, "showrunner")

        context = (
            f"[系统上下文] 当前已加载素材: {len(refs['images'])} 张图片, "
            f"{len(refs['text'])} 字符文本。"
            f"工作流状态: {state_info.get('status', 'idle')}。"
            f"\n\n"
            f"你是制片总监 Showrunner，是用户的主要对接人。"
            f"当用户表达了明确的创作需求（如写剧本、制作短剧等），"
            f"请在回复末尾加上 [ACTION:START_WORKFLOW] 来启动工作流。"
            f"如果用户只是在闲聊或提问，正常回复即可，不要加标记。"
        )
        if showrunner_ctx:
            context += f"\n\n{showrunner_ctx}"
        messages.append(HumanMessage(content=context))

        for msg in history[-_MAX_HISTORY:]:
            messages.append(msg)
        messages.append(HumanMessage(content=text))

        llm = get_llm("showrunner")
        response = _invoke_with_search(llm, messages)

        raw = response.content
        if isinstance(raw, str):
            reply_content = raw
        elif isinstance(raw, list):
            reply_content = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in raw
            )
        else:
            reply_content = str(raw) if raw else ""

        history.append(HumanMessage(content=text))
        history.append(response)
        if len(history) > _MAX_HISTORY * 2:
            _showrunner_history[thread_id] = history[-_MAX_HISTORY:]

        if "[ACTION:START_WORKFLOW]" in reply_content:
            clean_reply = reply_content.replace("[ACTION:START_WORKFLOW]", "").strip()
            send_as_agent("showrunner", chat_id, clean_reply)
            if on_start_workflow:
                on_start_workflow(chat_id, thread_id, text)
        else:
            send_as_agent("showrunner", chat_id, reply_content)

    except Exception as e:
        logger.error("Showrunner error: %s", e, exc_info=True)
        send_text(chat_id, f"❌ 制片暂时无法回复: {e}")


def handle_agent_chat(agent_name: str, chat_id: str, message_id: str,
                      text: str, thread_id: str,
                      thread_refs: dict, thread_state: dict,
                      on_start_workflow=None):
    """通用 Agent 对话路由。"""
    if agent_name != "housekeeper":
        send_as_agent(agent_name, chat_id, "收到👌")

    if agent_name == "showrunner":
        handle_showrunner(chat_id, message_id, text, thread_id,
                          thread_refs, thread_state, on_start_workflow)
        return
    if agent_name == "housekeeper":
        handle_housekeeper(chat_id, message_id, text, thread_id,
                           thread_refs, thread_state, on_start_workflow)
        return

    # 通用 Agent：搜索 + 角色对话
    try:
        try:
            sys_prompt = get_agent_prompt(agent_name)
        except (ValueError, FileNotFoundError):
            sys_prompt = f"你是{agent_name}。"

        sys_prompt += "\n\n你可以使用搜索工具查找互联网上的信息来辅助回答。请用你的专业身份回复，保持角色特色。"

        from langchain.agents import AgentExecutor, create_tool_calling_agent
        from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

        llm = get_llm(agent_name)

        prompt = ChatPromptTemplate.from_messages([
            ("system", sys_prompt),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ])

        agent = create_tool_calling_agent(llm, SEARCH_TOOLS, prompt)
        executor = AgentExecutor(agent=agent, tools=SEARCH_TOOLS, verbose=False, max_iterations=3)

        result = executor.invoke({"input": text})
        reply = result.get("output", "")
        send_as_agent(agent_name, chat_id, reply)

    except Exception as e:
        logger.error("Agent %s chat error: %s", agent_name, e, exc_info=True)
        send_as_agent(agent_name, chat_id, "抱歉，处理时出了点问题，请稍后再试。")
