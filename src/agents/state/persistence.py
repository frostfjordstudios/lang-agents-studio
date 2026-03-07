"""Agent 状态持久化 I/O — JSON 文件读写"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
PROJECTS_DIR = BASE_DIR / "projects"
_STATE_FILENAME = ".agent-state.json"
_SUMMARY_MAX = 500
_KEY_OUTPUT_MAX = 50000


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def truncate(text: str, max_len: int) -> str:
    if not text:
        return ""
    return text[:max_len] + ("..." if len(text) > max_len else "")


def state_path(project: str) -> Path:
    return PROJECTS_DIR / project / _STATE_FILENAME


def load_state(project: str) -> dict:
    path = state_path(project)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load agent state for %s: %s", project, e)

    return {
        "project": project,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "current_phase": "",
        "sessions": {},
        "agent_latest": {},
    }


def save_state(project: str, state: dict) -> None:
    path = state_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = now_iso()
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
