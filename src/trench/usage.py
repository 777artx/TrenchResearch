"""Monthly usage ledger with hard caps, so free plans are never exhausted.

Every metered call is charged *before* it is made. If the charge would take the
provider past its cap for the current UTC month, the call is refused with
``QuotaExceeded`` and nothing is sent. Caps sit well below each free allowance so
that other uses of the same key (for example the Helius dashboard) still have room.

Credit costs are deliberately conservative. Where a provider's exact price for a
method is unknown, the higher figure is used.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path

from trench.timeutil import utcnow


class QuotaExceeded(Exception):
    pass


@dataclass(frozen=True)
class Plan:
    provider: str
    monthly_allowance: float
    cap: float  # our own ceiling, below the allowance
    unit: str
    costs: dict[str, float]
    default_cost: float


PLANS: dict[str, Plan] = {
    # Helius free plan: 1,000,000 credits a month. Standard RPC calls cost 1 credit;
    # enhanced transactions API is charged at 100 credits per call to be safe.
    "helius": Plan("helius", 1_000_000, 700_000, "credits",
                   {"getMultipleAccounts": 1, "getAccountInfo": 1, "getSignaturesForAddress": 1,
                    "getTransaction": 1, "getSlot": 1, "enhanced_transactions": 100},
                   default_cost=10),
    # Alchemy free plan: 30,000,000 compute units a month. Costs per method follow
    # Alchemy's published compute-unit table, rounded up.
    "alchemy": Plan("alchemy", 30_000_000, 20_000_000, "compute units",
                    {"eth_blockNumber": 10, "eth_getLogs": 75, "eth_getBlockByNumber": 20,
                     "getTransaction": 40, "getSignaturesForAddress": 40,
                     "getMultipleAccounts": 20, "getSlot": 10},
                    default_cost=100),
}


class Ledger:
    """Per-provider monthly counters in ``<data>/usage/<provider>/<YYYY-MM>.json``."""

    def __init__(self, root: Path | None = None):
        self.root = Path(root or os.environ.get("TRENCH_DATA_DIR", "data")) / "usage"
        self._lock = threading.Lock()

    def _path(self, provider: str) -> Path:
        return self.root / provider / f"{utcnow():%Y-%m}.json"

    def used(self, provider: str) -> float:
        p = self._path(provider)
        return json.loads(p.read_text())["used"] if p.exists() else 0.0

    def charge(self, provider: str, method: str, n: int = 1) -> float:
        plan = PLANS[provider]
        cost = plan.costs.get(method, plan.default_cost) * n
        with self._lock:
            p = self._path(provider)
            state = json.loads(p.read_text()) if p.exists() else {"used": 0.0, "by_method": {}}
            if state["used"] + cost > plan.cap:
                raise QuotaExceeded(
                    f"{provider}: {method} would bring this month to "
                    f"{state['used'] + cost:,.0f} {plan.unit} > cap {plan.cap:,.0f} "
                    f"(free allowance {plan.monthly_allowance:,.0f})"
                )
            state["used"] += cost
            state["by_method"][method] = state["by_method"].get(method, 0) + cost
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".tmp")
            tmp.write_text(json.dumps(state, indent=1, sort_keys=True))
            tmp.replace(p)
            return state["used"]

    def report(self) -> dict[str, dict]:
        return {
            name: {"used": self.used(name), "cap": plan.cap,
                   "allowance": plan.monthly_allowance, "unit": plan.unit}
            for name, plan in PLANS.items()
        }
