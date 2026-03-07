"""帮助命令"""

from src.tools.lark.msg.multi_bot import send_as_agent


def handle_help(chat_id):
    send_as_agent("housekeeper", chat_id, (
        "命令列表\n\n"
        "@help      显示此帮助\n"
        "@stop      停止当前工作流\n"
        "@status    查看状态和素材\n"
        "@review_art  评审效果图\n"
        "@read_folder <token或链接>  读取飞书文件夹\n"
        "@read_doc <文档ID或链接>  读取飞书文档\n"
        "@archive [folder_token]  归档产出到飞书云文档\n"
        "@test      切换到测试模式(最小LLM调用)\n"
        "@work      切换到工作模式(完整能力)\n\n"
        "对话\n"
        "  直接说话 -> 管家接待\n"
        "  发图片/文件自动存入素材\n"
        "  支持 PDF, PPTX, DOCX, XLSX, TXT 等"
    ))
