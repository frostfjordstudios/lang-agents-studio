"""Shared helpers for media group nodes."""

import logging
import os
from pathlib import Path

from langchain_core.messages import HumanMessage, ToolMessage

from src.tools.llm import get_llm
from src.agents.media_group.state import GraphState
from src.tools.search import SEARCH_TOOLS

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "projects"

TEST_MODE = os.environ.get("TEST_MODE", "").strip().lower() in ("1", "true", "yes")

_TEST_PROMPTS = {
    "writer": "用一句话写个10字以内的剧本概念。只回一句话。",
    "director_script_review": "回复：✅ 全部通过。评分9/10。不要多说。",
    "showrunner_script_review": "回复：✅ 全部通过。合规无问题。不要多说。",
    "director_breakdown": "用一句话写个10字以内的拆解指令。只回一句话。",
    "art_design": "用一句话写个10字以内的美术风格。只回一句话。",
    "voice_design": "用一句话写个10字以内的声音风格。只回一句话。",
    "director_production_review": "回复：✅ 全部通过。不要多说。",
    "storyboard": "用一句话写个10字以内的分镜。只回一句话。",
    "director_storyboard_review": "回复：✅ 全部通过。七维均8+。不要多说。",
    "scoring": "回复：总分8.5。不要多说。",
    "scoring_summary": "回复：加权总分8.5/10，达标。不要多说。",
}


def extract_text(content) -> str:
    """Extract plain text from model response content."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(item.get("text", ""))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return str(content)


def invoke_with_search(llm, messages):
    """Invoke llm with optional search tool fallback."""
    try:
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
    except Exception as exc:
        logger.warning("Search-enhanced invoke failed, falling back: %s", exc)
        return llm.invoke(messages)


def save_output(project_name: str, episode: int, subdir: str, filename: str, content: str) -> str:
    """Write generated output into projects directory."""
    output_path = OUTPUT_DIR / project_name / "集数" / f"第{episode}集" / subdir
    output_path.mkdir(parents=True, exist_ok=True)
    filepath = output_path / filename
    filepath.write_text(content, encoding="utf-8")
    return str(filepath)


def test_call(node_key: str) -> str:
    """Execute a very short prompt under TEST_MODE to reduce token usage."""
    prompt = _TEST_PROMPTS.get(node_key, "回复：OK。不要多说。")
    llm = get_llm("director")
    response = llm.invoke([HumanMessage(content=prompt)])
    return extract_text(response.content)


def get_project(state: GraphState) -> str:
    """Get project name from state."""
    return state.get("project_name") or "default_project"


def build_multimodal_message(text: str, images: list[str]) -> HumanMessage:
    """Build a multimodal user message with optional images."""
    if not images:
        return HumanMessage(content=text)
    content: list[dict] = [{"type": "text", "text": text}]
    for img_b64 in images:
        content.append({"type": "image_url", "image_url": {"url": img_b64}})
    return HumanMessage(content=content)


def extract_react_final_content(messages) -> str:
    """Get the final textual assistant response from a ReAct transcript."""
    for msg in reversed(messages):
        if hasattr(msg, "content") and isinstance(msg.content, str) and msg.content:
            if not hasattr(msg, "tool_calls") or not msg.tool_calls:
                return msg.content
    return ""
