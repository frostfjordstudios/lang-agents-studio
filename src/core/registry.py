"""全局 Agent 注册表 — 联邦制架构的组织宪法

定义所有 Agent 的：
  - 身份（角色名、显示名、emoji）
  - 组织（所属组、层级、权限等级）
  - 行为（temperature、System Prompt 路径）

权限模型:
  - Level 0: 用户（绝对最高权限，可越级指挥任何 Agent）
  - Level 1: 管家 housekeeper（管理层，调度所有组长）
  - Level 2: 组长（showrunner=影视组长, architect=开发组长）
  - Level 3: 组员（writer, director, art_design, voice_design, storyboard, ...）

规则:
  - 管理层可调度组长，组长调度组内员工
  - 用户可在任何时候直接与任意 Agent 对话（绝对越级权）
  - 只有开发组（dev_group）有权执行自我进化（修改代码/Prompt/API）
"""

from dataclasses import dataclass, field
from typing import Optional


# ── 温度全谱（0.0 ~ 1.0，每 0.05 一档）─────────────────────────────

# 命名常量：覆盖完整温度谱
FROZEN      = 0.0    # 冻结：纯确定性输出（JSON schema、代码生成）
PRECISE     = 0.05   # 精确：分镜提示词（格式严格但需微量变化）
STRICT      = 0.1    # 严格：合规审核、制片终审
ANALYTICAL  = 0.15   # 分析：导演审核（需要判断但不能发散）
FOCUSED     = 0.2    # 聚焦：架构分析、导演拆解
METHODICAL  = 0.25   # 条理：技术文档、运维操作
MODERATE    = 0.3    # 适中：UI/UX 设计（需审美但有规范）
BALANCED    = 0.5    # 平衡：通用对话
EXPRESSIVE  = 0.6    # 表达：声音设计（需要情感但有框架）
CREATIVE    = 0.7    # 创意：编剧、美术设计
IMAGINATIVE = 0.8    # 想象：头脑风暴、概念探索
FREESTYLE   = 0.9    # 自由：管家闲聊、创意讨论
UNHINGED    = 1.0    # 无拘：纯创意实验（慎用）


# ── Agent 注册信息 ───────────────────────────────────────────────────

@dataclass(frozen=True)
class AgentProfile:
    """单个 Agent 的完整身份档案。"""
    name: str                   # 内部标识 (e.g. "writer")
    display_name: str           # 中文显示名 (e.g. "编剧")
    emoji: str                  # 消息前缀 emoji
    group: str                  # 所属组: "management" | "media_group" | "dev_group"
    level: int                  # 权限层级: 1=管理层, 2=组长, 3=组员
    temperature: float          # LLM 温度
    prompt_path: str = ""       # System Prompt 相对路径 (相对于 system_prompts/)
    is_group_leader: bool = False  # 是否为组长
    can_evolve: bool = False    # 是否有自我进化权限（写代码/修改系统）
    description: str = ""       # 职责描述


# ── 完整注册表 ───────────────────────────────────────────────────────

AGENT_REGISTRY: dict[str, AgentProfile] = {

    # ── 管理层 (Level 1) ──
    "housekeeper": AgentProfile(
        name="housekeeper",
        display_name="管家",
        emoji="🏠",
        group="management",
        level=1,
        temperature=FREESTYLE,
        prompt_path="agents/management/housekeeper/housekeeper.md",
        is_group_leader=False,
        can_evolve=False,
        description="项目管家，负责用户接待、任务分流、跨组协调",
    ),

    # ── 影视组 media_group (Level 2-3) ──
    "showrunner": AgentProfile(
        name="showrunner",
        display_name="制片人",
        emoji="🎯",
        group="media_group",
        level=2,
        temperature=STRICT,
        prompt_path="agents/media_group/showrunner/showrunner.md",
        is_group_leader=True,
        can_evolve=False,
        description="影视组组长，负责业务审核、合规审核、评分汇总",
    ),
    "writer": AgentProfile(
        name="writer",
        display_name="编剧",
        emoji="✍️",
        group="media_group",
        level=3,
        temperature=CREATIVE,
        prompt_path="agents/media_group/writer/writer.md",
        description="编写剧本，支持联网搜索，可被打回修改",
    ),
    "director": AgentProfile(
        name="director",
        display_name="导演",
        emoji="🎬",
        group="media_group",
        level=3,
        temperature=ANALYTICAL,
        prompt_path="agents/media_group/director/director.md",
        description="剧本审核、导演拆解、生产审核、分镜终审",
    ),
    "art_design": AgentProfile(
        name="art_design",
        display_name="美术设计",
        emoji="🎨",
        group="media_group",
        level=3,
        temperature=CREATIVE,
        prompt_path="agents/media_group/art-design/art-design.md",
        description="基于导演拆解生成美术设计方案和提示词",
    ),
    "voice_design": AgentProfile(
        name="voice_design",
        display_name="声音设计",
        emoji="🔊",
        group="media_group",
        level=3,
        temperature=EXPRESSIVE,
        prompt_path="agents/media_group/voice-design/voice-design.md",
        description="基于导演拆解生成声音设计方案",
    ),
    "storyboard": AgentProfile(
        name="storyboard",
        display_name="分镜师",
        emoji="📐",
        group="media_group",
        level=3,
        temperature=PRECISE,
        prompt_path="agents/media_group/storyboard-artist/storyboard-artist.md",
        description="整合所有材料编写最终分镜提示词",
    ),

    # ── 开发组 dev_group (Level 2-3) ──
    "architect": AgentProfile(
        name="architect",
        display_name="架构师",
        emoji="🏗️",
        group="dev_group",
        level=2,
        temperature=FOCUSED,
        prompt_path="",  # 内置 prompt，无外部文件
        is_group_leader=True,
        can_evolve=True,
        description="开发组组长，分析系统瓶颈、指导进化方向、审核代码变更",
    ),
}


# ── 查询接口 ─────────────────────────────────────────────────────────

def get_agent(name: str) -> Optional[AgentProfile]:
    """根据名称获取 Agent 档案。"""
    return AGENT_REGISTRY.get(name)


def get_group_members(group: str) -> list[AgentProfile]:
    """获取指定组的所有成员（按 level 排序，组长在前）。"""
    members = [a for a in AGENT_REGISTRY.values() if a.group == group]
    members.sort(key=lambda a: (a.level, a.name))
    return members


def get_group_leader(group: str) -> Optional[AgentProfile]:
    """获取指定组的组长。"""
    for a in AGENT_REGISTRY.values():
        if a.group == group and a.is_group_leader:
            return a
    return None


def get_all_agents() -> list[AgentProfile]:
    """获取所有已注册 Agent（按组 + 层级排序）。"""
    agents = list(AGENT_REGISTRY.values())
    _GROUP_ORDER = {"management": 0, "media_group": 1, "dev_group": 2}
    agents.sort(key=lambda a: (_GROUP_ORDER.get(a.group, 99), a.level, a.name))
    return agents


def get_agents_with_evolve_permission() -> list[AgentProfile]:
    """获取所有拥有自我进化权限的 Agent。"""
    return [a for a in AGENT_REGISTRY.values() if a.can_evolve]


def can_agent_command(commander: str, target: str) -> bool:
    """检查 commander 是否有权指挥 target。

    规则:
      - 用户（不在 registry 中）拥有绝对权限 → 调用方自行判断
      - 管理层 (level=1) 可指挥任何组长和组员
      - 组长 (level=2) 只能指挥自己组内的组员 (level=3)
      - 组员 (level=3) 不能指挥任何人
    """
    cmd = AGENT_REGISTRY.get(commander)
    tgt = AGENT_REGISTRY.get(target)
    if not cmd or not tgt:
        return False

    # 管理层可以指挥所有人
    if cmd.level == 1:
        return True

    # 组长可以指挥同组组员
    if cmd.level == 2 and cmd.group == tgt.group and tgt.level > cmd.level:
        return True

    return False


def get_display_name(name: str) -> str:
    """获取 Agent 的显示名（含 emoji）。"""
    agent = AGENT_REGISTRY.get(name)
    if agent:
        return f"{agent.emoji} {agent.display_name}"
    return name


def get_temperature(name: str) -> float:
    """获取 Agent 的温度设定。"""
    agent = AGENT_REGISTRY.get(name)
    return agent.temperature if agent else BALANCED
