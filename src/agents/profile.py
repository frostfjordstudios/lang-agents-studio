"""AgentProfile 数据类 — 单个 Agent 的完整身份档案"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentProfile:
    name: str                      # 内部标识 (e.g. "writer")
    display_name: str              # 中文显示名 (e.g. "编剧")
    emoji: str                     # 消息前缀 emoji
    group: str                     # 所属组: "management" | "media_group" | "dev_group"
    level: int                     # 权限层级: 1=管理层, 2=组长, 3=组员
    temperature: float             # LLM 温度
    prompt_path: str = ""          # System Prompt 相对路径
    is_group_leader: bool = False  # 是否为组长
    can_evolve: bool = False       # 是否有自我进化权限
    description: str = ""          # 职责描述
