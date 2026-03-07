"""安全的 MD 文件读写"""

import logging

logger = logging.getLogger(__name__)


def safe_read_md(file_path: str) -> str:
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except Exception as e:
        logger.error("safe_read_md failed: %s — %s", file_path, e)
        return f"读取失败: {e}"


def safe_write_md(file_path: str, content: str) -> bool:
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    except Exception as e:
        logger.error("safe_write_md failed: %s — %s", file_path, e)
        return False
