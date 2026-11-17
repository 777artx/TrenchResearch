import httpx
import pytest

from trench.sources.solana_rpc import SolanaRPC
from trench.usage import PLANS, Ledger, QuotaExceeded


def test_ledger_refuses_past_cap(tmp_path):
    led = Ledger(tmp_path)
    cap = PLANS["helius"].cap
    led.charge("helius", "enhanced_transactions", n=int(cap // 100))
    with pytest.raises(QuotaExceeded):
        led.charge("helius", "getMultipleAccounts")
    assert led.used("helius") == cap


def test_rpc_call_is_not_sent_when_over_cap(tmp_path):
    led = Ledger(tmp_path)
    led.charge("helius", "enhanced_transactions", n=int(PLANS["helius"].cap // 100))
    sent = {"n": 0}

    def handler(req):
        sent["n"] += 1
        return httpx.Response(200, json={"result": {"value": [None]}})

    rpc = SolanaRPC(transport=httpx.MockTransport(handler), ledger=led)
    with pytest.raises(QuotaExceeded):
        rpc.token_account_owners(["Acct1"])
    assert sent["n"] == 0
