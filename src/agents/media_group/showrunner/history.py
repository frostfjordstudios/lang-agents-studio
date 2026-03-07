"""制片人对话历史管理"""

_MAX_HISTORY = 20

_showrunner_history: dict[str, list] = {}


def get_history(thread_id: str) -> list:
    if thread_id not in _showrunner_history:
        _showrunner_history[thread_id] = []
    return _showrunner_history[thread_id]


def append_and_trim(thread_id: str, *messages):
    history = get_history(thread_id)
    for msg in messages:
        history.append(msg)
    if len(history) > _MAX_HISTORY * 2:
        _showrunner_history[thread_id] = history[-_MAX_HISTORY:]
