"""Decode DEX swap events on EVM chains into trader-perspective token deltas.

Supported events (topic0):

* Uniswap V2 and forks, Aerodrome V2:
  ``Swap(address indexed sender, uint amount0In, uint amount1In, uint amount0Out,
  uint amount1Out, address indexed to)``
* Uniswap V3 and forks, Aerodrome Slipstream:
  ``Swap(address indexed sender, address indexed recipient, int256 amount0,
  int256 amount1, uint160 sqrtPriceX96, uint128 liquidity, int24 tick)``.
  Amounts are from the pool's side: positive means the pool received.
* Uniswap V4 (one PoolManager per chain; the pool is ``topics[1]``):
  ``Swap(bytes32 indexed id, address indexed sender, int128 amount0, int128 amount1,
  uint160, uint128, int24, uint24 fee)``. Amounts are the swapper's balance delta:
  negative means the swapper paid.

Output amounts ``d0`` and ``d1`` are always from the trader's side: positive means
the trader received that token. Token order follows the protocols: token0 is the
lower address (native ETH, the zero address, is always currency0 in V4).
"""

from __future__ import annotations

TOPIC_V2 = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"
TOPIC_V3 = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
TOPIC_AERO_V2 = "0xb3e2773606abfd36b5bd91394b3a54d1398336c65005baf7bf7a05efeffaf75b"
TOPIC_V4 = "0x40e9cecb9f5f1f1c5b9c97dec2917b7ee92e57ba5563708daca94dd84ad7112f"
POOL_TOPICS = [TOPIC_V2, TOPIC_V3, TOPIC_AERO_V2]

# Uniswap V4 PoolManager per chain. Robinhood's was found from live Swap logs on
# 2026-11-17; Ethereum's and Base's are Uniswap's published deployments.
V4_POOL_MANAGER = {
    "robinhood": "0x8366a39cc670b4001a1121b8f6a443a643e40951",
    "ethereum": "0x000000000004444c5dc75cb358380d2e3de08a90",
    "base": "0x498581ff718922c3f8e6a244956af099b2652b2b",
}


def _words(data: str) -> list[int]:
    h = data[2:] if data.startswith("0x") else data
    return [int(h[i : i + 64], 16) for i in range(0, len(h), 64)]


def _signed(x: int, bits: int = 256) -> int:
    return x - (1 << bits) if x >= 1 << (bits - 1) else x


def _addr(topic: str) -> str:
    return "0x" + topic[-40:].lower()


def decode(log: dict, chain: str) -> dict | None:
    topics = log.get("topics") or []
    if not topics:
        return None
    t0 = topics[0].lower()
    w = _words(log.get("data") or "0x")
    if t0 in (TOPIC_V2, TOPIC_AERO_V2) and len(w) >= 4 and len(topics) >= 3:
        in0, in1, out0, out1 = w[:4]
        pool, kind = log["address"].lower(), "v2"
        d0, d1 = out0 - in0, out1 - in1
        sender, recipient = _addr(topics[1]), _addr(topics[2])
    elif t0 == TOPIC_V3 and len(w) >= 2 and len(topics) >= 3:
        pool, kind = log["address"].lower(), "v3"
        d0, d1 = -_signed(w[0]), -_signed(w[1])
        sender, recipient = _addr(topics[1]), _addr(topics[2])
    elif t0 == TOPIC_V4 and len(w) >= 2 and len(topics) >= 3:
        pool, kind = topics[1].lower(), "v4"
        d0, d1 = _signed(w[0]), _signed(w[1])
        sender, recipient = _addr(topics[2]), None
    else:
        return None
    ts = log.get("blockTimestamp")
    return {
        "chain": chain, "pool_id": pool, "kind": kind,
        "block_number": int(log["blockNumber"], 16),
        "block_timestamp": int(ts, 16) if isinstance(ts, str) else ts,
        "tx_hash": log["transactionHash"].lower(), "log_index": int(log["logIndex"], 16),
        "d0": str(d0), "d1": str(d1), "sender": sender, "recipient": recipient,
    }
