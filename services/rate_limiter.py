"""Ограничение частоты запросов на пользователя (скользящее окно, в памяти процесса)."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Callable


class RateLimiter:
    def __init__(
        self,
        max_requests: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._clock = clock
        self._hits: defaultdict[int, deque[float]] = defaultdict(deque)

    def acquire(self, user_id: int) -> float:
        """Регистрирует запрос. Возвращает 0, если можно, иначе — через сколько секунд повторить."""
        now = self._clock()
        hits = self._hits[user_id]
        while hits and now - hits[0] >= self._window:
            hits.popleft()
        if len(hits) >= self._max:
            return self._window - (now - hits[0])
        hits.append(now)
        return 0.0
