"""管理组成员定义"""

from src.agents.profile import AgentProfile
from src.agents.temperature import FREESTYLE

TEAM: dict[str, AgentProfile] = {
    "housekeeper": AgentProfile(
        name="housekeeper", display_name="管家", emoji="🏠",
        group="management", level=1, temperature=FREESTYLE,
        prompt_path="agents/management/housekeeper/housekeeper.md",
        description="项目管家，负责用户接待、任务分流、跨组协调",
    ),
}
