"""Tavily 搜索工具 — 为 Agent 提供联网查阅资料的能力"""

from langchain_tavily import TavilySearch


def get_search_tool(max_results: int = 2) -> TavilySearch:
    return TavilySearch(max_results=max_results)


SEARCH_TOOLS = [get_search_tool()]
