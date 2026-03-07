"""GraphState 智能压缩"""

import re
import logging

from src.services.compressor.config import FIELD_LIMITS, PHASE_IRRELEVANT
from src.services.compressor.text_compress import compress_text

logger = logging.getLogger(__name__)


def compress_state_context(state: dict, current_phase: str = "") -> dict:
    slim = dict(state)

    # 阶段裁剪
    if current_phase:
        for field in PHASE_IRRELEVANT.get(current_phase, []):
            if field in slim and slim[field]:
                slim[field] = ""

    # 字段级压缩
    total_saved = 0
    for field, limit in FIELD_LIMITS.items():
        content = slim.get(field, "")
        if not content or not isinstance(content, str) or len(content) <= limit:
            continue
        original_len = len(content)
        slim[field] = compress_text(content, max_chars=limit)
        total_saved += original_len - len(slim[field])

    # Base64 清理
    ref_text = slim.get("reference_text", "")
    if ref_text and "base64" in ref_text.lower():
        slim["reference_text"] = re.sub(
            r'data:[^;]+;base64,[A-Za-z0-9+/=]+',
            '[图片数据已移至多模态通道]', ref_text,
        )

    if total_saved > 500:
        logger.info("上下文压缩: phase=%s, 节省 ~%d chars", current_phase or "?", total_saved)

    return slim
