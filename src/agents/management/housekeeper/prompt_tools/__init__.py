"""管家 Prompt 编辑工具集"""

from src.agents.management.housekeeper.prompt_tools.list_files import list_prompt_files
from src.agents.management.housekeeper.prompt_tools.read_file import read_prompt_file
from src.agents.management.housekeeper.prompt_tools.write_file import write_prompt_file
from src.agents.management.housekeeper.prompt_tools.edit_file import edit_prompt_file

PROMPT_EDITOR_TOOLS = [list_prompt_files, read_prompt_file, write_prompt_file, edit_prompt_file]
