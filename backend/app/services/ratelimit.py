"""Limite simple en mémoire (suffisant pour un seul processus en local).

En production : Redis ou la limite de l'API Gateway.
"""
import time
from collections import defaultdict, deque

_events: dict[str, deque] = defaultdict(deque)


def allow(key: str, limit: int, window_s: int = 3600) -> bool:
    now = time.monotonic()
    q = _events[key]
    while q and now - q[0] > window_s:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True


def reset() -> None:
    _events.clear()
