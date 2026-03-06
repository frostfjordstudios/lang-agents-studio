"""浏览器工具 — 基于 Playwright 的网页浏览与内容抓取

借鉴 Browser MCP Agent 的设计思路，使用 Playwright 实现真实网页浏览，
封装为 LangChain @tool 供 Agent 节点调用。

线程安全：Playwright 是异步 API，通过独立事件循环 + 线程池隔离，
避免与 LangGraph 的同步节点产生事件循环冲突。

使用方式:
    from src.services.ai.browser_mcp import BROWSER_TOOLS, browse_web_page
    # 绑定到 Agent: llm.bind_tools(BROWSER_TOOLS)
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# 专用线程池，运行独立事件循环来执行 Playwright 异步操作
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="playwright")


def _run_async(coro):
    """在独立线程的新事件循环中运行异步协程，避免嵌套循环冲突。"""
    def _target():
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    future = _executor.submit(_target)
    return future.result(timeout=60)


async def _fetch_page_content(url: str, timeout_ms: int = 30000) -> str:
    """异步获取网页纯文本内容。"""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            # 等待主要内容加载
            await page.wait_for_timeout(2000)
            # 提取纯文本
            text = await page.inner_text("body")
            title = await page.title()
            return f"[页面标题] {title}\n\n{text[:15000]}"
        finally:
            await browser.close()


async def _fetch_page_screenshot_description(url: str) -> str:
    """异步获取网页截图并返回 base64（供多模态 LLM 分析）。"""
    import base64
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page(viewport={"width": 1280, "height": 720})
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            screenshot_bytes = await page.screenshot(full_page=False)
            b64 = base64.b64encode(screenshot_bytes).decode()
            title = await page.title()
            return f"[截图] {title}\ndata:image/png;base64,{b64}"
        finally:
            await browser.close()


@tool("browse_web_page")
def browse_web_page(url: str) -> str:
    """浏览指定网页并返回页面的纯文本内容。

    当你需要查阅网页上的信息时使用此工具。传入完整的 URL，
    工具会启动真实浏览器访问页面并提取文本内容。

    Args:
        url: 要访问的完整网页 URL（如 https://example.com）

    Returns:
        页面标题和纯文本内容（最多 15000 字符）
    """
    try:
        logger.info("Browsing: %s", url)
        result = _run_async(_fetch_page_content(url))
        logger.info("Page fetched: %d chars", len(result))
        return result
    except Exception as e:
        logger.error("Browse failed for %s: %s", url, e)
        return f"无法访问该页面: {type(e).__name__}: {str(e)[:200]}"


@tool("screenshot_web_page")
def screenshot_web_page(url: str) -> str:
    """对指定网页进行截图，返回截图的 base64 数据。

    当你需要查看网页的视觉布局或设计风格时使用此工具。

    Args:
        url: 要截图的完整网页 URL

    Returns:
        页面标题和截图的 base64 编码数据
    """
    try:
        logger.info("Screenshotting: %s", url)
        result = _run_async(_fetch_page_screenshot_description(url))
        logger.info("Screenshot captured for: %s", url)
        return result
    except Exception as e:
        logger.error("Screenshot failed for %s: %s", url, e)
        return f"无法截图该页面: {type(e).__name__}: {str(e)[:200]}"


# 导出工具列表，供 Agent 绑定
BROWSER_TOOLS = [browse_web_page, screenshot_web_page]
