"""LangChain 消息级压缩"""

from src.services.compressor.headroom import check_headroom, headroom_compress_messages
from src.services.compressor.text_compress import compress_text


def compress_messages(messages: list, model: str = "gemini-3.1-pro-preview") -> list:
    if check_headroom():
        from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
        hr_msgs = []
        for msg in messages:
            role = "user"
            if hasattr(msg, "type"):
                role = {"system": "system", "human": "user", "ai": "assistant"}.get(msg.type, "user")
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            hr_msgs.append({"role": role, "content": content})

        compressed = headroom_compress_messages(hr_msgs, model=model)
        _ROLE_MAP = {"system": SystemMessage, "user": HumanMessage, "assistant": AIMessage}
        return [_ROLE_MAP.get(m["role"], HumanMessage)(content=m["content"]) for m in compressed]

    # Layer 2: 内置文本压缩
    from langchain_core.messages import SystemMessage
    result = []
    for msg in messages:
        if isinstance(msg.content, str) and len(msg.content) > 6000 and not isinstance(msg, SystemMessage):
            result.append(type(msg)(content=compress_text(msg.content, max_chars=6000)))
        else:
            result.append(msg)
    return result
