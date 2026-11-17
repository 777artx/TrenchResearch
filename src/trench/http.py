"""Rate-limited, retrying HTTP client that caches every response body."""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from trench.rawstore import RawRecord, RawStore
from trench.timeutil import utcnow


class NotFound(Exception):
    """The upstream returned 404 for a resource."""


class UpstreamError(Exception):
    """The upstream failed after all retries."""


class RateLimiter:
    """Sliding-window limiter: at most ``max_calls`` per ``period`` seconds."""

    def __init__(
        self,
        max_calls: int,
        period: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.max_calls = max_calls
        self.period = period
        self._clock = clock
        self._sleep = sleep
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            while True:
                now = self._clock()
                while self._calls and now - self._calls[0] >= self.period:
                    self._calls.popleft()
                if len(self._calls) < self.max_calls:
                    self._calls.append(now)
                    return
                self._sleep(self.period - (now - self._calls[0]) + 0.01)


@dataclass(frozen=True)
class Fetched:
    data: Any
    raw: RawRecord


class HttpClient:
    def __init__(
        self,
        *,
        source: str,
        base_url: str,
        raw_store: RawStore,
        max_per_minute: int,
        timeout: float = 60.0,
        max_retries: int = 5,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        headers: dict[str, str] | None = None,
    ):
        self.source = source
        self.raw_store = raw_store
        self.max_retries = max_retries
        self._sleep = sleep
        self.limiter = RateLimiter(max_per_minute, sleep=sleep)
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            transport=transport,
            headers={"User-Agent": "trench-research/0.1", **(headers or {})},
        )

    def close(self) -> None:
        self._client.close()

    def get_json(self, endpoint: str, params: dict | None = None) -> Fetched:
        params = {k: v for k, v in (params or {}).items() if v is not None}
        last_err: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self.limiter.acquire()
            try:
                resp = self._client.get(endpoint, params=params)
            except httpx.TransportError as exc:
                last_err = exc
                self._sleep(min(60.0, 2.0**attempt))
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                last_err = UpstreamError(f"{resp.status_code} on {endpoint}")
                retry_after = resp.headers.get("Retry-After")
                try:
                    wait = float(retry_after) if retry_after else 2.0**attempt
                except ValueError:
                    wait = 2.0**attempt
                self._sleep(min(120.0, wait))
                continue
            if resp.status_code == 404:
                raise NotFound(f"{self.source}: 404 on {endpoint} {params}")
            if resp.status_code >= 400:
                raise UpstreamError(
                    f"{self.source}: {resp.status_code} on {endpoint}: {resp.text[:300]}"
                )
            raw = self.raw_store.save(
                source=self.source,
                url=str(resp.request.url),
                endpoint=endpoint,
                params=params,
                status=resp.status_code,
                body=resp.content,
                fetched_at=utcnow(),
            )
            return Fetched(data=json.loads(resp.content), raw=raw)
        raise UpstreamError(f"{self.source}: gave up on {endpoint} {params}: {last_err}")
