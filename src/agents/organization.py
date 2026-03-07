"""Agent 组织架构 — 聚合所有组的成员定义

每个组在自己的文件夹内通过 team.py 定义成员。
本文件仅声明有哪些组，并提供全局查询接口。
"""

from typing import Optional

from src.agents.profile import AgentProfile
from src.agents.temperature import BALANCED

from src.agents.management.team import TEAM as _MANAGEMENT
from src.agents.media_group.team import TEAM as _MEDIA_GROUP
from src.agents.dev_group.team import TEAM as _DEV_GROUP

# 组注册表：组名 -> 该组的 TEAM 字典
GROUPS: dict[str, dict[str, AgentProfile]] = {
    "management": _MANAGEMENT,
    "media_group": _MEDIA_GROUP,
    "dev_group": _DEV_GROUP,
}

# 全局扁平索引（自动聚合）
AGENT_ORG: dict[str, AgentProfile] = {}
for _team in GROUPS.values():
    AGENT_ORG.update(_team)


def get_agent(name: str) -> Optional[AgentProfile]:
    return AGENT_ORG.get(name)


def get_group_members(group: str) -> list[AgentProfile]:
    team = GROUPS.get(group, {})
    members = list(team.values())
    members.sort(key=lambda a: (a.level, a.name))
    return members


def get_group_leader(group: str) -> Optional[AgentProfile]:
    for a in GROUPS.get(group, {}).values():
        if a.is_group_leader:
            return a
    return None


def get_all_agents() -> list[AgentProfile]:
    _ORDER = {"management": 0, "media_group": 1, "dev_group": 2}
    agents = list(AGENT_ORG.values())
    agents.sort(key=lambda a: (_ORDER.get(a.group, 99), a.level, a.name))
    return agents


def get_display_name(name: str) -> str:
    agent = AGENT_ORG.get(name)
    return f"{agent.emoji} {agent.display_name}" if agent else name


def get_temperature(name: str) -> float:
    agent = AGENT_ORG.get(name)
    return agent.temperature if agent else BALANCED
