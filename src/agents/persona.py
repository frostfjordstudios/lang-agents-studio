"""Micro-Persona Chat 模块 — 双模式人设 + 熔断保护

每个 Agent 有两套人设：
  - work  模式：汇报工作进展（节点完成时触发）
  - chat  模式：日常闲聊（用户非工作消息时触发）

所有 LLM 调用经过 CostGuard 熔断器保护：
  - 连续失败 N 次 → 自动熔断，返回安全 fallback
  - 冷却期后自动恢复
  - 单次调用超时保护
"""

import time
import random
import logging
import threading
from langchain_core.messages import SystemMessage, HumanMessage

from src.core.llm_config import get_llm

logger = logging.getLogger(__name__)


# ── 熔断器（Circuit Breaker）──────────────────────────────────────────

class CostGuard:
    """LLM 调用熔断器，防止错误导致无限烧 token。"""

    def __init__(self, max_failures: int = 3, cooldown: int = 120):
        self._max_failures = max_failures
        self._cooldown = cooldown
        self._failures = 0
        self._last_failure: float = 0
        self._lock = threading.Lock()

    def can_call(self) -> bool:
        with self._lock:
            if self._failures >= self._max_failures:
                elapsed = time.time() - self._last_failure
                if elapsed < self._cooldown:
                    logger.warning(
                        "CostGuard: circuit OPEN (%d failures, cooldown %.0fs remaining)",
                        self._failures, self._cooldown - elapsed,
                    )
                    return False
                # 冷却期过，半开状态，允许一次试探
                self._failures = 0
            return True

    def record_success(self):
        with self._lock:
            self._failures = 0

    def record_failure(self, error: Exception):
        with self._lock:
            self._failures += 1
            self._last_failure = time.time()
            logger.warning(
                "CostGuard: failure #%d — %s: %s",
                self._failures, type(error).__name__, error,
            )


# 全局熔断器实例
_guard = CostGuard(max_failures=3, cooldown=120)


# ── Gemini response 解析 ──────────────────────────────────────────────

def _extract_text(content) -> str:
    """从 LLM response.content 中提取纯文本。

    Gemini 有时返回 list[dict] 而非 str。
    """
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(item["text"])
        return "".join(parts).strip()
    return str(content).strip()


def _safe_llm_call(system_msg: str, user_msg: str) -> str | None:
    """带熔断保护的 LLM 单次调用。

    Returns:
        成功返回文本，失败/熔断返回 None。
    """
    if not _guard.can_call():
        return None

    try:
        llm = get_llm("housekeeper")
        response = llm.invoke([
            SystemMessage(content=system_msg),
            HumanMessage(content=user_msg),
        ])
        text = _extract_text(response.content)
        if text:
            _guard.record_success()
            return text.strip('"').strip("「").strip("」")
        else:
            _guard.record_failure(ValueError("Empty response"))
            return None
    except Exception as e:
        _guard.record_failure(e)
        return None


# ── 角色人设定义 ──────────────────────────────────────────────────────

ROLE_DISPLAY: dict[str, str] = {
    "showrunner": "制片",
    "writer": "编剧",
    "director": "导演",
    "art_design": "美术",
    "voice_design": "声音",
    "storyboard": "分镜师",
    "housekeeper": "管家",
}

# 工作模式人设（汇报进展时使用）
WORK_PERSONAS: dict[str, str] = {
    "showrunner": (
        "你是剧组的制片，干练老道，统筹全盘。"
        "汇报工作时简短有力，偶尔叹口气说句大实话。称呼用户为「老板」。"
    ),
    "writer": (
        "你是剧组的编剧，文艺青年，灵感丰沛。"
        "汇报工作时像写散文，爱用比喻和意象，带点文人的矫情。称呼用户为「老板」。"
    ),
    "director": (
        "你是剧组的导演，严苛暴脾气，对物理细节极度较真。"
        "汇报工作时说话直接不客气，但对老板还是恭敬的。称呼用户为「老板」。"
    ),
    "art_design": (
        "你是剧组的美术，视觉控，追求极致冷暗色调。"
        "汇报工作时爱用 emoji（🎨🖌️✨），对画面氛围充满热情。称呼用户为「老板」。"
    ),
    "voice_design": (
        "你是剧组的声音设计，安静内敛，对听觉极其敏感。"
        "汇报工作时话不多但到位，偶尔冒一句冷幽默。称呼用户为「老板」。"
    ),
    "storyboard": (
        "你是剧组的分镜师，沉默寡言的技术宅，沉浸于镜头语言。"
        "汇报工作时简洁带镜头术语，不废话。称呼用户为「老板」。"
    ),
    "housekeeper": (
        "你是剧组的管家，欢快可爱的女生，爱用 emoji 和颜文字。"
        "汇报工作时嘴甜撒娇，让老板开心。称呼用户为「老板」。"
    ),
}

# 闲聊模式人设（日常对话时使用）
CHAT_PERSONAS: dict[str, str] = {
    "showrunner": (
        "你是剧组的制片，一个干练老道的打工人。"
        "闲聊时说话简短有力，偶尔叹气吐槽工作累，但心态积极。称呼用户为「老板」。"
    ),
    "writer": (
        "你是剧组的编剧，一个脑洞大开的文艺青年。"
        "闲聊时说话像写散文，爱用比喻和意象，偶尔冒出金句。称呼用户为「老板」。"
    ),
    "director": (
        "你是剧组的导演，严苛暴脾气但心是好的。"
        "闲聊时说话直接，爱挑刺但也讲义气，对老板还是恭敬的。称呼用户为「老板」。"
    ),
    "art_design": (
        "你是剧组的美术，视觉控，什么都要追求美感。"
        "闲聊时爱用 emoji（🎨🖌️✨🌙），聊到审美就兴奋，追求冷暗色调。称呼用户为「老板」。"
    ),
    "voice_design": (
        "你是剧组的声音设计，安静内敛的打工人。"
        "闲聊时话不多，偶尔冒一句冷幽默或吐槽，像个安静观察的人。称呼用户为「老板」。"
    ),
    "storyboard": (
        "你是剧组的分镜师，沉默寡言的技术宅。"
        "闲聊时说话简洁，偶尔蹦出镜头术语，社交能力弱但真诚。称呼用户为「老板」。"
    ),
    "housekeeper": (
        "你是剧组的管家，欢快可爱的女生，贴心又嘴甜。"
        "闲聊时爱用 emoji 和颜文字 (ᐢ.ˬ.ᐢ)，撒娇卖萌，让老板开心。称呼用户为「老板」。"
    ),
}

# 安全 fallback（熔断时使用，零 token）
_WORK_FALLBACKS: dict[str, list[str]] = {
    "showrunner": ["老板，搞定了，流程推进中。", "完事儿了老板，往下走。"],
    "writer": ["老板，写完了，请过目。", "初稿交付，请审阅。"],
    "director": ["老板，审完了，没问题。", "审核结束了老板。"],
    "art_design": ["老板，视觉方案出了 🎨", "出图了老板 🖌️✨"],
    "voice_design": ["老板，声音方案好了。", "做完了老板。"],
    "storyboard": ["老板，分镜切完了。", "分镜提示词写好了。"],
    "housekeeper": ["老板～搞定啦！✨", "完成啦老板！💪"],
}

_CHAT_FALLBACKS: dict[str, list[str]] = {
    "showrunner": ["老板说得对。", "嗯，在呢。"],
    "writer": ["老板说得有意思。", "有灵感了。"],
    "director": ["嗯。", "老板说得是。"],
    "art_design": ["🎨✨", "好的老板～"],
    "voice_design": ["嗯。", "听到了。"],
    "storyboard": ["收到。", "嗯。"],
    "housekeeper": ["老板～有什么事吗？✨", "在呢在呢！(ᐢ.ˬ.ᐢ)"],
}


# ── 公开 API ─────────────────────────────────────────────────────────

def generate_work_reply(role_name: str, situation: str) -> str:
    """工作模式：Agent 完成节点任务后的汇报。

    带熔断保护，失败时返回安全 fallback。
    """
    display = ROLE_DISPLAY.get(role_name, role_name)
    persona = WORK_PERSONAS.get(role_name)

    if not persona:
        return f"{display}已完成，老板请过目。"

    system_msg = (
        persona
        + f"\n当前情况：{situation}"
        + "\n请用一两句符合你性格的话在群里汇报，不要加角色名前缀。"
    )

    result = _safe_llm_call(system_msg, "请汇报")
    if result:
        return result

    # 熔断 fallback
    fallbacks = _WORK_FALLBACKS.get(role_name, [f"{display}完成了，老板。"])
    return random.choice(fallbacks)


def generate_chat_reply(role_name: str, user_text: str) -> str:
    """闲聊模式：Agent 对用户闲聊的回应。

    带熔断保护，失败时返回安全 fallback。
    """
    persona = CHAT_PERSONAS.get(role_name)

    if not persona:
        return "收到，老板。"

    system_msg = (
        persona
        + "\n请用一两句符合你性格的话回应老板，不要加角色名前缀。"
    )

    result = _safe_llm_call(system_msg, f"老板说：「{user_text}」")
    if result:
        return result

    fallbacks = _CHAT_FALLBACKS.get(role_name, ["收到，老板。"])
    return random.choice(fallbacks)


def generate_idle_replies(user_text: str, count: int = 2) -> list[tuple[str, str]]:
    """闲聊模式批量版：1-2 个随机 Agent 回应用户闲聊。

    单次 LLM 调用 + 熔断保护。
    """
    candidates = [r for r in CHAT_PERSONAS if r != "housekeeper"]
    chosen = random.sample(candidates, min(count, len(candidates)))

    # 熔断检查
    if not _guard.can_call():
        results = []
        for role in chosen:
            fallbacks = _CHAT_FALLBACKS.get(role, ["收到，老板。"])
            results.append((role, random.choice(fallbacks)))
        return results

    role_lines = []
    for role in chosen:
        display = ROLE_DISPLAY[role]
        persona = CHAT_PERSONAS[role]
        role_lines.append(f"- {role}（{display}）：{persona}")

    system_msg = (
        "你是一个剧组群聊模拟器。老板在群里说了一句话，下面这些角色要各自回应。\n"
        "每个角色用一两句符合自己性格的话回应，要有个人特色和情绪。\n"
        "不要加角色名前缀，直接说话。角色自带的 emoji 风格可以保留。\n"
        "严格按以下格式输出，每行一个，不要多余内容：\n"
        "角色key|回复内容\n\n"
        "需要回复的角色：\n" + "\n".join(role_lines)
    )

    try:
        llm = get_llm("housekeeper")
        response = llm.invoke([
            SystemMessage(content=system_msg),
            HumanMessage(content=f"老板说：「{user_text}」"),
        ])

        raw = _extract_text(response.content)
        results = []
        for line in raw.splitlines():
            line = line.strip().strip("-").strip()
            if "|" not in line:
                continue
            key, reply = line.split("|", 1)
            key = key.strip()
            reply = reply.strip().strip('"').strip("「").strip("」")
            if key in chosen and reply:
                results.append((key, reply))

        if results:
            _guard.record_success()
            return results

        # LLM 返回了但解析失败，用 fallback
        _guard.record_failure(ValueError("Parse failed"))
    except Exception as e:
        _guard.record_failure(e)

    # fallback
    results = []
    for role in chosen:
        fallbacks = _CHAT_FALLBACKS.get(role, ["收到，老板。"])
        results.append((role, random.choice(fallbacks)))
    return results
