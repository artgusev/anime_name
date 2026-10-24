"""TTL-кэш ответов: одинаковые запросы Sonarr не ходят в Prowlarr повторно."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Callable, Generic, Hashable, TypeVar

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


class TTLCache(Generic[K, V]):
    """Потокобезопасный кэш: записи живут ``ttl`` секунд, хранится не больше ``max_size`` штук.

    ``ttl <= 0`` или ``max_size <= 0`` выключают кэш: ``get`` всегда промахивается,
    ``get_or_fetch`` просто вызывает ``fetch``.
    """

    def __init__(
        self, ttl: float, max_size: int = 256, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.ttl = float(ttl)
        self.max_size = int(max_size)
        self._clock = clock
        self._lock = threading.Lock()
        self._data: OrderedDict[K, tuple[float, V]] = OrderedDict()
        # key -> (замок, [число ожидающих]); одинаковые запросы ждут один fetch, а не делают свой
        self._inflight: dict[K, tuple[threading.Lock, list[int]]] = {}

    @property
    def enabled(self) -> bool:
        return self.ttl > 0 and self.max_size > 0

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)

    def get(self, key: K) -> V | None:
        if not self.enabled:
            return None
        now = self._clock()
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            expires, value = item
            if expires <= now:
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return value

    def set(self, key: K, value: V) -> None:
        if not self.enabled:
            return
        now = self._clock()
        with self._lock:
            self._data[key] = (now + self.ttl, value)
            self._data.move_to_end(key)
            while self._data:
                oldest, (expires, _) = next(iter(self._data.items()))
                if expires <= now or len(self._data) > self.max_size:
                    del self._data[oldest]
                else:
                    break

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def get_or_fetch(
        self,
        key: K,
        fetch: Callable[[], V],
        *,
        should_cache: Callable[[V], bool] = lambda value: True,
    ) -> tuple[V, bool]:
        """Вернуть ``(значение, взято_из_кэша)``."""
        if not self.enabled:
            return fetch(), False
        lock = self._acquire_inflight(key)
        try:
            with lock:
                cached = self.get(key)
                if cached is not None:
                    return cached, True
                value = fetch()
                if should_cache(value):
                    self.set(key, value)
                return value, False
        finally:
            self._release_inflight(key)

    def _acquire_inflight(self, key: K) -> threading.Lock:
        with self._lock:
            entry = self._inflight.get(key)
            if entry is None:
                entry = (threading.Lock(), [0])
                self._inflight[key] = entry
            entry[1][0] += 1
            return entry[0]

    def _release_inflight(self, key: K) -> None:
        with self._lock:
            entry = self._inflight.get(key)
            if entry is None:
                return
            entry[1][0] -= 1
            if entry[1][0] <= 0:
                del self._inflight[key]
