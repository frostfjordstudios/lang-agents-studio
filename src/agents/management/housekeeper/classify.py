"""LLM 意图分类 — 当关键词匹配失败时使用 LLM 判断"""

from langchain_core.messages import SystemMessage, HumanMessage

from src.tools.llm import get_llm
from src.agents.organization import get_temperature


def classify_intent(user_request: str) -> str:
    """用 LLM 分类用户意图，返回 'media' | 'dev'。"""
    llm = get_llm(temperature=get_temperature("housekeeper"))
    messages = [
        SystemMessage(content=(
            "你是项目管家。请判断用户的意图属于哪个类别，只回复一个单词：\n"
            "- media: 与影视创作相关（剧本、拍摄、分镜、美术、声音等）\n"
            "- dev: 与系统优化、架构调整、Agent 进化、或其他所有问题相关\n"
            "只回复 media 或 dev，不要解释。"
        )),
        HumanMessage(content=user_request),
    ]
    response = llm.invoke(messages)
    content = response.content.strip().lower() if isinstance(response.content, str) else "dev"

    if "media" in content:
        return "media"
    return "dev"
