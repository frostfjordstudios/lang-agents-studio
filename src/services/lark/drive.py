"""飞书云盘、文档、媒体工具模块

提供：
  - list_folder_files(folder_token): 列出文件夹下所有文件
  - download_media_as_base64(file_token, mime_type): 下载媒体文件并转为 Base64
  - read_feishu_docx(document_id): 读取 Docx 文档（支持图文混排）
  - read_all_from_folder(folder_token): 一键读取文件夹下所有 Docx 文本 + 图片
"""

import base64
import logging
from typing import Optional

import lark_oapi as lark
from lark_oapi.api.drive.v1 import (
    ListFileRequest,
    ListFileResponse,
    DownloadMediaRequest,
    DownloadMediaResponse,
)
from lark_oapi.api.docx.v1 import (
    ListDocumentBlockRequest,
    ListDocumentBlockResponse,
)

from .client import get_client

logger = logging.getLogger(__name__)

# 图片文件扩展名集合（用于按文件名判断类型）
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}

# Docx Block 类型常量
_BLOCK_TYPE_IMAGE = 27
_TEXT_BLOCK_TYPES = {2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15}


# ── Drive 文件列表 ───────────────────────────────────────────────────

def list_folder_files(folder_token: str) -> list[dict]:
    """列出飞书云盘指定文件夹下的所有文件。"""
    client = get_client()
    files = []
    page_token: Optional[str] = None

    while True:
        builder = ListFileRequest.builder() \
            .folder_token(folder_token) \
            .page_size(50)

        if page_token:
            builder = builder.page_token(page_token)

        request = builder.build()
        response: ListFileResponse = client.drive.v1.file.list(request)

        if not response.success():
            logger.error(
                "Failed to list folder files: code=%s, msg=%s",
                response.code, response.msg,
            )
            raise RuntimeError(
                f"飞书 Drive API 调用失败: [{response.code}] {response.msg}"
            )

        if response.data and response.data.files:
            for f in response.data.files:
                files.append({
                    "token": f.token,
                    "name": f.name,
                    "type": f.type,
                })

        if response.data and response.data.has_more:
            page_token = response.data.next_page_token
        else:
            break

    logger.info("Listed %d files from folder %s", len(files), folder_token)
    return files


# ── 媒体下载 ─────────────────────────────────────────────────────────

def download_media_as_base64(
    file_token: str,
    mime_type: str = "image/jpeg",
) -> str:
    """下载飞书云盘媒体文件并转换为 Base64 Data URI。"""
    client = get_client()

    request = DownloadMediaRequest.builder() \
        .file_token(file_token) \
        .build()

    response: DownloadMediaResponse = client.drive.v1.media.download(request)

    if not response.success():
        logger.error(
            "Failed to download media: code=%s, msg=%s, token=%s",
            response.code, response.msg, file_token,
        )
        raise RuntimeError(
            f"飞书 Media 下载失败: [{response.code}] {response.msg}"
        )

    raw_bytes = response.file.read()
    encoded = base64.b64encode(raw_bytes).decode("utf-8")

    logger.info(
        "Downloaded media %s (%d bytes, %s)",
        file_token, len(raw_bytes), mime_type,
    )
    return f"data:{mime_type};base64,{encoded}"


# ── Docx 文档读取 ────────────────────────────────────────────────────

def _extract_text_from_block(block) -> str:
    """从文本类 Block 中提取纯文本内容。"""
    text_obj = None
    for attr in ("text", "heading1", "heading2", "heading3", "heading4",
                 "heading5", "heading6", "heading7", "heading8", "heading9",
                 "bullet", "ordered", "code", "quote"):
        text_obj = getattr(block, attr, None)
        if text_obj is not None:
            break

    if text_obj is None or not hasattr(text_obj, "elements"):
        return ""

    parts = []
    for element in (text_obj.elements or []):
        if hasattr(element, "text_run") and element.text_run:
            parts.append(element.text_run.content or "")
    return "".join(parts)


def read_feishu_docx(document_id: str) -> dict:
    """读取飞书 Docx 文档，返回结构化的图文混排内容。"""
    client = get_client()
    all_blocks = []
    page_token: Optional[str] = None

    while True:
        builder = ListDocumentBlockRequest.builder() \
            .document_id(document_id) \
            .page_size(500) \
            .document_revision_id(-1)

        if page_token:
            builder = builder.page_token(page_token)

        request = builder.build()
        response: ListDocumentBlockResponse = client.docx.v1.document_block.list(request)

        if not response.success():
            logger.error(
                "Failed to list document blocks: code=%s, msg=%s",
                response.code, response.msg,
            )
            raise RuntimeError(
                f"飞书 Docx API 调用失败: [{response.code}] {response.msg}"
            )

        if response.data and response.data.items:
            all_blocks.extend(response.data.items)

        if response.data and response.data.has_more:
            page_token = response.data.page_token
        else:
            break

    text_parts = []
    images = []

    for block in all_blocks:
        block_type = block.block_type

        if block_type in _TEXT_BLOCK_TYPES:
            text = _extract_text_from_block(block)
            if text:
                text_parts.append(text)

        elif block_type == _BLOCK_TYPE_IMAGE and block.image:
            image_token = block.image.token
            if image_token:
                try:
                    b64 = download_media_as_base64(image_token)
                    images.append(b64)
                except Exception as e:
                    logger.warning(
                        "Failed to download image %s from docx: %s",
                        image_token, e,
                    )

    logger.info(
        "Read docx %s: %d text blocks, %d images",
        document_id, len(text_parts), len(images),
    )

    return {
        "text": "\n".join(text_parts),
        "images": images,
    }


# ── 一键读取文件夹 ──────────────────────────────────────────────────

def _guess_mime_type(filename: str) -> str:
    """根据文件名推断 MIME 类型。"""
    name_lower = filename.lower()
    if name_lower.endswith(".png"):
        return "image/png"
    if name_lower.endswith(".gif"):
        return "image/gif"
    if name_lower.endswith(".webp"):
        return "image/webp"
    if name_lower.endswith(".bmp"):
        return "image/bmp"
    return "image/jpeg"


def read_all_from_folder(folder_token: str) -> dict:
    """一键读取飞书文件夹下的所有 Docx 文本和图片资源。"""
    files = list_folder_files(folder_token)

    all_texts = []
    all_images = []

    for file_info in files:
        token = file_info["token"]
        name = file_info["name"]
        file_type = file_info["type"]

        if file_type == "docx":
            try:
                result = read_feishu_docx(token)
                if result["text"]:
                    all_texts.append(f"--- {name} ---\n{result['text']}")
                all_images.extend(result["images"])
                logger.info("Processed docx: %s", name)
            except Exception as e:
                logger.warning("Failed to read docx %s: %s", name, e)

        elif file_type == "file" and any(name.lower().endswith(ext) for ext in _IMAGE_EXTENSIONS):
            try:
                mime = _guess_mime_type(name)
                b64 = download_media_as_base64(token, mime_type=mime)
                all_images.append(b64)
                logger.info("Downloaded image file: %s", name)
            except Exception as e:
                logger.warning("Failed to download image %s: %s", name, e)

        else:
            logger.info("Skipped unsupported file: %s (type=%s)", name, file_type)

    logger.info(
        "read_all_from_folder complete: %d text sections, %d images",
        len(all_texts), len(all_images),
    )

    return {
        "text_content": "\n\n".join(all_texts),
        "image_list": all_images,
    }
