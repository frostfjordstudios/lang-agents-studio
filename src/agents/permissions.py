"""Agent 权限判断 — 联邦制指挥链规则"""

from src.agents.organization import AGENT_ORG


def can_agent_command(commander: str, target: str) -> bool:
    """检查 commander 是否有权指挥 target。

    规则:
      - 管理层 (level=1) 可指挥任何组长和组员
      - 组长 (level=2) 只能指挥自己组内的组员 (level=3)
      - 组员 (level=3) 不能指挥任何人
      - 用户（不在 registry 中）拥有绝对权限，调用方自行判断
    """
    cmd = AGENT_ORG.get(commander)
    tgt = AGENT_ORG.get(target)
    if not cmd or not tgt:
        return False
    if cmd.level == 1:
        return True
    if cmd.level == 2 and cmd.group == tgt.group and tgt.level > cmd.level:
        return True
    return False


def get_agents_with_evolve_permission() -> list:
    return [a for a in AGENT_ORG.values() if a.can_evolve]
