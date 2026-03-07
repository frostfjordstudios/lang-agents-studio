"""开发组自我进化工具集"""

from src.agents.dev_group.evolution.prompt_update import update_agent_system_prompt
from src.agents.dev_group.evolution.file_read import read_project_file
from src.agents.dev_group.evolution.file_patch import patch_project_file
from src.agents.dev_group.evolution.file_create import create_project_file
from src.agents.dev_group.evolution.structure import list_project_structure

EVOLUTION_TOOLS = [
    update_agent_system_prompt,
    read_project_file,
    patch_project_file,
    create_project_file,
    list_project_structure,
]
