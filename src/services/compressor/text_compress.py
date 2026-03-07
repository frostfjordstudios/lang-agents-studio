"""SmartCrusher 文本压缩 — 保留首尾 + 异常段 + 结构骨架"""

import re
import logging

logger = logging.getLogger(__name__)

_ANOMALY_KEYWORDS = {
    "不通过", "修改", "问题", "错误", "警告", "建议", "评分", "分数",
    "总分", "结论", "总结", "最终", "最后", "通过",
    "FAIL", "ERROR", "WARN", "reject", "revise",
}


def compress_text(text: str, max_chars: int = 3000, preserve_structure: bool = True) -> str:
    if not text or len(text) <= max_chars:
        return text

    paragraphs = re.split(r'\n\n+', text.strip())
    if len(paragraphs) <= 3:
        return text[:max_chars] + f"\n\n[...已截断，原文 {len(text)} 字符]"

    kept_indices = set()

    # 保留前 2 段 + 最后 1 段
    for i in range(min(2, len(paragraphs))):
        kept_indices.add(i)
    kept_indices.add(len(paragraphs) - 1)

    # 扫描中间段
    for i in range(2, len(paragraphs) - 1):
        para = paragraphs[i]
        if any(kw in para for kw in _ANOMALY_KEYWORDS):
            kept_indices.add(i)
        elif preserve_structure and para.strip().startswith('#'):
            kept_indices.add(i)

    omitted = len(paragraphs) - len(kept_indices)
    result_parts = []
    omit_marker_added = False
    for i, para in enumerate(paragraphs):
        if i in kept_indices:
            result_parts.append(para)
            omit_marker_added = False
        elif not omit_marker_added:
            result_parts.append(f"[...已省略 {omitted} 段冗余内容...]")
            omit_marker_added = True

    result = "\n\n".join(result_parts)
    if len(result) > max_chars:
        result = result[:max_chars] + f"\n\n[...已截断至 {max_chars} 字符]"

    compression_ratio = (1 - len(result) / len(text)) * 100
    if compression_ratio > 5:
        logger.debug("文本压缩: %d -> %d chars (%.0f%%)", len(text), len(result), compression_ratio)

    return result
