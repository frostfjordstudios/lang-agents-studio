"""开发组成员定义"""

from src.agents.profile import AgentProfile
from src.agents.temperature import FOCUSED

TEAM: dict[str, AgentProfile] = {
    "architect": AgentProfile(
        name="architect", display_name="架构师", emoji="🏗️",
        group="dev_group", level=2, temperature=FOCUSED,
        is_group_leader=True, can_evolve=True,
        description="开发组组长，分析系统瓶颈、指导进化方向、审核代码变更",
    ),
}
