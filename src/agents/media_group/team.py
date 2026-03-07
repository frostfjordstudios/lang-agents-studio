"""影视组成员定义"""

from src.agents.profile import AgentProfile
from src.agents.temperature import STRICT, CREATIVE, ANALYTICAL, EXPRESSIVE, PRECISE

TEAM: dict[str, AgentProfile] = {
    "showrunner": AgentProfile(
        name="showrunner", display_name="制片人", emoji="🎯",
        group="media_group", level=2, temperature=STRICT,
        prompt_path="agents/media_group/showrunner/showrunner.md",
        is_group_leader=True,
        description="影视组组长，负责业务审核、合规审核、评分汇总",
    ),
    "writer": AgentProfile(
        name="writer", display_name="编剧", emoji="✍️",
        group="media_group", level=3, temperature=CREATIVE,
        prompt_path="agents/media_group/writer/writer.md",
        description="编写剧本，支持联网搜索，可被打回修改",
    ),
    "director": AgentProfile(
        name="director", display_name="导演", emoji="🎬",
        group="media_group", level=3, temperature=ANALYTICAL,
        prompt_path="agents/media_group/director/director.md",
        description="剧本审核、导演拆解、生产审核、分镜终审",
    ),
    "art_design": AgentProfile(
        name="art_design", display_name="美术设计", emoji="🎨",
        group="media_group", level=3, temperature=CREATIVE,
        prompt_path="agents/media_group/art-design/art-design.md",
        description="基于导演拆解生成美术设计方案和提示词",
    ),
    "voice_design": AgentProfile(
        name="voice_design", display_name="声音设计", emoji="🔊",
        group="media_group", level=3, temperature=EXPRESSIVE,
        prompt_path="agents/media_group/voice-design/voice-design.md",
        description="基于导演拆解生成声音设计方案",
    ),
    "storyboard": AgentProfile(
        name="storyboard", display_name="分镜师", emoji="📐",
        group="media_group", level=3, temperature=PRECISE,
        prompt_path="agents/media_group/storyboard-artist/storyboard-artist.md",
        description="整合所有材料编写最终分镜提示词",
    ),
}
