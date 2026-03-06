"""Tavily 搜索工具 - 为 Agent 提供联网查阅资料的能力

使用 Tavily Search API，需要在 .env 中配置 TAVILY_API_KEY。
默认返回最多 2 条精准结果，控制 token 消耗。
"""

from langchain_community.tools.tavily_search import TavilySearchResults


def get_search_tool(max_results: int = 2) -> TavilySearchResults:
    """返回配置好的 Tavily 搜索工具实例。"""
    return TavilySearchResults(max_results=max_results)


SEARCH_TOOLS = [get_search_tool()]
