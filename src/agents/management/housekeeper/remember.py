"""管家"记住"指令处理"""

from src.services.memory.add import add_memory
from src.tools.lark.msg.multi_bot import send_as_agent

_REMEMBER_PREFIXES = ("记住", "记住：", "记住:", "remember", "remember:")


def handle_remember(chat_id: str, thread_id: str, text: str) -> bool:
    """检测并处理"记住"指令。返回 True 表示已处理。"""
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
                return True
            break
    return False
