"""全局配置常量 — 从环境变量加载"""

import os
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# System Prompts 目录
SYSTEM_PROMPTS_DIR = PROJECT_ROOT / "system_prompts"

# Agent 状态持久化目录
AGENT_STATE_DIR = PROJECT_ROOT / "agent_states"

# 日志目录
LOG_DIR = PROJECT_ROOT / "logs"

# 默认项目名称
DEFAULT_PROJECT = os.environ.get("PROJECT_NAME", "default")

# LLM 配置
LLM_MODEL = os.environ.get("LLM_MODEL", "gemini-2.0-flash")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
