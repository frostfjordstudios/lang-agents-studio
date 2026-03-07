"""Mem0 Memory 单例初始化"""

import os
import logging

logger = logging.getLogger(__name__)

_memory_instance = None


def get_memory():
    global _memory_instance
    if _memory_instance is not None:
        return _memory_instance

    try:
        from mem0 import Memory
    except ImportError:
        logger.error("mem0ai 未安装，请运行: pip install mem0ai>=0.1.29")
        raise

    host = os.environ.get("QDRANT_HOST", "localhost")
    port = int(os.environ.get("QDRANT_PORT", "6333"))
    gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")

    config = {
        "embedder": {
            "provider": "google",
            "config": {"model": "models/text-embedding-004", "api_key": gemini_key},
        },
        "vector_store": {
            "provider": "qdrant",
            "config": {"collection_name": "langgraph_agent_memory", "host": host, "port": port},
        },
    }

    _memory_instance = Memory.from_config(config)
    logger.info("Long-term memory initialized (Qdrant @ %s:%d)", host, port)
    return _memory_instance
