"""Reconstruct Solana swaps from token transfers (BigQuery extract).

Why this shape: the free BigQuery dataset gives exact SPL token legs but no amounts
for native SOL transfers, and pump.fun's bonding curve moves SOL without a transfer
at all. So a swap here is defined by its *token* legs:

* **Owners.** A transfer's source account is owned by its ``authority``. A
  destination account's owner is found by deriving the associated token account
  (ATA) of each wallet that signs or pays in the same transaction, for both token
  programs; anything left over is resolved later by RPC and cached.
* **Net flows.** Within a transaction, legs are netted per (owner, mint). Routing
  hops and wrap/unwrap legs cancel out.
* **Trader vs pool.** Wallets are ed25519 keys on the curve; pool vault authorities
  are program-derived addresses, off the curve. A swap is a tracked-mint movement
  between an on-curve owner and an off-curve owner. Movements between two wallets
  are kept separately as transfers (cost basis carries over or resets, SPEC §5.4).
* **Quote.** If the trader's opposite leg is wrapped SOL, USDC or USDT, the quote
  amount is exact. Otherwise (native SOL) it is left null and priced later at the
  minute price, flagged ``quote_exact = false``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache

from solders.pubkey import Pubkey

TOKEN_PROGRAM = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
TOKEN_2022 = Pubkey.from_string("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")
ATA_PROGRAM = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")

WSOL = "So11111111111111111111111111111111111111112"
QUOTE_MINTS = {
    WSOL: "SOL",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": "USDT",
}
SPL_TYPES = {"spl-transfer", "spl-transfer-with-fee"}


@lru_cache(maxsize=2_000_000)
def ata(owner: str, mint: str, token_program: str) -> str | None:
    try:
        addr, _ = Pubkey.find_program_address(
            [bytes(Pubkey.from_string(owner)), bytes(Pubkey.from_string(token_program)),
             bytes(Pubkey.from_string(mint))],
            ATA_PROGRAM,
        )
    except ValueError:
        return None
    return str(addr)


@lru_cache(maxsize=2_000_000)
def on_curve(address: str) -> bool:
    try:
        return Pubkey.from_string(address).is_on_curve()
    except ValueError:
        return False


@dataclass
class Leg:
    tx: str
    slot: int
    ts: object
    ttype: str
    source: str | None
    destination: str | None
    authority: str | None
    value: str | None
    decimals: object
    mint: str | None


def _amount(value: str | None, decimals) -> Decimal:
    """BigQuery ``value`` is already in token units (e.g. '7170470.000000000')."""
    return Decimal(value) if value not in (None, "") else Decimal(0)


def owner_of_destination(dest: str, mint: str, candidates: Iterable[str],
                         known: dict[str, str]) -> str | None:
    if dest in known:
        return known[dest]
    for c in candidates:
        for prog in (str(TOKEN_PROGRAM), str(TOKEN_2022)):
            if ata(c, mint, prog) == dest:
                return c
    return None


def reconstruct_tx(legs: list[Leg], tracked: set[str], known_owners: dict[str, str]):
    """Return (swaps, transfers, unresolved_accounts) for one transaction."""
    spl = [lg for lg in legs if lg.ttype in SPL_TYPES and lg.mint]
    if not any(lg.mint in tracked for lg in spl):
        return [], [], set()
    candidates = {lg.authority for lg in legs if lg.authority}
    candidates |= {lg.source for lg in legs if lg.ttype == "transfer" and lg.source}
    candidates = sorted(c for c in candidates if on_curve(c))

    net: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    unresolved: set[str] = set()
    for lg in spl:
        amt = _amount(lg.value, lg.decimals)
        src_owner = lg.authority or known_owners.get(lg.source or "")
        dst_owner = owner_of_destination(lg.destination or "", lg.mint, candidates, known_owners)
        if src_owner is None:
            unresolved.add(lg.source or "")
        if dst_owner is None:
            unresolved.add(lg.destination or "")
        # Unresolved sides are netted under the raw account address, which is never
        # on-curve for a token account, so it is treated as the pool side.
        net[(src_owner or f"acct:{lg.source}", lg.mint)] -= amt
        net[(dst_owner or f"acct:{lg.destination}", lg.mint)] += amt

    first = legs[0]
    swaps, transfers = [], []
    traders = {o for (o, m), v in net.items() if m in tracked and v != 0 and on_curve(o)}
    pools = {o for (o, m), v in net.items() if m in tracked and v != 0 and not on_curve(o)}
    for trader in sorted(traders):
        for mint in sorted(m for (o, m) in net if o == trader and m in tracked):
            d = net[(trader, mint)]
            if d == 0:
                continue
            if not pools:
                # Tracked mint moved only between wallets: a transfer, not a trade.
                transfers.append({"tx_signature": first.tx, "block_slot": first.slot,
                                  "block_timestamp": first.ts, "wallet": trader,
                                  "mint": mint, "amount": str(d)})
                continue
            quote = [(QUOTE_MINTS[m], -net[(trader, m)]) for (o, m) in net
                     if o == trader and m in QUOTE_MINTS and net[(trader, m)] * d < 0]
            other = [m for (o, m) in net if o == trader and m in tracked and m != mint
                     and net[(trader, m)] * d < 0]
            swaps.append({
                "tx_signature": first.tx, "block_slot": first.slot,
                "block_timestamp": first.ts, "trader": trader, "mint": mint,
                "side": "buy" if d > 0 else "sell", "token_amount": str(abs(d)),
                "quote_asset": quote[0][0] if quote else (other[0] if other else "SOL_NATIVE"),
                "quote_amount": str(abs(quote[0][1])) if quote else None,
                "quote_exact": bool(quote),
                "n_traders_in_tx": len(traders),
            })
    return swaps, transfers, unresolved - {""}


def reconstruct(rows: Iterable[tuple], tracked: set[str],
                known_owners: dict[str, str] | None = None):
    """``rows`` ordered by tx_signature: (tx, slot, ts, type, source, destination,
    authority, value, decimals, mint)."""
    known_owners = known_owners or {}
    swaps, transfers, unresolved = [], [], set()
    cur: list[Leg] = []
    for r in rows:
        leg = Leg(*r)
        if cur and leg.tx != cur[0].tx:
            s, t, u = reconstruct_tx(cur, tracked, known_owners)
            swaps += s
            transfers += t
            unresolved |= u
            cur = []
        cur.append(leg)
    if cur:
        s, t, u = reconstruct_tx(cur, tracked, known_owners)
        swaps += s
        transfers += t
        unresolved |= u
    return swaps, transfers, unresolved


def known_owners_from_lake(lake) -> dict[str, str]:
    if "sol_token_accounts" not in lake.tables():
        return {}
    return dict(lake.connect().execute(
        "SELECT account, owner FROM sol_token_accounts WHERE status = 'ok'").fetchall())


def resolve_unresolved(lake, rpc, accounts: set[str], run_id: str) -> int:
    """Fetch owners for accounts not yet cached and append them to the cache."""
    from trench.timeutil import utcnow

    cached: set[str] = set()
    if "sol_token_accounts" in lake.tables():
        cached = {a for (a,) in lake.connect().execute(
            "SELECT DISTINCT account FROM sol_token_accounts").fetchall()}
    todo = sorted(a for a in accounts if a and a not in cached)
    if not todo:
        return 0
    rows = rpc.token_account_owners(todo)
    lake.write("sol_token_accounts", rows, run_id=run_id, fetched_at=utcnow())
    return len(rows)
