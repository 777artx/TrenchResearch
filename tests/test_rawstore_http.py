import json

import httpx
import pytest

from trench.http import HttpClient, NotFound, RateLimiter, UpstreamError
from trench.rawstore import RawStore


def test_rate_limiter_blocks_until_window_frees():
    t = [0.0]
    sleeps = []

    def sleep(s):
        sleeps.append(s)
        t[0] += s

    rl = RateLimiter(2, period=60, clock=lambda: t[0], sleep=sleep)
    rl.acquire()
    rl.acquire()
    rl.acquire()  # third call must wait ~60s
    assert len(sleeps) == 1 and 59.9 < sleeps[0] < 60.1


def _client(tmp_path, handler, **kw):
    return HttpClient(
        source="test",
        base_url="https://example.test",
        raw_store=RawStore(tmp_path),
        max_per_minute=1000,
        transport=httpx.MockTransport(handler),
        sleep=lambda s: None,
        **kw,
    )


def test_retries_429_then_caches_body(tmp_path):
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "1"})
        return httpx.Response(200, json={"ok": True})

    c = _client(tmp_path, handler)
    f = c.get_json("/x", {"window": "all"})
    assert f.data == {"ok": True} and calls["n"] == 2
    assert json.loads(RawStore(tmp_path).load(f.raw)) == {"ok": True}
    manifest = list(tmp_path.rglob("manifest.jsonl"))
    assert len(manifest) == 1 and f.raw.sha256 in manifest[0].read_text()


def test_404_raises_not_found_and_400_is_not_retried(tmp_path):
    c = _client(tmp_path, lambda r: httpx.Response(404, json={"detail": "x"}))
    with pytest.raises(NotFound):
        c.get_json("/missing")
    calls = {"n": 0}

    def bad(req):
        calls["n"] += 1
        return httpx.Response(400, json={"detail": "bad window"})

    with pytest.raises(UpstreamError):
        _client(tmp_path, bad).get_json("/bad")
    assert calls["n"] == 1


def test_gives_up_after_max_retries(tmp_path):
    c = _client(tmp_path, lambda r: httpx.Response(503), max_retries=2)
    with pytest.raises(UpstreamError):
        c.get_json("/down")
