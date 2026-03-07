"""TEST_MODE 广播逻辑 — 所有 Agent 发送短状态"""

import os

from src.tools.lark.msg.multi_bot import send_as_agent

TEST_MODE = os.environ.get("TEST_MODE", "").strip().lower() in ("1", "true", "yes")
TEST_MODE_ALL_AGENTS_SPEAK = os.environ.get("TEST_MODE_ALL_AGENTS_SPEAK", "1").strip().lower() in ("1", "true", "yes")

_TEST_AGENT_LINES = {
    "showrunner": "状态：统筹中",
    "writer": "状态：可开始写稿",
    "director": "状态：可开始审稿",
    "art_design": "状态：可开始美术方案",
    "voice_design": "状态：可开始声音方案",
    "storyboard": "状态：可开始分镜提示词",
}


def broadcast_test_updates(chat_id: str, thread_id: str):
    project = f"test_{thread_id[-6:]}" if thread_id else "test_session"
    for agent, line in _TEST_AGENT_LINES.items():
        send_as_agent(agent, chat_id, f"项目：{project}\n{line}")
