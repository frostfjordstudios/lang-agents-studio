"""飞书云文档输出模块 — 零 LLM Token 消耗

将工作流 state 中的产出物直接写入飞书云文档，
按 media_group 产出分组组织，无需任何 LLM 调用。

使用方式:
    from src.tools.lark.docs.docs_writer import export_state_to_docx
    doc_url = export_state_to_docx(state, folder_token)
"""

import json
import logging
from typing import Optional

import lark_oapi as lark
from lark_oapi.api.docx.v1 import (
    CreateDocumentRequest,
    CreateDocumentRequestBody,
    CreateDocumentBlockChildrenRequest,
    CreateDocumentBlockChildrenRequestBody,
)

from ..client import get_client

logger = logging.getLogger(__name__)


# ── 文档块构建辅助 ────────────────────────────────────────────────────

def _heading_block(text: str, level: int = 2) -> dict:
    """构建标题 Block。"""
    heading_key = f"heading{level}"
    return {
        "block_type": level + 1,  # heading1=2, heading2=3, ...
        heading_key: {
            "elements": [{"text_run": {"content": text}}],
        },
    }


def _text_block(text: str) -> dict:
    """构建段落 Block。"""
    return {
        "block_type": 2,
        "text": {
            "elements": [{"text_run": {"content": text}}],
        },
    }


def _divider_block() -> dict:
    """构建分割线 Block。"""
    return {"block_type": 22}


# ── 主导出函数 ────────────────────────────────────────────────────────

def export_state_to_docx(
    state: dict,
    folder_token: Optional[str] = None,
) -> Optional[str]:
    """将工作流 state 导出为飞书云文档。

    Args:
        state: GraphState 字典，包含所有工作流产出
        folder_token: 飞书云盘文件夹 token（可选，不传则创建在根目录）

    Returns:
        文档 URL 或 None（失败时）
    """
    client = get_client()
    project_name = state.get("project_name") or "default_project"
    title = f"{project_name} — 影视提示词产出归档"

    # 1. 创建文档
    create_body = CreateDocumentRequestBody.builder() \
        .title(title) \
        .folder_token(folder_token or "") \
        .build()

    create_req = CreateDocumentRequest.builder() \
        .request_body(create_body) \
        .build()

    create_resp = client.docx.v1.document.create(create_req)
    if not create_resp.success():
        logger.error(
            "创建文档失败: code=%s, msg=%s",
            create_resp.code, create_resp.msg,
        )
        return None

    document_id = create_resp.data.document.document_id
    logger.info("文档已创建: document_id=%s, title=%s", document_id, title)

    # 2. 组装内容块
    blocks = _build_content_blocks(state)

    if not blocks:
        logger.warning("State 中无有效产出，文档为空")
        return f"https://bytedance.larkoffice.com/docx/{document_id}"

    # 3. 批量插入块到文档
    _insert_blocks(client, document_id, blocks)

    doc_url = f"https://bytedance.larkoffice.com/docx/{document_id}"
    logger.info("文档归档完成: %s (%d 个内容块)", doc_url, len(blocks))
    return doc_url


def _build_content_blocks(state: dict) -> list[dict]:
    """根据 state 内容构建文档块列表。"""
    blocks = []

    # ── 剧本 ──
    if state.get("current_script"):
        blocks.append(_heading_block("Phase 1: 剧本", level=1))
        blocks.append(_text_block(state["current_script"][:30000]))
        blocks.append(_divider_block())

    # ── 导演拆解 ──
    if state.get("director_breakdown"):
        blocks.append(_heading_block("Phase 2: 导演拆解", level=1))
        blocks.append(_text_block(state["director_breakdown"][:30000]))
        blocks.append(_divider_block())

    # ── 美术设计 ──
    if state.get("art_design_content"):
        blocks.append(_heading_block("Phase 3a: 美术设计", level=1))
        blocks.append(_text_block(state["art_design_content"][:30000]))

    # ── 声音设计 ──
    if state.get("voice_design_content"):
        blocks.append(_heading_block("Phase 3b: 声音设计", level=1))
        blocks.append(_text_block(state["voice_design_content"][:30000]))
        blocks.append(_divider_block())

    # ── 分镜提示词 ──
    if state.get("final_storyboard"):
        blocks.append(_heading_block("Phase 4: 分镜提示词", level=1))
        blocks.append(_text_block(state["final_storyboard"][:30000]))
        blocks.append(_divider_block())

    # ── 评分报告 ──
    if state.get("final_scoring_report"):
        blocks.append(_heading_block("终审评分报告", level=1))
        blocks.append(_text_block(state["final_scoring_report"][:30000]))

    # ── 审核记录 ──
    review_sections = {
        "director_script_review": "导演剧本审核",
        "showrunner_script_review": "制片剧本审核",
        "director_production_review": "导演生产审核",
        "director_storyboard_review": "导演分镜终审",
    }
    has_reviews = any(state.get(k) for k in review_sections)
    if has_reviews:
        blocks.append(_divider_block())
        blocks.append(_heading_block("附录: 审核记录", level=1))
        for key, label in review_sections.items():
            content = state.get(key, "")
            if content:
                blocks.append(_heading_block(label, level=2))
                blocks.append(_text_block(content[:15000]))

    return blocks


def _insert_blocks(client, document_id: str, blocks: list[dict]) -> None:
    """将内容块批量插入到文档中。"""
    # 飞书 API 每次最多插入 50 个块
    BATCH_SIZE = 50
    for i in range(0, len(blocks), BATCH_SIZE):
        batch = blocks[i:i + BATCH_SIZE]

        body = CreateDocumentBlockChildrenRequestBody.builder() \
            .children(batch) \
            .index(-1) \
            .build()

        req = CreateDocumentBlockChildrenRequest.builder() \
            .document_id(document_id) \
            .block_id(document_id) \
            .request_body(body) \
            .build()

        resp = client.docx.v1.document_block_children.create(req)
        if not resp.success():
            logger.error(
                "插入文档块失败: code=%s, msg=%s, batch=%d-%d",
                resp.code, resp.msg, i, i + len(batch),
            )
