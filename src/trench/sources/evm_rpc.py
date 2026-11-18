"""Minimal EVM JSON-RPC client with batching and adaptive ``eth_getLogs`` ranges.

Public RPCs cap log queries by block range and by result count, with different
limits and error texts. ``get_logs`` starts with a wide range and halves it on any
range/size error, then widens again after successes.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator

import httpx

from trench.http import RateLimiter

log = logging.getLogger(__name__)

RPC_URLS = {
    "robinhood": "https://rpc.mainnet.chain.robinhood.com",
    "base": "https://base-rpc.publicnode.com",
    "ethereum": "https://ethereum-rpc.publicnode.com",
}
RANGE_ERRORS = ("exceed", "limit", "max", "spans", "too many", "range", "retry with")


class RPCError(Exception):
    pass


class EvmRPC:
    def __init__(self, url: str, per_minute: int = 120,
                 transport: httpx.BaseTransport | None = None):
        self.url = url
        self.limiter = RateLimiter(per_minute)
        self._c = httpx.Client(timeout=90, transport=transport,
                               headers={"User-Agent": "trench-research/0.1"})
        self.calls = 0

    def close(self) -> None:
        self._c.close()

    def _post(self, payload):
        self.limiter.acquire()
        self.calls += 1
        for attempt in range(6):
            try:
                r = self._c.post(self.url, json=payload)
            except httpx.TransportError:
                continue
            if r.status_code == 429 or r.status_code >= 500:
                ra = r.headers.get("Retry-After")
                wait = float(ra) if ra and ra.replace(".", "", 1).isdigit() else 5 * 2**attempt
                time.sleep(min(wait, 120))
                continue
            r.raise_for_status()
            return r.json()
        raise RPCError(f"{self.url}: gave up after retries")

    def call(self, method: str, params: list):
        body = self._post({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        if "error" in body:
            raise RPCError(str(body["error"]))
        return body["result"]

    def batch(self, method: str, params_list: list[list]) -> list:
        """One HTTP request, but rate-limited per item: public RPCs (Robinhood's)
        count each call inside a batch toward their limit."""
        if not params_list:
            return []
        for _ in range(len(params_list) - 1):
            self.limiter.acquire()
        body = self._post([{"jsonrpc": "2.0", "id": i, "method": method, "params": p}
                           for i, p in enumerate(params_list)])
        by_id = {b["id"]: b for b in body}
        return [by_id.get(i, {}).get("result") for i in range(len(params_list))]

    def head(self) -> int:
        return int(self.call("eth_blockNumber", []), 16)

    def get_logs(self, start: int, end: int, *, address=None, topics=None,
                 step: int = 20_000, min_step: int = 50) -> Iterator[list[dict]]:
        """Yield lists of logs covering [start, end], shrinking the range on errors."""
        cur = start
        while cur <= end:
            hi = min(end, cur + step - 1)
            flt = {"fromBlock": hex(cur), "toBlock": hex(hi)}
            if address is not None:
                flt["address"] = address
            if topics is not None:
                flt["topics"] = topics
            try:
                logs = self.call("eth_getLogs", [flt])
            except RPCError as exc:
                if any(k in str(exc).lower() for k in RANGE_ERRORS) and step > min_step:
                    step = max(min_step, step // 2)
                    continue
                raise
            yield logs
            cur = hi + 1
            if len(logs) < 2_000:
                step = min(step * 2, 200_000)
