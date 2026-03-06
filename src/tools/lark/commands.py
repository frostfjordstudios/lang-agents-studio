"""命令处理器 — 所有 @command / /command 的处理逻辑

职责：
  - handle_read_folder / handle_read_doc: 飞书文件夹/文档读取
  - handle_stop / handle_status / handle_help: 工作流控制
  - handle_archive: 产出归档到飞书云文档
  - handle_review_art: 美术效果图评审
"""

import os
import logging

from src.core.llm_config import get_llm
from src.tools.lark.msg.messaging import send_text
from src.tools.lark.msg.multi_bot import send_as_agent
from src.tools.lark.docs.drive import read_all_from_folder, read_feishu_docx
from src.tools.lark.docs.doc_extract import extract_text, get_supported_extensions

logger = logging.getLogger(__name__)


def ensure_thread_refs(thread_refs: dict, thread_id: str) -> dict:
    """确保线程参考资料字典已初始化。"""
    if thread_id not in thread_refs:
        thread_refs[thread_id] = {"text": "", "images": []}
    return thread_refs[thread_id]


def handle_read_folder(chat_id: str, thread_id: str, folder_token: str, thread_refs: dict):
    """读取飞书文件夹并缓存素材。"""
    try:
        send_text(chat_id, "📂 正在读取文件夹，请稍候...")
        result = read_all_from_folder(folder_token)
        refs = ensure_thread_refs(thread_refs, thread_id)
        if result["text_content"]:
            refs["text"] += ("\n\n" if refs["text"] else "") + result["text_content"]
        refs["images"].extend(result["image_list"])

        send_text(
            chat_id,
            f"✅ 文件夹读取完成\n\n"
            f"📄 文本: +{len(result['text_content'])} 字符\n"
            f"🖼️ 图片: +{len(result['image_list'])} 张\n\n"
            f"素材已存入参考资料，可以开始创作。",
        )
    except Exception as e:
        logger.error("/read_folder %s failed: %s", folder_token, e, exc_info=True)
        send_text(chat_id, f"❌ 读取文件夹失败: {e}")


def handle_read_doc(chat_id: str, thread_id: str, document_id: str, thread_refs: dict):
    """读取飞书文档并缓存素材。"""
    try:
        send_text(chat_id, "📄 正在读取文档，请稍候...")
        result = read_feishu_docx(document_id)
        refs = ensure_thread_refs(thread_refs, thread_id)
        if result["text"]:
            refs["text"] += ("\n\n" if refs["text"] else "") + result["text"]
        refs["images"].extend(result["images"])

        send_text(
            chat_id,
            f"✅ 文档读取完成\n\n"
            f"📄 文本: +{len(result['text'])} 字符\n"
            f"🖼️ 图片: +{len(result['images'])} 张\n\n"
            f"素材已存入参考资料，可以开始创作。",
        )
    except Exception as e:
        logger.error("/read_doc %s failed: %s", document_id, e, exc_info=True)
        send_text(chat_id, f"❌ 读取文档失败: {e}")


def handle_stop(chat_id: str, thread_id: str, thread_state: dict):
    """停止当前工作流。"""
    if thread_id in thread_state and thread_state[thread_id]["status"] == "running":
        thread_state[thread_id]["status"] = "stopped"
        send_text(chat_id, "⏹️ 工作流已标记停止\n\n发送新消息可继续对话或启动新任务。")
    else:
        send_text(chat_id, "ℹ️ 当前没有正在运行的工作流。")


def handle_status(chat_id: str, thread_id: str, graph_app,
                  thread_refs: dict, thread_state: dict, art_feedback_images: dict):
    """显示当前状态。"""
    refs = thread_refs.get(thread_id, {"text": "", "images": []})
    state_info = thread_state.get(thread_id, {})
    status = state_info.get("status", "idle")
    last_node = state_info.get("last_node", "-")

    config = {"configurable": {"thread_id": thread_id}}
    paused_at = ""
    try:
        graph_state = graph_app.get_state(config)
        if graph_state.next:
            paused_at = f"\n⏸️ 暂停于: {graph_state.next}"
    except Exception:
        pass

    art_queue = len(art_feedback_images.get(thread_id, []))
    msg = (
        f"📊 当前状态\n\n"
        f"🔄 工作流: {status}\n"
        f"📍 最后节点: {last_node}{paused_at}\n"
        f"📎 已加载素材: {len(refs['images'])} 张图片, {len(refs['text'])} 字符文本"
    )
    if art_queue:
        msg += f"\n🎨 效果图队列: {art_queue} 张（发送 /review_art 开始评审）"
    send_text(chat_id, msg)


def handle_help(chat_id: str):
    """显示帮助。"""
    send_as_agent("housekeeper", chat_id, (
        "📖 命令列表\n\n"
        "@help　　　　显示此帮助\n"
        "@stop　　　　停止当前工作流\n"
        "@status　　　查看状态和素材\n"
        "@review_art　评审效果图\n"
        "@read_folder <token或链接>　读取飞书文件夹\n"
        "@read_doc <文档ID或链接>　读取飞书文档\n"
        "@archive [folder_token]　归档产出到飞书云文档\n\n"
        "📣 对话\n"
        "　　直接说话 → 管家接待\n"
        "　　@编剧/导演/美术/声音/分镜/制片 → 对应成员回复\n"
        "　　@所有人 → 管家代收\n\n"
        "💡 发图片/文件自动存入素材\n"
        "💡 支持 PDF, PPTX, DOCX, XLSX, TXT 等"
    ))


def handle_archive(chat_id: str, thread_id: str, folder_token: str, graph_app):
    """归档产出到飞书云文档。"""
    from src.tools.lark.docs.docs_writer import export_state_to_docx

    config = {"configurable": {"thread_id": thread_id}}
    try:
        state = graph_app.get_state(config)
        state_values = state.values or {}
    except Exception:
        send_text(chat_id, "⚠️ 没有找到工作流数据，无法归档。")
        return

    if not state_values.get("current_script"):
        send_text(chat_id, "⚠️ 工作流尚未产出内容，无法归档。")
        return

    send_as_agent("housekeeper", chat_id, "📦 正在归档到飞书云文档...")

    try:
        doc_url = export_state_to_docx(state_values, folder_token=folder_token or None)
        if doc_url:
            send_as_agent("housekeeper", chat_id, f"✅ 归档完成！\n\n📄 文档链接: {doc_url}")
        else:
            send_text(chat_id, "❌ 归档失败，请检查飞书应用权限。")
    except Exception as e:
        logger.error("Archive failed: %s", e, exc_info=True)
        send_text(chat_id, f"❌ 归档出错: {type(e).__name__}: {str(e)[:200]}")


def handle_review_art(chat_id: str, thread_id: str, graph_app,
                      thread_state: dict, art_feedback_images: dict):
    """评审美术效果图。"""
    images = art_feedback_images.get(thread_id, [])
    if not images:
        send_text(chat_id, "⚠️ 还没有收到效果图\n\n请先发送生成的美术效果图，然后再使用 /review_art 命令。")
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
        send_text(chat_id, "⚠️ 当前没有美术设计方案或分镜数据\n\n请先完成一次创作工作流，再提交效果图进行反馈。")
        return

    send_text(chat_id, f"🎨 正在分析 {len(images)} 张效果图...\n\n⏳ 对比美术设计方案并生成反馈")

    try:
        _run_art_feedback(chat_id, thread_id, images, art_design, storyboard, art_feedback_images)
    except Exception as e:
        logger.error("Art feedback error: %s", e, exc_info=True)
        send_text(chat_id, f"❌ 效果图分析出错: {e}")


def _run_art_feedback(chat_id: str, thread_id: str, images: list[str],
                      art_design: str, storyboard: str, art_feedback_images: dict):
    """LLM 分析效果图并反馈。"""
    from src.agents.media_group.nodes import _build_multimodal_message
    from langchain_core.messages import SystemMessage

    prompt = (
        "你是一位资深的美术总监和视觉效果评审专家。\n\n"
        "用户已经基于美术设计方案生成了效果图，请你：\n"
        "1. 逐张分析效果图，评估与美术设计方案的符合程度\n"
        "2. 指出效果图中的亮点和不足\n"
        "3. 基于效果图的实际效果，给出优化后的视频分镜提示词\n"
        "4. 提出下一轮效果图生成的改进建议\n\n"
        "输出格式：\n"
        "📊 效果评估\n（逐张评分和点评）\n\n"
        "✅ 亮点\n（列出做得好的地方）\n\n"
        "⚠️ 需改进\n（列出需要调整的地方）\n\n"
        "📐 优化分镜提示词\n（基于实际效果图优化后的完整分镜提示词）\n\n"
        "💡 下一轮建议\n（改进建议）"
    )

    user_text = f"以下是用户提交的 {len(images)} 张效果图，请与美术设计方案进行对比。\n\n"
    if art_design:
        user_text += f"--- 美术设计方案 ---\n{art_design[:3000]}\n\n"
    if storyboard:
        user_text += f"--- 当前分镜提示词 ---\n{storyboard[:3000]}\n\n"
    user_text += "请分析以下效果图："

    llm = get_llm("art_design")
    messages = [
        SystemMessage(content=prompt),
        _build_multimodal_message(user_text, images),
    ]
    response = llm.invoke(messages)

    raw = response.content
    if isinstance(raw, str):
        reply = raw
    elif isinstance(raw, list):
        reply = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in raw
        )
    else:
        reply = str(raw) if raw else ""

    send_text(chat_id, reply)
    art_feedback_images[thread_id] = []
    logger.info("Art feedback sent (thread=%s, images=%d)", thread_id, len(images))
