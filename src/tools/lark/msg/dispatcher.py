"""飞书消息分发器 — 解析消息类型并路由到对应处理器

职责：
  - 解析飞书事件中的消息类型、@mention、命令
  - 路由到 commands / messages / agent_chat / workflow
  - 所有业务逻辑在下游处理器中，此处仅做分发
"""

import re
import json
import time
import uuid
import logging
import threading

from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

from src.tools.lark.msg.messaging import send_text
from src.tools.lark.msg.multi_bot import send_as_agent
from src.tools.lark.commands import (
    ensure_thread_refs,
    handle_read_folder,
    handle_read_doc,
    handle_stop,
    handle_status,
    handle_help,
    handle_archive,
    handle_review_art,
)
from src.tools.lark.msg.msg_handlers import (
    handle_image_message,
    handle_file_message,
    parse_mentions,
    MENTION_NAME_MAP,
)
from src.agents.management.chat import handle_agent_chat, handle_housekeeper
from src.workflow.runner import run_workflow, resume_workflow

logger = logging.getLogger(__name__)

# ── 命令正则 ─────────────────────────────────────────────────────────

_CMD_READ_FOLDER = re.compile(
    r"^[@/]read_folder\s+"
    r"(?:https?://[a-zA-Z0-9.-]*feishu\.cn/drive/folder/)?([a-zA-Z0-9]+)\s*$",
    re.IGNORECASE,
)
_CMD_READ_DOC = re.compile(
    r"^[@/]read_doc\s+"
    r"(?:https?://[a-zA-Z0-9.-]*feishu\.cn/docx/)?([a-zA-Z0-9]+)\s*$",
    re.IGNORECASE,
)
_CMD_STOP = re.compile(r"^[@/]stop\s*$", re.IGNORECASE)
_CMD_STATUS = re.compile(r"^[@/]status\s*$", re.IGNORECASE)
_CMD_HELP = re.compile(r"^[@/]help\s*$", re.IGNORECASE)
_CMD_REVIEW_ART = re.compile(r"^[@/]review_art\s*$", re.IGNORECASE)
_CMD_ARCHIVE = re.compile(r"^[@/]archive\s*([a-zA-Z0-9]*)\s*$", re.IGNORECASE)
_TEXT_AT_AGENT = re.compile(r"^@(\S+)\s*(.*)", re.DOTALL)


def _spawn(target, *args):
    """在守护线程中执行函数。"""
    threading.Thread(target=target, args=args, daemon=True).start()


class Dispatcher:
    """飞书消息分发器，持有共享状态和 graph_app 引用。"""

    # 消息去重：多机器人模式下同一条群消息会被多个 bot 收到
    _MSG_TTL = 60  # 秒

    def __init__(self, graph_app):
        self.graph_app = graph_app
        self.thread_refs: dict[str, dict] = {}
        self.thread_state: dict[str, dict] = {}
        self.art_feedback_images: dict[str, list] = {}
        self._seen_msgs: dict[str, float] = {}
        self._seen_lock = threading.Lock()

    def _on_start_workflow(self, chat_id: str, thread_id: str, text: str):
        run_workflow(self.graph_app, chat_id, thread_id, text,
                     self.thread_refs, self.thread_state)

    def _dedup(self, message_id: str) -> bool:
        """返回 True 表示重复消息，应跳过。"""
        now = time.time()
        with self._seen_lock:
            # 清理过期条目
            expired = [k for k, t in self._seen_msgs.items() if now - t > self._MSG_TTL]
            for k in expired:
                del self._seen_msgs[k]
            if message_id in self._seen_msgs:
                return True
            self._seen_msgs[message_id] = now
            return False

    def handle(self, data: P2ImMessageReceiveV1) -> None:
        """飞书消息事件入口。"""
        try:
            message = data.event.message
            msg_type = message.message_type
            chat_id = message.chat_id
            message_id = message.message_id

            # 多机器人去重
            if self._dedup(message_id):
                return

            thread_id = chat_id or str(uuid.uuid4())
            content = json.loads(message.content) if message.content else {}

            mentioned_agents, is_at_all = parse_mentions(message)

            # ── 图片 ──
            if msg_type == "image":
                _spawn(handle_image_message, chat_id, message_id, content, thread_id,
                       self.thread_refs, self.thread_state, self.art_feedback_images)
                return

            # ── 文件 ──
            if msg_type == "file":
                _spawn(handle_file_message, chat_id, message_id, content, thread_id,
                       self.thread_refs)
                return

            # ── 音视频 ──
            if msg_type in ("audio", "media"):
                send_text(chat_id, f"📎 已收到{msg_type}消息\n\nℹ️ 音视频处理功能即将上线。")
                return

            # ── 非文本 ──
            if msg_type != "text":
                return

            text = content.get("text", "").strip()
            clean_text = re.sub(r"@_user_\d+", "", text).strip()
            if not clean_text and not is_at_all:
                return

            # ── @所有人 ──
            if is_at_all:
                refs = ensure_thread_refs(self.thread_refs, thread_id)
                if clean_text:
                    refs["text"] += ("\n\n" if refs["text"] else "") + f"[全员通知] {clean_text}"
                send_as_agent("housekeeper", chat_id, "收到👌")
                return

            # ── 飞书 @mention ──
            if mentioned_agents:
                _spawn(handle_agent_chat, mentioned_agents[0], chat_id, message_id,
                       clean_text, thread_id, self.thread_refs, self.thread_state,
                       self._on_start_workflow)
                return

            # ── 命令 ──
            if self._dispatch_command(clean_text, chat_id, thread_id, message_id):
                return

            # ── 文本 @agent ──
            at_match = _TEXT_AT_AGENT.match(clean_text)
            if at_match:
                at_name = at_match.group(1).lower().strip()
                at_body = at_match.group(2).strip()
                agent = MENTION_NAME_MAP.get(at_name)
                if agent:
                    _spawn(handle_agent_chat, agent, chat_id, message_id,
                           at_body or "你好", thread_id, self.thread_refs,
                           self.thread_state, self._on_start_workflow)
                    return

            # ── 工作流恢复 ──
            config = {"configurable": {"thread_id": thread_id}}
            try:
                state = self.graph_app.get_state(config)
                if state.next:
                    _spawn(resume_workflow, self.graph_app, chat_id, thread_id,
                           clean_text, self.thread_state)
                    return
            except Exception:
                pass

            # ── 默认：管家 ──
            _spawn(handle_housekeeper, chat_id, message_id, clean_text, thread_id,
                   self.thread_refs, self.thread_state, self._on_start_workflow)

        except Exception as e:
            logger.error("Error handling Feishu message: %s", e, exc_info=True)

    def _dispatch_command(self, text: str, chat_id: str, thread_id: str, message_id: str) -> bool:
        """尝试匹配命令，匹配成功返回 True。"""
        if _CMD_HELP.match(text):
            handle_help(chat_id)
            return True

        if _CMD_STOP.match(text):
            handle_stop(chat_id, thread_id, self.thread_state)
            return True

        if _CMD_STATUS.match(text):
            handle_status(chat_id, thread_id, self.graph_app,
                          self.thread_refs, self.thread_state, self.art_feedback_images)
            return True

        m = _CMD_ARCHIVE.match(text)
        if m:
            _spawn(handle_archive, chat_id, thread_id, m.group(1) or "", self.graph_app)
            return True

        if _CMD_REVIEW_ART.match(text):
            _spawn(handle_review_art, chat_id, thread_id, self.graph_app,
                   self.thread_state, self.art_feedback_images)
            return True

        m = _CMD_READ_FOLDER.match(text)
        if m:
            _spawn(handle_read_folder, chat_id, thread_id, m.group(1), self.thread_refs)
            return True

        m = _CMD_READ_DOC.match(text)
        if m:
            _spawn(handle_read_doc, chat_id, thread_id, m.group(1), self.thread_refs)
            return True

        return False
