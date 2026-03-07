"""Final output dispatch when workflow completes."""

import logging
import os

from src.tools.lark.docs.docs_writer import export_state_to_docx
from src.tools.lark.msg.messaging import send_text
from src.tools.lark.msg.multi_bot import send_as_agent

logger = logging.getLogger(__name__)


def _truncate(text: str, limit: int, suffix: str) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + suffix


def send_final_output(graph_app, chat_id: str, config: dict):
    """Extract final outputs from state and send to user."""
    try:
        final_state = graph_app.get_state(config).values or {}
        project_name = final_state.get("project_name", "default_project")

        storyboard = final_state.get("final_storyboard", "")
        if storyboard:
            clipped_storyboard = _truncate(
                storyboard,
                25000,
                "\n\n... (内容过长，已截断。完整版已保存到 projects/ 目录)",
            )
            send_as_agent(
                "housekeeper",
                chat_id,
                f"项目：{project_name}\n状态：最终分镜产出\n\n📐 最终分镜提示词\n\n{clipped_storyboard}",
            )

        report = final_state.get("final_scoring_report", "")
        if report:
            clipped_report = _truncate(report, 10000, "\n\n... (已截断)")
            send_as_agent(
                "housekeeper",
                chat_id,
                f"项目：{project_name}\n状态：评分汇总产出\n\n📊 评分汇总报告\n\n{clipped_report}",
            )

        try:
            from src.tools.lark.docs.permissions import get_department_folder
            folder_token = (get_department_folder("media_group")
                            or os.environ.get("FEISHU_ARCHIVE_FOLDER_TOKEN", "").strip())
            if not folder_token:
                logger.warning("No department folder or FEISHU_ARCHIVE_FOLDER_TOKEN; skip cloud archive")
                send_as_agent(
                    "housekeeper",
                    chat_id,
                    "⚠️ 未配置部门文件夹，已跳过飞书云文档归档。",
                )
            else:
                doc_url = export_state_to_docx(final_state, folder_token)
                if doc_url:
                    send_as_agent(
                        "housekeeper",
                        chat_id,
                        f"项目：{project_name}\n状态：云文档归档完成\n文档：{doc_url}",
                    )
                else:
                    logger.warning("飞书云文档归档返回 None")
                    send_as_agent("housekeeper", chat_id, "⚠️ 云文档归档失败，请检查飞书权限。")
        except Exception as exc:
            logger.error("飞书云文档归档失败: %s", exc)
            send_as_agent("housekeeper", chat_id, "⚠️ 云文档归档失败，请检查飞书权限与文件夹配置。")

        send_as_agent("housekeeper", chat_id, f"项目：{project_name}\n状态：全部完成")
    except Exception as exc:
        logger.error("Failed to send final output: %s", exc)
        send_text(chat_id, "✅ 工作流已完成，但发送结果时出错。产出物已保存到 projects/ 目录。")
