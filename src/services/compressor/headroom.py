"""Headroom 库集成（Layer 1 压缩）"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_headroom_available: Optional[bool] = None


def check_headroom() -> bool:
    global _headroom_available
    if _headroom_available is None:
        try:
            import headroom  # noqa: F401
            _headroom_available = True
            logger.info("headroom-ai 库已加载")
        except ImportError:
            _headroom_available = False
    return _headroom_available


def headroom_compress_messages(messages: list[dict], model: str = "gemini-3.1-pro-preview") -> list[dict]:
    try:
        from headroom import compress
        result = compress(messages, model=model)
        logger.info("Headroom: 节省 %d tokens (%.0f%%)", result.tokens_saved, result.compression_ratio * 100)
        return result.messages
    except Exception as e:
        logger.warning("Headroom 失败，回退 Layer 2: %s", e)
        return messages
