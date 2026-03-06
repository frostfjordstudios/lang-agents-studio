"""上下文压缩优化器 — 解决多 Agent 协作 Token 爆炸问题

双层架构:
  Layer 1: 尝试使用 headroom-ai 库（SmartCrusher + ContentRouter）
  Layer 2: 自研轻量压缩器（无外部依赖回退方案）

核心策略（源自 Headroom SmartCrusher 思想）:
  1. 保留首尾 — 保留最早和最新的信息，中间重复内容用摘要替代
  2. 异常检测 — 自动识别并保留关键异常（错误、修改意见、评分低于阈值）
  3. 查询相关 — 根据当前阶段只保留相关上下文，丢弃无关历史
  4. 长度截断 — 对超长文本按重要度截断，保留结构完整性

使用方式:
    from src.core.context_optimizer import compress_state_context, compress_text
    slim_state = compress_state_context(state)
    slim_text = compress_text(long_review, max_chars=3000)
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ── 压缩参数 ─────────────────────────────────────────────────────────

# 各字段最大保留字符数（按重要度分级）
_FIELD_LIMITS: dict[str, int] = {
    # Tier 1: 核心产出（保留较多）
    "current_script":           8000,
    "director_breakdown":       6000,
    "final_storyboard":         8000,
    "art_design_content":       5000,
    "voice_design_content":     5000,

    # Tier 2: 审核记录（大幅压缩）
    "director_script_review":   2000,
    "showrunner_script_review": 2000,
    "director_production_review": 2000,
    "director_storyboard_review": 2000,

    # Tier 3: 评分（保留摘要即可）
    "scoring_director":         1500,
    "scoring_writer":           1500,
    "scoring_art":              1500,
    "scoring_voice":            1500,
    "scoring_storyboard":       1500,
    "scoring_showrunner":       1500,
    "final_scoring_report":     3000,

    # Tier 4: 用户反馈（保留全文，通常较短）
    "user_script_feedback":     2000,
    "user_production_feedback": 2000,
    "user_request":             3000,
    "reference_text":           5000,
}

# 当前阶段不需要的字段（按阶段裁剪，彻底清空以省 Token）
_PHASE_IRRELEVANT: dict[str, list[str]] = {
    "writer": [
        "scoring_director", "scoring_writer", "scoring_art",
        "scoring_voice", "scoring_storyboard", "scoring_showrunner",
        "final_scoring_report", "art_feedback_images", "art_feedback_result",
        "refined_storyboard",
    ],
    "director_script_review": [
        "scoring_director", "scoring_writer", "scoring_art",
        "scoring_voice", "scoring_storyboard", "scoring_showrunner",
        "final_scoring_report",
    ],
    "showrunner_script_review": [
        "scoring_director", "scoring_writer", "scoring_art",
        "scoring_voice", "scoring_storyboard", "scoring_showrunner",
        "final_scoring_report",
    ],
    "director_breakdown": [
        "director_script_review", "showrunner_script_review",
        "scoring_director", "scoring_writer", "scoring_art",
        "scoring_voice", "scoring_storyboard", "scoring_showrunner",
        "final_scoring_report",
    ],
    "art_design": [
        "showrunner_script_review",
        "scoring_director", "scoring_writer", "scoring_art",
        "scoring_voice", "scoring_storyboard", "scoring_showrunner",
        "final_scoring_report",
    ],
    "voice_design": [
        "showrunner_script_review",
        "scoring_director", "scoring_writer", "scoring_art",
        "scoring_voice", "scoring_storyboard", "scoring_showrunner",
        "final_scoring_report",
    ],
    "storyboard": [
        "director_script_review", "showrunner_script_review",
        "scoring_director", "scoring_writer", "scoring_art",
        "scoring_voice", "scoring_storyboard", "scoring_showrunner",
        "final_scoring_report",
    ],
}


# ── Headroom 库集成（Layer 1）───────────────────────────────────────

_headroom_available: Optional[bool] = None


def _check_headroom() -> bool:
    """检查 headroom-ai 是否可用。"""
    global _headroom_available
    if _headroom_available is None:
        try:
            import headroom  # noqa: F401
            _headroom_available = True
            logger.info("headroom-ai 库已加载，启用 Layer 1 压缩")
        except ImportError:
            _headroom_available = False
            logger.info("headroom-ai 未安装，使用内置 Layer 2 压缩器")
    return _headroom_available


def _headroom_compress_messages(messages: list[dict], model: str = "gemini-3.1-pro-preview") -> list[dict]:
    """使用 headroom-ai 库压缩 LLM 消息列表。

    Args:
        messages: [{"role": "system"|"user"|"assistant", "content": "..."}]
        model: 目标模型名称（用于 token 计算）

    Returns:
        压缩后的消息列表
    """
    try:
        from headroom import compress
        result = compress(messages, model=model)
        logger.info(
            "Headroom 压缩: 节省 %d tokens (压缩率 %.0f%%)",
            result.tokens_saved,
            result.compression_ratio * 100,
        )
        return result.messages
    except Exception as e:
        logger.warning("Headroom 压缩失败，回退到 Layer 2: %s", e)
        return messages


# ── 内置轻量压缩器（Layer 2）────────────────────────────────────────

def compress_text(text: str, max_chars: int = 3000, preserve_structure: bool = True) -> str:
    """智能文本压缩 — SmartCrusher 轻量版。

    策略:
      1. 短文本直接返回（不浪费 CPU）
      2. 按段落分割，保留首尾段 + 含关键词的段落
      3. 中间被省略的部分用 "[...已省略 N 段...]" 替代

    Args:
        text: 原始文本
        max_chars: 最大保留字符数
        preserve_structure: 是否保留 Markdown 标题结构

    Returns:
        压缩后的文本
    """
    if not text or len(text) <= max_chars:
        return text

    # 按段落分割（双换行或 Markdown 标题）
    paragraphs = re.split(r'\n\n+', text.strip())
    if len(paragraphs) <= 3:
        # 段落太少，直接硬截断
        return text[:max_chars] + f"\n\n[...已截断，原文 {len(text)} 字符]"

    # SmartCrusher 核心策略：保留首尾 + 异常段
    kept = []
    kept_indices = set()

    # 1. 保留前 2 段（上下文）
    for i in range(min(2, len(paragraphs))):
        kept.append(paragraphs[i])
        kept_indices.add(i)

    # 2. 保留最后 1 段（最新结论）
    kept_indices.add(len(paragraphs) - 1)

    # 3. 扫描中间段，保留含关键信号的段落
    _ANOMALY_KEYWORDS = {
        "不通过", "修改", "问题", "错误", "警告", "建议", "评分", "分数",
        "❌", "⚠️", "总分", "结论", "总结", "最终", "最后", "通过",
        "FAIL", "ERROR", "WARN", "reject", "revise",
    }

    for i in range(2, len(paragraphs) - 1):
        if i in kept_indices:
            continue
        para = paragraphs[i]
        # 异常检测：含关键词的段落保留
        if any(kw in para for kw in _ANOMALY_KEYWORDS):
            kept.append(para)
            kept_indices.add(i)
        # Markdown 标题保留（结构骨架）
        elif preserve_structure and para.strip().startswith('#'):
            kept.append(para)
            kept_indices.add(i)

    # 添加最后一段
    if len(paragraphs) - 1 not in {i for i, _ in enumerate(kept)}:
        kept.append(paragraphs[-1])

    # 计算被省略的段落数
    omitted = len(paragraphs) - len(kept_indices)

    # 组装结果
    result_parts = []
    for i, para in enumerate(paragraphs):
        if i in kept_indices:
            result_parts.append(para)
        elif (i > 0 and i - 1 in kept_indices) or i == 2:
            # 在首次跳过位置插入省略标记
            result_parts.append(f"[...已省略 {omitted} 段冗余内容...]")

    result = "\n\n".join(result_parts)

    # 如果仍然超长，硬截断
    if len(result) > max_chars:
        result = result[:max_chars] + f"\n\n[...已截断至 {max_chars} 字符]"

    compression_ratio = (1 - len(result) / len(text)) * 100
    if compression_ratio > 5:
        logger.debug("文本压缩: %d -> %d chars (%.0f%%)", len(text), len(result), compression_ratio)

    return result


def compress_state_context(state: dict, current_phase: str = "") -> dict:
    """对 GraphState 进行智能压缩，返回瘦身后的 State 副本。

    Args:
        state: 原始 GraphState 字典
        current_phase: 当前节点名称（用于阶段裁剪）

    Returns:
        压缩后的 State 副本（不修改原始 state）
    """
    slim = dict(state)

    # ── Step 1: 阶段裁剪 — 清空当前阶段不需要的字段 ──
    if current_phase:
        irrelevant = _PHASE_IRRELEVANT.get(current_phase, [])
        for field in irrelevant:
            if field in slim and slim[field]:
                original_len = len(str(slim[field]))
                slim[field] = ""
                if original_len > 100:
                    logger.debug(
                        "阶段裁剪: %s.%s 清空 (%d chars)",
                        current_phase, field, original_len,
                    )

    # ── Step 2: 字段级压缩 — 对超长文本执行 SmartCrusher ──
    total_saved = 0
    for field, limit in _FIELD_LIMITS.items():
        content = slim.get(field, "")
        if not content or not isinstance(content, str):
            continue
        if len(content) > limit:
            original_len = len(content)
            slim[field] = compress_text(content, max_chars=limit)
            saved = original_len - len(slim[field])
            total_saved += saved

    # ── Step 3: 图片引用压缩 — Base64 数据不传入 LLM 文本 ──
    # （图片走多模态通道，文本上下文中只保留计数摘要）
    ref_images = slim.get("reference_images", [])
    if ref_images and len(ref_images) > 0:
        # 不修改 reference_images 本身（多模态消息需要），
        # 但确保 reference_text 中不重复包含 Base64
        ref_text = slim.get("reference_text", "")
        if ref_text and "base64" in ref_text.lower():
            # 移除可能被误插入文本中的 Base64 数据
            slim["reference_text"] = re.sub(
                r'data:[^;]+;base64,[A-Za-z0-9+/=]+',
                '[图片数据已移至多模态通道]',
                ref_text,
            )

    if total_saved > 500:
        logger.info(
            "上下文压缩完成 (phase=%s): 节省 ~%d 字符 (~%d tokens)",
            current_phase or "unknown",
            total_saved,
            total_saved // 4,
        )

    return slim


# ── 消息级压缩（配合 Headroom Layer 1）──────────────────────────────

def compress_messages(messages: list, model: str = "gemini-3.1-pro-preview") -> list:
    """压缩 LangChain 消息列表。

    如果 headroom-ai 可用，使用其 compress() 函数；
    否则对超长消息内容执行内置文本压缩。

    Args:
        messages: LangChain Message 对象列表
        model: 目标模型名称

    Returns:
        压缩后的消息列表（可能是原始对象或新对象）
    """
    if _check_headroom():
        # 转换为 headroom 格式
        hr_messages = []
        for msg in messages:
            role = "user"
            if hasattr(msg, "type"):
                role = {"system": "system", "human": "user", "ai": "assistant"}.get(msg.type, "user")
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            hr_messages.append({"role": role, "content": content})

        compressed = _headroom_compress_messages(hr_messages, model=model)

        # 转换回 LangChain 格式
        from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
        _ROLE_MAP = {"system": SystemMessage, "user": HumanMessage, "assistant": AIMessage}
        result = []
        for m in compressed:
            cls = _ROLE_MAP.get(m["role"], HumanMessage)
            result.append(cls(content=m["content"]))
        return result

    # Layer 2: 对超长消息内容执行文本压缩
    from langchain_core.messages import SystemMessage, HumanMessage
    result = []
    for msg in messages:
        if isinstance(msg.content, str) and len(msg.content) > 6000:
            # System Prompt 不压缩（含完整角色定义和技能规范）
            if isinstance(msg, SystemMessage):
                result.append(msg)
            else:
                compressed_content = compress_text(msg.content, max_chars=6000)
                result.append(type(msg)(content=compressed_content))
        else:
            result.append(msg)

    return result
