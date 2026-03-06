"""Small utility helpers for runtime modules."""


def normalize_output_text(value) -> str:
    """Normalize model output content to plain string."""
    if isinstance(value, list):
        return "\n".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in value
        )
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return str(value)
