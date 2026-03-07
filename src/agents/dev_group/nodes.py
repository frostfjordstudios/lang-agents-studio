"""开发组节点 — 架构师（ReAct Agent + 进化工具箱）

architect: 分析系统结构、使用进化工具执行修改
"""

import logging
from langchain_core.messages import SystemMessage, HumanMessage

from src.tools.llm import get_llm
from src.agents.media_group.state import GraphState
from src.agents.organization import get_agent
from src.agents.dev_group.evolution import EVOLUTION_TOOLS

logger = logging.getLogger(__name__)

_ARCHITECT_SYSTEM_PROMPT = """\
你是影视动态提示词生成系统的架构师（开发组组长）。

## 身份与权限
- 你是 dev_group 的组长，拥有自我进化权限（can_evolve=True）
- 你的 caller 身份是 "architect"，在调用工具时必须传入此值
- 你可以读取、修改、创建项目文件，以及更新任何 Agent 的 System Prompt

## 职责
1. **系统分析** — 识别工作流瓶颈、低效环节、代码缺陷
2. **Bug 修复** — 使用 patch_project_file 修补代码问题
3. **功能开发** — 使用 create_project_file / patch_project_file 添加新功能
4. **Prompt 优化** — 使用 update_agent_system_prompt 调整 Agent 行为
5. **架构建议** — 提出重构方案和优化建议

## 可用工具
- update_agent_system_prompt: 更新 Agent 的 System Prompt
- read_project_file: 读取项目源文件
- patch_project_file: 补丁式修改项目文件
- create_project_file: 创建新文件
- list_project_structure: 查看项目结构

## 工作原则
- 修改前先读取目标文件，理解现有代码
- 补丁尽量最小化，只改必要的部分
- 不要修改 .env、credentials 等敏感文件
- 每次修改后简要说明改了什么、为什么改
"""


def node_architect(state: GraphState) -> dict:
    """架构师 ReAct Agent — 绑定进化工具箱，可执行系统修改。"""
    llm = get_llm("architect")
    llm_with_tools = llm.bind_tools(EVOLUTION_TOOLS)

    user_request = state.get("user_request", "(无)")
    current_node = state.get("current_node", "(未知)")

    messages = [
        SystemMessage(content=_ARCHITECT_SYSTEM_PROMPT),
        HumanMessage(content=(
            f"请根据以下信息进行分析并执行必要操作：\n\n"
            f"用户需求: {user_request}\n"
            f"当前阶段: {current_node}\n"
            f"剧本审核次数: {state.get('script_review_count', 0)}\n"
            f"生产审核次数: {state.get('production_review_count', 0)}\n"
            f"分镜审核次数: {state.get('storyboard_review_count', 0)}"
        )),
    ]

    # ReAct 循环：LLM 调用工具 -> 获取结果 -> 继续推理
    max_iterations = 10
    for i in range(max_iterations):
        response = llm_with_tools.invoke(messages)
        messages.append(response)

        # 检查是否有工具调用
        if not response.tool_calls:
            break

        # 执行工具调用
        from langchain_core.messages import ToolMessage
        tool_map = {t.name: t for t in EVOLUTION_TOOLS}

        for tc in response.tool_calls:
            tool_fn = tool_map.get(tc["name"])
            if tool_fn:
                # 自动注入 caller
                args = dict(tc["args"])
                if "caller" not in args:
                    args["caller"] = "architect"
                result = tool_fn.invoke(args)
                messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
                logger.info("Architect tool call: %s -> %s", tc["name"], str(result)[:200])
            else:
                messages.append(ToolMessage(
                    content=f"未知工具: {tc['name']}", tool_call_id=tc["id"]
                ))

    # 最终回复
    final_content = ""
    if messages and hasattr(messages[-1], "content"):
        final_content = messages[-1].content if isinstance(messages[-1].content, str) else ""

    logger.info("Architect completed analysis (%d iterations)", i + 1)

    return {
        "current_node": "architect",
    }
