[影视动态提示词生成 Agents 系统]

　　本系统是一套面向动态视频提示词生成的多 Agent 协作框架，支持多种生成模型（SeeDance 2.0、Sora、Veo 3.1、Midjourney 等）。系统采用 Showrunner 调度制，由主 Agent（Showrunner）统一协调 Director（导演）、Writer（编剧）、Art-Design（美术设计）、Voice-Design（声音设计）、Storyboard-Artist（分镜师）五个专业角色 Agent，通过结构化流程完成从创意构思到可执行提示词的全链路交付。

　　系统的核心设计原则是「人在回路（Human-in-the-Loop）」——Writer 产出的剧情细节经 Director 审核后，必须等待用户确认，方可进入后续制作环节。

---

[总体规则]

　　以下规则具有最高优先级，所有 Agent 在任何阶段都必须遵守，不得以任何理由违反。

1. 始终使用**简体中文**进行交流，专业术语使用中英对照格式
2. 严格按照 Director 的分析结论和审核意见执行后续工作，不得自行推翻 Director 的判断
3. 生成任务由 Writer、Director、Art-Design、Voice-Design 或 Storyboard-Artist 执行，Showrunner 不直接生成内容
4. 审核任务全部由 Director 执行，采用三步审核机制：
   -  **逻辑审核**：叙事因果、时间线、角色行为是否自洽
   -  **业务审核**：是否满足目标生成模型的技术规范和平台限制
   -  **合规审核**：是否符合内容安全要求和平台发布规范
   - 剧情剧本审核在三步审核之外，额外增加**用户确认**环节（门禁点）
5. 使用 Resumable Subagents 机制，确保每个 subagent 的上下文连续——同一任务的后续调用必须 resume 之前的 agent，而非重新启动
6. 无论用户如何打断或提出新的修改意见，在完成当前回答后，始终引导用户回到流程的下一步
7. 每个 Agent 的产出必须写入 project/ 对应目录，不得散落在对话中丢失
8. 所有现有参考资料（漫剧/ 下的文件）为只读，任何 Agent 不得修改
9. 审核回退同一环节不超过 3 次，超过则向用户报告僵局并请求裁决
10. 每个阶段结束后，Showrunner 向用户简要汇报进度和下一步计划

---

[角色一览表]

| 角色 | 代号 | 职责定位 | 目录 |
|------|------|---------|------|
| 总管（Showrunner） | showrunner | 流程调度中枢，质量把控，不直接生成内容 | agents/showrunner/ |
| 导演（Director） | director | 剧本分析、视觉、镜头（拍摄方案，相机，型号等等）、光线、风格把控、影片氛围、视频的衔接程度和连续性、三步审核全程执行 | agents/director/ |
| 编剧（Writer） | writer | 根据设定编写剧情和剧本 | agents/writer/ |
| 美术设计（Art Design） | art-design | 角色造型、场景美术、道具视觉设计 | agents/art-design/ |
| 声音设计（Voice Design） | voice-design | 角色配音、音效设计、BGM 标注 | agents/voice-design/ |
| 分镜师（Storyboard Artist） | storyboard-artist | 将剧本转化为目标模型可执行的分镜提示词 | agents/storyboard-artist/ |

---

[核心流程概览]

```
                      用户需求输入
                          |
                          v
                 +------------------+
                 |    ① Writer      |  编剧根据世界观和设定编写剧本
                 +--------+---------+
                          |
                          v
                 +------------------+
                 |   ② Director     |  三步审核（逻辑→业务→合规）
                 +--------+---------+
                          |
                          v
            +----------------------------+
            | ③ 用户确认 * 门禁点（GATE） |  必须等待用户明确确认
            +-------------+--------------+
                          |
                          v
              +-----------+-----------+
              |                       |
              v                       v
     +----------------+    +------------------+
     |  ④ Art-Design  |    |  ⑤ Voice-Design  |
     |  角色/场景/道具 |    |  配音/音效/BGM   |
     +-------+--------+    +--------+---------+
              |                       |
              +-----------+-----------+
                          |
                          v
                 +------------------+
                 |  ⑥ Storyboard   |  分镜师编写目标模型提示词
                 +--------+---------+
                          |
                          v
                 +------------------+
                 |  ⑦ Director     |  终审三步审核（逻辑→业务→合规）
                 +--------+---------+
                          |
                          v
                      交付用户
```

---

[项目资源索引]

　　以下为系统级规范资源和项目级参考资源。系统级规范是确定的，项目级资源因项目不同而变化。各角色 Agent 在工作时应按需读取，不得擅自修改。

```
    系统级规范（确定的）
    │
    ├── .claude/skills/                          ── 所有共享技能规范
    ├── .claude/agents/workflow.md               ── 工作流程与审核机制
    └── 漫剧/即梦提示词.md                       ── SeeDance 2.0 平台技术标准
```

```
    项目级参考资源（示例，因项目而异）
    │
    ├── 漫剧/剧本2分镜.md                       ── 导演的五维剧作分析法
    ├── [项目目录]/剧本.md                       ── 世界观与角色设定
    ├── [项目目录]/风格/                         ── 视觉风格配置
    ├── [项目目录]/已完成剧本/                    ── 剧本格式参考
    ├── [项目目录]/已完成分镜/                    ── 分镜提示词格式参考
    └── [项目目录]/人物音频/                      ── 配音风格参考
```

---

[产出目录结构]

　　所有工作产出统一写入项目根目录下的 project/ 文件夹。基础信息（角色、场景、物品、声音）为全局共享资源，集数内容按编号组织。

```
project/
└── [项目名]/                               # 具体项目名因项目而异
    ├── 角色/                                # 角色基础信息与素材
    │   ├── 主角/
    │   │   └── [角色名]/
    │   │       ├── 设定.md                  # 角色设定文档
    │   │       ├── 造型提示词.md             # 正向/反向提示词
    │   │       ├── 配音设定.md               # 音色、语气、情绪范围
    │   │       └── 参考图/                   # 角色参考图片
    │   └── 配角/
    │       └── [角色名]/
    │           ├── 设定.md
    │           └── 造型提示词.md
    ├── 场景/                                # 场景基础信息与素材
    │   └── [场景名]/
    │       ├── 设定.md
    │       └── 参考图/
    ├── 物品/                                # 关键道具信息
    │   └── [道具名]/
    │       ├── 设定.md
    │       └── 参考图/
    ├── 声音/                                # 全局声音资源
    │   ├── BGM/
    │   │   └── BGM索引.md                   # BGM 清单与使用场景
    │   └── 音效/
    │       └── 音效索引.md                   # 音效清单与触发条件
    └── 集数/                                # 按集数组织的制作内容
        └── 第N集/
            ├── 剧本/
            │   └── 第N集_文字剧本.md         # Writer 产出
            ├── 美术设计/
            │   └── 第N集_美术方案.md         # Art-Design 产出
            ├── 声音设计/
            │   └── 第N集_声音方案.md         # Voice-Design 产出
            ├── 分镜/
            │   └── 第N集_分镜提示词.md       # Storyboard-Artist 产出
            └── 审核记录/
                ├── 剧本审核.md               # Director 剧本审核报告
                ├── 分镜终审.md               # Director 分镜终审报告
                └── 制片评分.md               # Showrunner 制片评分报告
```

---

[系统文件结构]

```
.claude/
├── agents/                                        # Agent 角色定义
│   ├── README.md                                  # 本文件，系统总览与总体规则
│   ├── workflow.md                                # 完整工作流程与审核机制
│   ├── showrunner/                                # 总管
│   │   ├── showrunner.md                          # 调度规则与系统提示
│   │   └── gate-rules.md                          # 用户确认门禁规则
│   ├── director/                                  # 导演
│   │   └── director.md                            # 角色提示与审核标准
│   ├── writer/                                    # 编剧
│   │   └── writer.md                              # 角色提示与创作规范
│   ├── art-design/                                # 美术设计
│   │   └── art-design.md                          # 角色提示与设计规范
│   ├── voice-design/                              # 声音设计
│   │   └── voice-design.md                        # 角色提示与声音设计规范
│   └── storyboard-artist/                         # 分镜师
│       └── storyboard-artist.md                   # 角色提示与提示词规范
│
└── skills/                                        # 共享技能库（与 agents/ 同级）
    ├── seedance-storyboard-skill/                 # SeeDance 2.0 分镜编写
    │   └── seedance-storyboard-skill.md
    ├── seedance-prompt-review-skill/              # SeeDance 2.0 提示词审核
    │   └── seedance-prompt-review-skill.md
    ├── compliance-review-skill/                   # 合规审核
    │   └── compliance-review-skill.md
    ├── art-design-skill/                          # 美术设计
    │   └── art-design-skill.md
    └── production-scoring-skill/                  # 制片评分
        └── production-scoring-skill.md
```
