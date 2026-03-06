"""Status message templates for workflow updates."""


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def format_status_update(
    project_name: str,
    status: str,
    *,
    node_name: str = "",
    summary: str = "",
) -> str:
    """Build concise and structured status text."""
    lines = [
        f"项目：{project_name or 'default_project'}",
        f"状态：{status}",
    ]
    if node_name:
        lines.append(f"节点：{node_name}")
    if summary:
        lines.append(f"摘要：{_clip(summary, 160)}")
    return "\n".join(lines)


def format_task_received(project_name: str, node_name: str) -> str:
    """Standardized status when an agent receives a task."""
    return format_status_update(project_name, "已接收任务", node_name=node_name)
