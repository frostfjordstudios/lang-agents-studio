"""美术效果图评审命令"""

import logging
from langchain_core.messages import SystemMessage

from src.tools.llm import get_llm
from src.agents.organization import get_temperature
from src.tools.lark.msg.messaging import send_text

logger = logging.getLogger(__name__)


def handle_review_art(chat_id, thread_id, graph_app, thread_state, art_feedback_images):
    images = art_feedback_images.get(thread_id, [])
    if not images:
        send_text(chat_id, "还没有收到效果图\n\n请先发送效果图，然后再使用 /review_art 命令。")
        return

    config = {"configurable": {"thread_id": thread_id}}
    art_design = ""
    storyboard = ""
    try:
        graph_state = graph_app.get_state(config)
        state_values = graph_state.values or {}
        art_design = state_values.get("art_design_content", "")
        storyboard = state_values.get("final_storyboard", "")
    except Exception:
        pass

    if not art_design and not storyboard:
        send_text(chat_id, "当前没有美术设计方案或分镜数据\n\n请先完成一次创作工作流。")
        return

    send_text(chat_id, f"正在分析 {len(images)} 张效果图...\n\n对比美术设计方案并生成反馈")
    try:
        _run_art_feedback(chat_id, thread_id, images, art_design, storyboard, art_feedback_images)
    except Exception as e:
        logger.error("Art feedback error: %s", e, exc_info=True)
        send_text(chat_id, f"效果图分析出错: {e}")


def _run_art_feedback(chat_id, thread_id, images, art_design, storyboard, art_feedback_images):
    from src.agents.media_group.nodes import _build_multimodal_message

    prompt = (
        "你是一位资深的美术总监和视觉效果评审专家。\n\n"
        "请：\n1. 逐张分析效果图\n2. 指出亮点和不足\n"
        "3. 给出优化后的分镜提示词\n4. 提出改进建议"
    )

    user_text = f"以下是 {len(images)} 张效果图。\n\n"
    if art_design:
        user_text += f"--- 美术设计方案 ---\n{art_design[:3000]}\n\n"
    if storyboard:
        user_text += f"--- 当前分镜提示词 ---\n{storyboard[:3000]}\n\n"
    user_text += "请分析以下效果图："

    llm = get_llm(temperature=get_temperature("art_design"))
    messages = [SystemMessage(content=prompt), _build_multimodal_message(user_text, images)]
    response = llm.invoke(messages)

    raw = response.content
    if isinstance(raw, str):
        reply = raw
    elif isinstance(raw, list):
        reply = "\n".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in raw)
    else:
        reply = str(raw) if raw else ""

    send_text(chat_id, reply)
    art_feedback_images[thread_id] = []
