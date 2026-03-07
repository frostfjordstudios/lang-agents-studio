"""LLM 意图分类 — 当关键词匹配失败时使用 LLM 判断"""

from langchain_core.messages import SystemMessage, HumanMessage

from src.tools.llm import get_llm
from src.agents.organization import get_temperature


def classify_intent(user_request: str) -> str:
    """用 LLM 分类用户意图，返回 'media' | 'dev' | 'chat'。"""
    llm = get_llm(temperature=get_temperature("housekeeper"))
    messages = [
        SystemMessage(content=(
            "你是项目管家。请判断用户的意图属于哪个类别，只回复一个单词：\n"
            "- media: 与影视创作相关（剧本、拍摄、分镜、美术、声音等）\n"
            "- dev: 与系统优化、架构调整、Agent 进化相关\n"
            "- chat: 日常闲聊、问候、与创作无关的问题\n"
            "只回复 media、dev 或 chat，不要解释。"
        )),
        HumanMessage(content=user_request),
    ]
    response = llm.invoke(messages)
    content = response.content.strip().lower() if isinstance(response.content, str) else "chat"

    if "media" in content:
        return "media"
    elif "dev" in content:
        return "dev"
    return "chat"
