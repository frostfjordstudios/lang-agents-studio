"""读取飞书文件夹命令"""

import logging

from src.tools.lark.msg.messaging import send_text
from src.tools.lark.docs.drive import read_all_from_folder

logger = logging.getLogger(__name__)


def ensure_thread_refs(thread_refs: dict, thread_id: str) -> dict:
    if thread_id not in thread_refs:
        thread_refs[thread_id] = {"text": "", "images": []}
    return thread_refs[thread_id]


def handle_read_folder(chat_id, thread_id, folder_token, thread_refs):
    try:
        send_text(chat_id, "正在读取文件夹，请稍候...")
        result = read_all_from_folder(folder_token)
        refs = ensure_thread_refs(thread_refs, thread_id)
        if result["text_content"]:
            refs["text"] += ("\n\n" if refs["text"] else "") + result["text_content"]
        refs["images"].extend(result["image_list"])
        send_text(chat_id,
            f"文件夹读取完成\n\n"
            f"文本: +{len(result['text_content'])} 字符\n"
            f"图片: +{len(result['image_list'])} 张\n\n"
            f"素材已存入参考资料。")
    except Exception as e:
        logger.error("/read_folder %s failed: %s", folder_token, e, exc_info=True)
        send_text(chat_id, f"读取文件夹失败: {e}")
