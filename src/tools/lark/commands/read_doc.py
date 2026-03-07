"""读取飞书文档命令"""

import logging
from src.tools.lark.msg.messaging import send_text
from src.tools.lark.docs.drive import read_feishu_docx
from src.tools.lark.commands.read_folder import ensure_thread_refs

logger = logging.getLogger(__name__)


def handle_read_doc(chat_id, thread_id, document_id, thread_refs):
    try:
        send_text(chat_id, "正在读取文档，请稍候...")
        result = read_feishu_docx(document_id)
        refs = ensure_thread_refs(thread_refs, thread_id)
        if result["text"]:
            refs["text"] += ("\n\n" if refs["text"] else "") + result["text"]
        refs["images"].extend(result["images"])
        send_text(chat_id,
            f"文档读取完成\n\n"
            f"文本: +{len(result['text'])} 字符\n"
            f"图片: +{len(result['images'])} 张\n\n"
            f"素材已存入参考资料。")
    except Exception as e:
        logger.error("/read_doc %s failed: %s", document_id, e, exc_info=True)
        send_text(chat_id, f"读取文档失败: {e}")
