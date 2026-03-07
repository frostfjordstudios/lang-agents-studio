"""跨模块共享的基础类型定义"""

from typing import Callable, Any

# 工作流启动回调签名
WorkflowStarter = Callable[[str, str, str], None]

# 通用消息处理器签名
MessageHandler = Callable[..., Any]
