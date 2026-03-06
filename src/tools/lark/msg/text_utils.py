"""Pure text helpers for Feishu message handling."""

import re

_AT_TAG = re.compile(r"<at\b[^>]*>.*?</at>", re.IGNORECASE | re.DOTALL)
_AT_USER_PLACEHOLDER = re.compile(r"@_user_\d+")
_WHITESPACE = re.compile(r"\s+")


def clean_text_content(text: str) -> str:
    """Strip Feishu mention markup and normalize whitespace."""
    raw = text or ""
    raw = _AT_TAG.sub(" ", raw)
    raw = _AT_USER_PLACEHOLDER.sub(" ", raw)
    raw = raw.replace("\u200b", " ")
    raw = _WHITESPACE.sub(" ", raw).strip()
    return raw


def build_mention_echo(text: str) -> str:
    """Build deterministic echo reply for mention tests."""
    cleaned = clean_text_content(text)
    return f"收到你发送的消息：{cleaned}" if cleaned else "收到你的@消息。"
