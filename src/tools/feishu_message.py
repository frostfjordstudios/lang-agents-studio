"""飞书 IM 消息收发模块

提供：
  - send_text(chat_id, text)              发送文本消息到群聊
  - reply_text(message_id, text)          回复指定消息
  - send_file(chat_id, file_bytes, name)  上传并发送文件
  - send_image_bytes(chat_id, img_bytes)  上传并发送图片
  - download_message_image(message_id, image_key)   下载消息中的图片
  - download_message_file(message_id, file_key)     下载消息中的文件
"""

import io
import json
import base64
import logging
from typing import Optional

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    CreateMessageResponse,
    ReplyMessageRequest,
    ReplyMessageRequestBody,
    ReplyMessageResponse,
    CreateImageRequest,
    CreateImageRequestBody,
    CreateImageResponse,
    CreateFileRequest,
    CreateFileRequestBody,
    CreateFileResponse,
    GetMessageResourceRequest,
    GetMessageResourceResponse,
)

from .feishu_integration import _get_client

logger = logging.getLogger(__name__)


def _strip_markdown(text: str) -> str:
    """移除 Markdown 格式符号，保留纯文本。"""
    import re
    # **bold** / __bold__ → bold
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    # *italic* / _italic_ → italic
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'(?<!\w)_(.+?)_(?!\w)', r'\1', text)
    # ~~strikethrough~~ → strikethrough
    text = re.sub(r'~~(.+?)~~', r'\1', text)
    # `code` → code
    text = re.sub(r'`(.+?)`', r'\1', text)
    # [text](url) → text
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
    # ### headings → headings
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    return text


# ── 发送文本消息 ──────────────────────────────────────────────────────

def send_text(chat_id: str, text: str) -> Optional[str]:
    """发送文本消息到指定群聊。

    Args:
        chat_id: 群聊 ID（chat_id）
        text: 消息文本（支持 emoji）

    Returns:
        message_id（成功时），None（失败时）
    """
    client = _get_client()

    # Feishu text messages: clean markdown, ensure non-empty, truncate if too long
    if not text or not isinstance(text, str):
        text = "(空消息)"
    text = _strip_markdown(text)
    if len(text) > 30000:
        text = text[:30000] + "\n\n... (内容过长，已截断)"

    content_str = json.dumps({"text": text}, ensure_ascii=False)

    body = CreateMessageRequestBody.builder() \
        .receive_id(chat_id) \
        .msg_type("text") \
        .content(content_str) \
        .build()

    request = CreateMessageRequest.builder() \
        .receive_id_type("chat_id") \
        .request_body(body) \
        .build()

    response: CreateMessageResponse = client.im.v1.message.create(request)

    if not response.success():
        logger.error(
            "发送文本失败: code=%s, msg=%s, ext=%s, chat_id=%s",
            response.code, response.msg, getattr(response, 'ext', ''), chat_id,
        )
        return None

    msg_id = response.data.message_id
    logger.info("文本消息已发送: chat_id=%s, message_id=%s", chat_id, msg_id)
    return msg_id


def reply_text(message_id: str, text: str) -> Optional[str]:
    """回复指定消息。

    Args:
        message_id: 要回复的消息 ID
        text: 回复文本

    Returns:
        新消息的 message_id（成功时），None（失败时）
    """
    client = _get_client()

    if not text or not isinstance(text, str):
        text = "(空消息)"

    body = ReplyMessageRequestBody.builder() \
        .msg_type("text") \
        .content(json.dumps({"text": text}, ensure_ascii=False)) \
        .build()

    request = ReplyMessageRequest.builder() \
        .message_id(message_id) \
        .request_body(body) \
        .build()

    response: ReplyMessageResponse = client.im.v1.message.reply(request)

    if not response.success():
        logger.error(
            "回复消息失败: code=%s, msg=%s, message_id=%s",
            response.code, response.msg, message_id,
        )
        return None

    new_msg_id = response.data.message_id
    logger.info("消息已回复: reply_to=%s, new_id=%s", message_id, new_msg_id)
    return new_msg_id


# ── 上传并发送图片 ────────────────────────────────────────────────────

def send_image_bytes(
    chat_id: str,
    image_bytes: bytes,
    image_type: str = "message",
) -> Optional[str]:
    """上传图片到飞书并发送到群聊。

    Args:
        chat_id: 群聊 ID
        image_bytes: 图片二进制数据
        image_type: 图片类型（message / avatar）

    Returns:
        message_id（成功时），None（失败时）
    """
    client = _get_client()

    # 1. 上传图片获取 image_key
    upload_body = CreateImageRequestBody.builder() \
        .image_type(image_type) \
        .image(io.BytesIO(image_bytes)) \
        .build()

    upload_request = CreateImageRequest.builder() \
        .request_body(upload_body) \
        .build()

    upload_response: CreateImageResponse = client.im.v1.image.create(upload_request)

    if not upload_response.success():
        logger.error(
            "上传图片失败: code=%s, msg=%s",
            upload_response.code, upload_response.msg,
        )
        return None

    image_key = upload_response.data.image_key
    logger.info("图片已上传: image_key=%s", image_key)

    # 2. 发送图片消息
    body = CreateMessageRequestBody.builder() \
        .receive_id(chat_id) \
        .msg_type("image") \
        .content(json.dumps({"image_key": image_key})) \
        .build()

    request = CreateMessageRequest.builder() \
        .receive_id_type("chat_id") \
        .request_body(body) \
        .build()

    response: CreateMessageResponse = client.im.v1.message.create(request)

    if not response.success():
        logger.error(
            "发送图片消息失败: code=%s, msg=%s",
            response.code, response.msg,
        )
        return None

    msg_id = response.data.message_id
    logger.info("图片消息已发送: chat_id=%s, message_id=%s", chat_id, msg_id)
    return msg_id


# ── 上传并发送文件 ────────────────────────────────────────────────────

def send_file(
    chat_id: str,
    file_bytes: bytes,
    file_name: str,
    file_type: str = "stream",
) -> Optional[str]:
    """上传文件到飞书并发送到群聊。

    Args:
        chat_id: 群聊 ID
        file_bytes: 文件二进制数据
        file_name: 文件名
        file_type: 文件类型（opus/mp4/pdf/doc/xls/ppt/stream）

    Returns:
        message_id（成功时），None（失败时）
    """
    client = _get_client()

    # 1. 上传文件获取 file_key
    upload_body = CreateFileRequestBody.builder() \
        .file_type(file_type) \
        .file_name(file_name) \
        .file(io.BytesIO(file_bytes)) \
        .build()

    upload_request = CreateFileRequest.builder() \
        .request_body(upload_body) \
        .build()

    upload_response: CreateFileResponse = client.im.v1.file.create(upload_request)

    if not upload_response.success():
        logger.error(
            "上传文件失败: code=%s, msg=%s, name=%s",
            upload_response.code, upload_response.msg, file_name,
        )
        return None

    file_key = upload_response.data.file_key
    logger.info("文件已上传: file_key=%s, name=%s", file_key, file_name)

    # 2. 发送文件消息
    body = CreateMessageRequestBody.builder() \
        .receive_id(chat_id) \
        .msg_type("file") \
        .content(json.dumps({"file_key": file_key})) \
        .build()

    request = CreateMessageRequest.builder() \
        .receive_id_type("chat_id") \
        .request_body(body) \
        .build()

    response: CreateMessageResponse = client.im.v1.message.create(request)

    if not response.success():
        logger.error(
            "发送文件消息失败: code=%s, msg=%s",
            response.code, response.msg,
        )
        return None

    msg_id = response.data.message_id
    logger.info("文件消息已发送: chat_id=%s, name=%s, message_id=%s", chat_id, file_name, msg_id)
    return msg_id


# ── 下载消息中的资源 ──────────────────────────────────────────────────

def download_message_image(message_id: str, image_key: str) -> Optional[bytes]:
    """下载消息中的图片。

    Args:
        message_id: 消息 ID
        image_key: 图片 key（从消息 content 中解析）

    Returns:
        图片二进制数据，失败返回 None
    """
    client = _get_client()

    request = GetMessageResourceRequest.builder() \
        .message_id(message_id) \
        .file_key(image_key) \
        .type("image") \
        .build()

    response: GetMessageResourceResponse = client.im.v1.message_resource.get(request)

    if not response.success():
        logger.error(
            "下载消息图片失败: code=%s, msg=%s, key=%s",
            response.code, response.msg, image_key,
        )
        return None

    data = response.file.read()
    logger.info("消息图片已下载: message_id=%s, key=%s, %d bytes", message_id, image_key, len(data))
    return data


def download_message_file(message_id: str, file_key: str) -> Optional[tuple[bytes, str]]:
    """下载消息中的文件。

    Args:
        message_id: 消息 ID
        file_key: 文件 key

    Returns:
        (文件二进制数据, 文件名) 元组，失败返回 None
    """
    client = _get_client()

    request = GetMessageResourceRequest.builder() \
        .message_id(message_id) \
        .file_key(file_key) \
        .type("file") \
        .build()

    response: GetMessageResourceResponse = client.im.v1.message_resource.get(request)

    if not response.success():
        logger.error(
            "下载消息文件失败: code=%s, msg=%s, key=%s",
            response.code, response.msg, file_key,
        )
        return None

    data = response.file.read()
    file_name = getattr(response, "file_name", "unknown")
    logger.info("消息文件已下载: message_id=%s, key=%s, name=%s, %d bytes", message_id, file_key, file_name, len(data))
    return (data, file_name)


def image_bytes_to_base64(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """将图片二进制数据转换为 Base64 Data URI。"""
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"
