"""飞书消息分发器 — 管家单点对话 + @Agent 对话 + 命令处理 + 工作流控制

职责：
  - 处理图片/文件素材消息
  - 处理命令和工作流恢复
  - @提及 Agent 时，让该 Agent 以自己的人设回复
  - 所有自由文本默认交给 housekeeper
"""

import re
import json
import time
import uuid
import logging
import threading

from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

from src.tools.lark.msg.messaging import send_text
from src.tools.lark.commands import (
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
)
from src.tools.lark.msg.text_utils import clean_text_content
from src.tools.llm import sanitize_input
from src.agents.management.housekeeper.chat import handle_housekeeper
from src.agents.management.housekeeper.test_mode import is_test_mode, set_test_mode
from src.agents.management.chat import handle_agent_chat
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
_CMD_TEST = re.compile(r"^[@/]test\s*$", re.IGNORECASE)
_CMD_WORK = re.compile(r"^[@/]work\s*$", re.IGNORECASE)


def _spawn(target, *args):
    """在守护线程中执行函数。"""
    threading.Thread(target=target, args=args, daemon=True).start()


class Dispatcher:
    """飞书消息分发器，持有共享状态和 graph_app 引用。"""

    _MSG_TTL = 60

    def __init__(self, graph_app):
        self.graph_app = graph_app
        self.thread_refs: dict[str, dict] = {}
        self.thread_state: dict[str, dict] = {}
        self.art_feedback_images: dict[str, list] = {}
        self._seen_msgs: dict[str, float] = {}
        self._seen_lock = threading.Lock()
        # 管家静默状态：当其他 Agent 被@时，管家暂停响应，直到用户再@管家
        self._housekeeper_silenced: dict[str, bool] = {}  # chat_id -> silenced

    def _on_start_workflow(self, chat_id: str, thread_id: str, text: str):
        run_workflow(self.graph_app, chat_id, thread_id, text,
                     self.thread_refs, self.thread_state)

    def _dedup(self, message_id: str) -> bool:
        """返回 True 表示重复消息，应跳过。"""
        now = time.time()
        with self._seen_lock:
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

            print(f"[RECV] type={msg_type} chat={chat_id} msg_id={message_id}", flush=True)
            logger.info("[RECV] type=%s chat=%s msg_id=%s", msg_type, chat_id, message_id)

            if self._dedup(message_id):
                logger.debug("[DEDUP] skipping %s", message_id)
                return

            thread_id = chat_id or str(uuid.uuid4())
            content = json.loads(message.content) if message.content else {}
            mentioned_agents, is_at_all = parse_mentions(message)

            if msg_type == "image":
                _spawn(handle_image_message, chat_id, message_id, content, thread_id,
                       self.thread_refs, self.thread_state, self.art_feedback_images)
                return

            if msg_type == "file":
                _spawn(handle_file_message, chat_id, message_id, content, thread_id,
                       self.thread_refs)
                return

            if msg_type in ("audio", "media"):
                send_text(chat_id, f"已收到{msg_type}消息\n\n音视频处理功能即将上线。")
                return

            if msg_type != "text":
                return

            text = content.get("text", "").strip()
            clean_text = sanitize_input(clean_text_content(text))
            if not clean_text and not is_at_all:
                return

            if self._dispatch_command(clean_text, chat_id, thread_id, message_id):
                return

            # ── @Agent 路由 ──
            housekeeper_mentioned = "housekeeper" in mentioned_agents
            other_agents = [a for a in mentioned_agents if a != "housekeeper"]

            if other_agents:
                # 有非管家 Agent 被@：让他们回复，管家进入静默
                self._housekeeper_silenced[chat_id] = True
                for agent_name in other_agents:
                    _spawn(handle_agent_chat, agent_name, chat_id, message_id,
                           clean_text, thread_id)
                # 如果同时@了管家，管家也回复并解除静默
                if housekeeper_mentioned:
                    self._housekeeper_silenced[chat_id] = False
                    _spawn(handle_housekeeper, chat_id, message_id, clean_text, thread_id,
                           self.thread_refs, self.thread_state, self._on_start_workflow)
                return

            if housekeeper_mentioned:
                # 只@了管家：解除静默，管家回复
                self._housekeeper_silenced[chat_id] = False
                _spawn(handle_housekeeper, chat_id, message_id, clean_text, thread_id,
                       self.thread_refs, self.thread_state, self._on_start_workflow)
                return

            if is_at_all:
                # @所有人：所有 Agent 回复，管家也回复
                self._housekeeper_silenced[chat_id] = False
                from src.agents.organization import get_all_agents
                for agent in get_all_agents():
                    if agent.name != "housekeeper":
                        _spawn(handle_agent_chat, agent.name, chat_id, message_id,
                               clean_text, thread_id)
                _spawn(handle_housekeeper, chat_id, message_id, clean_text, thread_id,
                       self.thread_refs, self.thread_state, self._on_start_workflow)
                return

            # ── 无@提及：管家静默时不响应 ──
            if self._housekeeper_silenced.get(chat_id, False):
                return

            # 检查是否有待恢复的工作流
            config = {"configurable": {"thread_id": thread_id}}
            try:
                state = self.graph_app.get_state(config)
                if state.next:
                    _spawn(resume_workflow, self.graph_app, chat_id, thread_id,
                           clean_text, self.thread_state)
                    return
            except Exception:
                pass

            # 默认：管家处理
            _spawn(handle_housekeeper, chat_id, message_id, clean_text, thread_id,
                   self.thread_refs, self.thread_state, self._on_start_workflow)

        except Exception as e:
            logger.error("Error handling Feishu message: %s", e, exc_info=True)

    def _dispatch_command(self, text: str, chat_id: str, thread_id: str, message_id: str) -> bool:
        """尝试匹配命令，匹配成功返回 True。"""
        if _CMD_TEST.match(text):
            set_test_mode(True)
            send_text(chat_id, "已切换到 TEST 模式 (最小LLM调用)")
            return True

        if _CMD_WORK.match(text):
            set_test_mode(False)
            send_text(chat_id, "已切换到 WORK 模式 (完整Agent能力)")
            return True

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
