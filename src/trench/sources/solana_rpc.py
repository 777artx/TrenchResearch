"""Token-account owner resolution over Solana RPC (Helius; key injected by the proxy).

``getMultipleAccounts`` with ``jsonParsed`` returns the owner and mint of up to 100
token accounts per call, at 1 Helius credit per call. Results are cached in the lake
table ``sol_token_accounts`` and never re-fetched, because a token account's mint
never changes and its owner almost never does. Accounts that no longer exist
(closed after the trade, common for temporary wrapped-SOL accounts) are cached with
status ``closed``.
"""

from __future__ import annotations

from collections.abc import Iterable

import httpx

from trench.http import RateLimiter

HELIUS_RPC = "https://mainnet.helius-rpc.com/"
BATCH = 100


class SolanaRPC:
    def __init__(self, url: str = HELIUS_RPC, per_minute: int = 300,
                 transport: httpx.BaseTransport | None = None):
        # Helius free plan: 10 requests/second. 300/min keeps half of that free.
        self.url = url
        self.limiter = RateLimiter(per_minute)
        self._c = httpx.Client(timeout=60, transport=transport,
                               headers={"User-Agent": "trench-research/0.1"})
        self.calls = 0

    def close(self) -> None:
        self._c.close()

    def _call(self, method: str, params: list):
        self.limiter.acquire()
        self.calls += 1
        r = self._c.post(self.url, json={"jsonrpc": "2.0", "id": 1, "method": method,
                                         "params": params})
        r.raise_for_status()
        body = r.json()
        if "error" in body:
            raise RuntimeError(f"{method}: {body['error']}")
        return body["result"]

    def token_account_owners(self, accounts: Iterable[str]) -> list[dict]:
        accounts = [a for a in dict.fromkeys(accounts) if a]
        out = []
        for i in range(0, len(accounts), BATCH):
            batch = accounts[i : i + BATCH]
            res = self._call("getMultipleAccounts", [batch, {"encoding": "jsonParsed"}])
            for acct, val in zip(batch, res["value"], strict=True):
                row = {"account": acct, "owner": None, "mint": None, "program": None,
                       "status": "closed"}
                if val is not None:
                    data = val.get("data")
                    parsed = data.get("parsed") if isinstance(data, dict) else None
                    info = (parsed or {}).get("info") or {}
                    row["program"] = val.get("owner")
                    if (parsed or {}).get("type") == "account" and info.get("owner"):
                        row.update(owner=info["owner"], mint=info.get("mint"), status="ok")
                    else:
                        row["status"] = "not_token_account"
                out.append(row)
        return out
