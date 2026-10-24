import threading
import time

from animename.cache import TTLCache


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_ttl_expiry():
    clock = Clock()
    cache = TTLCache(ttl=10, max_size=8, clock=clock)
    cache.set("a", 1)
    assert cache.get("a") == 1
    clock.now = 9.9
    assert cache.get("a") == 1
    clock.now = 10.0
    assert cache.get("a") is None
    assert len(cache) == 0


def test_lru_bound():
    cache = TTLCache(ttl=100, max_size=2, clock=Clock())
    cache.set("a", 1)
    cache.set("b", 2)
    assert cache.get("a") == 1  # "a" снова свежий, вытеснится "b"
    cache.set("c", 3)
    assert cache.get("b") is None
    assert cache.get("a") == 1
    assert cache.get("c") == 3
    assert len(cache) == 2


def test_expired_entries_are_purged_on_set():
    clock = Clock()
    cache = TTLCache(ttl=10, max_size=10, clock=clock)
    cache.set("old", 1)
    clock.now = 11
    cache.set("new", 2)
    assert len(cache) == 1
    assert cache.get("new") == 2


def test_disabled_cache():
    for cache in (TTLCache(ttl=0), TTLCache(ttl=10, max_size=0)):
        assert not cache.enabled
        cache.set("a", 1)
        assert cache.get("a") is None
        calls = []
        value, hit = cache.get_or_fetch("a", lambda: calls.append(1) or "v")
        assert (value, hit) == ("v", False)
        assert calls == [1]


def test_get_or_fetch_caches_and_respects_should_cache():
    cache = TTLCache(ttl=100)
    calls = []

    def fetch():
        calls.append(1)
        return "v"

    assert cache.get_or_fetch("k", fetch) == ("v", False)
    assert cache.get_or_fetch("k", fetch) == ("v", True)
    assert calls == [1]

    cache.get_or_fetch("bad", lambda: "error", should_cache=lambda v: v != "error")
    assert cache.get("bad") is None


def test_get_or_fetch_single_flight():
    cache = TTLCache(ttl=100)
    calls = []
    started = threading.Event()
    release = threading.Event()
    results = []

    def fetch():
        calls.append(1)
        started.set()
        release.wait(2)
        return "v"

    def worker():
        results.append(cache.get_or_fetch("k", fetch))

    first = threading.Thread(target=worker)
    first.start()
    assert started.wait(2)
    second = threading.Thread(target=worker)
    second.start()
    time.sleep(0.05)
    release.set()
    first.join(2)
    second.join(2)

    assert calls == [1]
    assert sorted(hit for _, hit in results) == [False, True]
    assert all(value == "v" for value, _ in results)
