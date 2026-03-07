"""飞书消息处理器 — 图片/文件消息 + @mention 解析

职责：
  - handle_image_message: 下载图片并存入参考素材或效果图队列
  - handle_file_message: 下载文件，按类型提取文本或存图
  - parse_mentions: 解析飞书 @mention（基于 open_id 精确匹配）
"""

import os
import logging
from src.tools.lark.msg.messaging import (
    send_text,
    download_message_image,
    download_message_file,
    image_bytes_to_base64,
)
from src.tools.lark.msg.multi_bot import get_bot_name_by_open_id
from src.tools.lark.commands.read_folder import ensure_thread_refs
from src.tools.lark.docs.doc_extract import extract_text, get_supported_extensions

logger = logging.getLogger(__name__)


def parse_mentions(message) -> tuple[list[str], bool]:
    """解析消息中的 @mention，基于 open_id 精确匹配机器人。

    Returns:
        (被@的 agent name 列表, 是否@了所有人)
    """
    mentioned_agents: list[str] = []
    is_at_all = False

    # 检测 @_all（文本中的 @所有人）
    content = getattr(message, "content", "")
    if content and "@_all" in content:
        is_at_all = True

    mentions = getattr(message, "mentions", None)
    if not mentions:
        return mentioned_agents, is_at_all

    raw_mentions = getattr(mentions, "items", mentions)
    for mention in raw_mentions:
        if isinstance(mention, dict):
            name = mention.get("name", "").strip()
            m_id = mention.get("id", {})
            open_id = m_id.get("open_id", "") if isinstance(m_id, dict) else ""
        else:
            name = getattr(mention, "name", "").strip()
            m_id = getattr(mention, "id", None)
            open_id = getattr(m_id, "open_id", "") if m_id else ""

        if open_id == "all" or name == "所有人":
            is_at_all = True
            continue

        # 通过 open_id 精确查找对应的 agent
        if open_id:
            agent = get_bot_name_by_open_id(open_id)
            if agent:
                mentioned_agents.append(agent)
                continue

        logger.debug("Unknown mention: name=%s open_id=%s", name, open_id)

    return mentioned_agents, is_at_all


def handle_image_message(chat_id: str, message_id: str, content: dict, thread_id: str,
                         thread_refs: dict, thread_state: dict, art_feedback_images: dict):
    """下载图片并存入参考素材或效果图队列。"""
    try:
        image_key = content.get("image_key", "")
        if not image_key:
            return

        image_bytes = download_message_image(message_id, image_key)
        if not image_bytes:
            return

        b64 = image_bytes_to_base64(image_bytes)

        state_info = thread_state.get(thread_id, {})
        if state_info.get("status") == "finished":
            if thread_id not in art_feedback_images:
                art_feedback_images[thread_id] = []
            art_feedback_images[thread_id].append(b64)
            count = len(art_feedback_images[thread_id])
            send_text(
                chat_id,
                f"🎨 效果图已收到 ({count} 张)\n\n"
                f"继续发送更多效果图，或发送 @review_art 开始评审。",
            )
        else:
            refs = ensure_thread_refs(thread_refs, thread_id)
            refs["images"].append(b64)
            send_text(
                chat_id,
                f"📎 图片已收到并存入参考素材\n\n"
                f"🖼️ 当前共 {len(refs['images'])} 张参考图片",
            )
    except Exception as e:
        logger.error("Handle image message failed: %s", e, exc_info=True)
        send_text(chat_id, "❌ 图片处理失败，请重试。")


def handle_file_message(chat_id: str, message_id: str, content: dict, thread_id: str,
                        thread_refs: dict):
    """下载文件并按类型处理。"""
    try:
        file_key = content.get("file_key", "")
        file_name = content.get("file_name", "unknown")
        if not file_key:
            return

        image_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
        ext = os.path.splitext(file_name)[1].lower()

        if ext in image_exts:
            result = download_message_file(message_id, file_key)
            if result:
                file_bytes, _ = result
                refs = ensure_thread_refs(thread_refs, thread_id)
                mime = "image/png" if ext == ".png" else "image/jpeg"
                b64 = image_bytes_to_base64(file_bytes, mime)
                refs["images"].append(b64)
                send_text(
                    chat_id,
                    f"📎 图片文件 {file_name} 已存入参考素材\n"
                    f"🖼️ 当前共 {len(refs['images'])} 张参考图片",
                )
            return

        supported_exts = get_supported_extensions()
        if ext in supported_exts:
            send_text(chat_id, f"📄 正在解析 {file_name}...")
            result = download_message_file(message_id, file_key)
            if not result:
                send_text(chat_id, f"❌ 文件 {file_name} 下载失败")
                return

            file_bytes, _ = result
            text = extract_text(file_bytes, file_name)

            if text and text.strip():
                refs = ensure_thread_refs(thread_refs, thread_id)
                header = f"--- {file_name} ---\n"
                refs["text"] += ("\n\n" if refs["text"] else "") + header + text.strip()

                preview = text.strip()[:200]
                send_text(
                    chat_id,
                    f"✅ {file_name} 解析完成\n\n"
                    f"📄 提取 {len(text)} 字符文本\n"
                    f"📎 已存入参考素材\n\n"
                    f"预览:\n{preview}...",
                )
            else:
                send_text(chat_id, f"⚠️ {file_name} 未能提取到文本内容")
            return

        send_text(
            chat_id,
            f"📎 文件 {file_name} 已收到\n\n"
            f"ℹ️ 暂不支持 {ext} 格式的自动解析。\n"
            f"支持的格式: PDF, PPTX, DOCX, XLSX, TXT, CSV, JSON, MD 等",
        )
    except Exception as e:
        logger.error("Handle file message failed: %s", e, exc_info=True)
        send_text(chat_id, "❌ 文件处理失败，请重试。")
