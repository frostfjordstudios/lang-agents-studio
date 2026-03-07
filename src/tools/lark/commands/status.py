"""查看状态命令"""

from src.tools.lark.msg.messaging import send_text


def handle_status(chat_id, thread_id, graph_app, thread_refs, thread_state, art_feedback_images):
    refs = thread_refs.get(thread_id, {"text": "", "images": []})
    state_info = thread_state.get(thread_id, {})
    status = state_info.get("status", "idle")
    last_node = state_info.get("last_node", "-")

    config = {"configurable": {"thread_id": thread_id}}
    paused_at = ""
    try:
        graph_state = graph_app.get_state(config)
        if graph_state.next:
            paused_at = f"\n暂停于: {graph_state.next}"
    except Exception:
        pass

    art_queue = len(art_feedback_images.get(thread_id, []))
    msg = (
        f"当前状态\n\n"
        f"工作流: {status}\n"
        f"最后节点: {last_node}{paused_at}\n"
        f"已加载素材: {len(refs['images'])} 张图片, {len(refs['text'])} 字符文本"
    )
    if art_queue:
        msg += f"\n效果图队列: {art_queue} 张（发送 /review_art 开始评审）"
    send_text(chat_id, msg)
