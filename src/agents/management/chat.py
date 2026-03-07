"""Agent 对话服务 — 管家默认对话 + @Agent 对话

职责：
  - handle_housekeeper: 管家 ReAct Agent（搜索 + Prompt 编辑 + 进化工具）
  - handle_agent_chat: 被 @提及 时，Agent 以自己人设回复
"""

import os
import logging
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from src.tools.llm import get_llm, extract_text as _extract_text
from src.services.prompt.loader import get_agent_prompt
from src.tools.lark.msg.messaging import send_text
from src.tools.lark.msg.multi_bot import send_as_agent
from src.tools.search import get_search_tool
from src.agents.management.housekeeper.prompt_tools import PROMPT_EDITOR_TOOLS
from src.agents.dev_group.evolution import EVOLUTION_TOOLS
from src.agents.organization import get_temperature
from src.services.memory.add import add_memory
from src.services.memory.retrieve import retrieve_memory
from langgraph.prebuilt import create_react_agent

logger = logging.getLogger(__name__)
TEST_MODE = os.environ.get("TEST_MODE", "").strip().lower() in ("1", "true", "yes")

_MAX_HISTORY = 20
_housekeeper_history: dict[str, list] = {}


def handle_housekeeper(chat_id: str, message_id: str, text: str, thread_id: str,
                       thread_refs: dict, thread_state: dict,
                       on_start_workflow=None):
    """管家 ReAct Agent 对话 — 用户的唯一默认对话入口。"""
    try:
        if TEST_MODE:
            llm = get_llm("housekeeper")
            short_messages = [
                SystemMessage(content=(
                    "你是项目管家。请用1-2句简短回复。"
                    "如果用户明确表达创作需求（剧本/分镜/创作/启动工作流），"
                    "在末尾追加 [ACTION:START_WORKFLOW]。"
                    "除该标记外不要输出多余解释。"
                )),
                HumanMessage(content=text),
            ]
            short_resp = llm.invoke(short_messages)
            short_reply = _extract_text(short_resp.content).strip() if short_resp else ""
            if "[ACTION:START_WORKFLOW]" in short_reply:
                clean_reply = short_reply.replace("[ACTION:START_WORKFLOW]", "").strip()
                send_as_agent("housekeeper", chat_id, clean_reply or "收到，准备启动。")
                if on_start_workflow:
                    on_start_workflow(chat_id, thread_id, text)
            else:
                send_as_agent("housekeeper", chat_id, short_reply or "收到。")
            return

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

    except Exception as e:
        logger.error("Housekeeper error: %s", e, exc_info=True)
        send_text(chat_id, f"管家暂时无法回复: {e}")


def handle_agent_chat(agent_name: str, chat_id: str, message_id: str,
                      text: str, thread_id: str):
    """被 @提及 的 Agent 用自己的 System Prompt 回复用户。

    只在用户通过飞书 @功能 指定某个 Agent 时触发。
    """
    try:
        try:
            sys_prompt = get_agent_prompt(agent_name)
        except (ValueError, FileNotFoundError):
            sys_prompt = f"你是{agent_name}。"

        sys_prompt += "\n\n请用简短的一两句话回应用户，保持你的专业角色特色。"

        llm = get_llm(temperature=get_temperature(agent_name))
        response = llm.invoke([
            SystemMessage(content=sys_prompt),
            HumanMessage(content=text),
        ])
        reply = _extract_text(response.content)
        send_as_agent(agent_name, chat_id, reply or "收到。")
    except Exception as e:
        logger.error("Agent %s chat error: %s", agent_name, e, exc_info=True)
        send_as_agent(agent_name, chat_id, "收到。")
