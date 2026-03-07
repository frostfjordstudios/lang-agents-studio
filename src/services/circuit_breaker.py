"""CostGuard 熔断器 — 防止 LLM 调用错误导致无限烧 token"""

import time
import logging
import threading

logger = logging.getLogger(__name__)


class CostGuard:
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


guard = CostGuard(max_failures=3, cooldown=120)
