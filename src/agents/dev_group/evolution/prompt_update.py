"""更新 Agent System Prompt"""

import logging
from pathlib import Path
from langchain_core.tools import tool

from src.agents.organization import AGENT_ORG, get_agent
from src.services.prompt.file_io import safe_read_md, safe_write_md
from src.services.prompt.cache import clear_cache
from src.agents.dev_group.evolution.permissions_guard import check_evolve_permission

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "system_prompts"


@tool("update_agent_system_prompt")
def update_agent_system_prompt(caller: str, agent_name: str, new_rules_content: str) -> str:
    """更新指定 Agent 的 System Prompt 文件。"""
    err = check_evolve_permission(caller)
    if err:
        return err

    target_agent = get_agent(agent_name)
    if not target_agent or not target_agent.prompt_path:
        available = [a.name for a in AGENT_ORG.values() if a.prompt_path]
        return f"未知或无 prompt 的 Agent: {agent_name}。可选: {', '.join(available)}"

    if not new_rules_content or not new_rules_content.strip():
        return "内容不能为空，拒绝写入。"

    target = PROMPTS_DIR / target_agent.prompt_path
    if target.exists():
        old_len = len(safe_read_md(str(target)))
        logger.info("Evolution: overwriting %s prompt (old=%d, new=%d)",
                     agent_name, old_len, len(new_rules_content))
    else:
        target.parent.mkdir(parents=True, exist_ok=True)

    ok = safe_write_md(str(target), new_rules_content)
    if not ok:
        return f"写入失败: {target_agent.prompt_path}"

    clear_cache()
    return f"已更新 {agent_name} 的 System Prompt ({len(new_rules_content)} 字符)"
