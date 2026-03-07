"""Agent LLM 温度常量 — 覆盖完整温度谱（0.0 ~ 1.0）"""

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
FREESTYLE   = 0.9    # 自由：创意讨论
UNHINGED    = 1.0    # 无拘：纯创意实验（慎用）
