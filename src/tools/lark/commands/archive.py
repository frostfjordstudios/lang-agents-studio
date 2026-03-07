"""归档产出到飞书云文档命令"""

import os
import logging

from src.tools.lark.msg.messaging import send_text
from src.tools.lark.msg.multi_bot import send_as_agent

logger = logging.getLogger(__name__)


def handle_archive(chat_id, thread_id, folder_token, graph_app):
    from src.tools.lark.docs.docs_writer import export_state_to_docx

    config = {"configurable": {"thread_id": thread_id}}
    try:
        state = graph_app.get_state(config)
        state_values = state.values or {}
    except Exception:
        send_text(chat_id, "没有找到工作流数据，无法归档。")
        return

    if not state_values.get("current_script"):
        send_text(chat_id, "工作流尚未产出内容，无法归档。")
        return

    resolved = (folder_token or os.environ.get("FEISHU_ARCHIVE_FOLDER_TOKEN", "")).strip()
    if not resolved:
        send_as_agent("housekeeper", chat_id, "未配置归档文件夹 token，请设置 FEISHU_ARCHIVE_FOLDER_TOKEN。")
        return

    send_as_agent("housekeeper", chat_id, "正在归档到飞书云文档...")
    try:
        doc_url = export_state_to_docx(state_values, folder_token=resolved)
        if doc_url:
            send_as_agent("housekeeper", chat_id, f"归档完成！\n\n文档链接: {doc_url}")
        else:
            send_text(chat_id, "归档失败，请检查飞书应用权限。")
    except Exception as e:
        logger.error("Archive failed: %s", e, exc_info=True)
        send_text(chat_id, f"归档出错: {type(e).__name__}: {str(e)[:200]}")
