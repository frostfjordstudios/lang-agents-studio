"""停止工作流命令"""

from src.tools.lark.msg.messaging import send_text


def handle_stop(chat_id, thread_id, thread_state):
    if thread_id in thread_state and thread_state[thread_id]["status"] == "running":
        thread_state[thread_id]["status"] = "stopped"
        send_text(chat_id, "工作流已标记停止\n\n发送新消息可继续对话或启动新任务。")
    else:
        send_text(chat_id, "当前没有正在运行的工作流。")
