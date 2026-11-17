"""Covered chains and their identifiers at each upstream source."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Chain:
    id: str  # our canonical id
    dexscreener: str
    geckoterminal: str
    tehcscreener: str
    evm: bool
    active: bool = True  # inactive chains are kept for history but not ingested or read


CHAINS: dict[str, Chain] = {
    c.id: c
    for c in [
        Chain("solana", "solana", "solana", "solana", evm=False),
        Chain("base", "base", "base", "base", evm=True),
        Chain("ethereum", "ethereum", "eth", "ethereum", evm=True),
        # BNB Chain deferred by Arthur on 2026-11-17. Entries already stored stay in history.
        Chain("bnb", "bsc", "bsc", "bnb", evm=True, active=False),
        Chain("robinhood", "robinhood", "robinhood", "robinhood", evm=True),
    ]
}

ACTIVE: tuple[str, ...] = tuple(c.id for c in CHAINS.values() if c.active)

_BY_TEH = {c.tehcscreener: c.id for c in CHAINS.values()}
_BY_GT = {c.geckoterminal: c.id for c in CHAINS.values()}
_BY_DXS = {c.dexscreener: c.id for c in CHAINS.values()}


def from_teh(name: str) -> str | None:
    return _BY_TEH.get(name)


def from_gt(name: str) -> str | None:
    return _BY_GT.get(name)


def from_dxs(name: str) -> str | None:
    return _BY_DXS.get(name)


def norm_address(chain: str, address: str) -> str:
    """EVM addresses are case-insensitive: store lowercase. Solana is base58: keep as is."""
    return address.lower() if CHAINS[chain].evm else address


# Quote, wrapped-native and stable assets. They are tagged rather than dropped, so the
# organic filters (SPEC §5.5) and the memecoin/majors/RWA buckets can use the tag.
# Rule: an asset is a quote asset if it is the chain's wrapped native token, a USD
# stablecoin or a liquid-staking token used as a routing pair.
QUOTE_ASSETS: dict[str, set[str]] = {
    "solana": {
        "So11111111111111111111111111111111111111112",  # wSOL
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
        "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
        "USD1ttGY1N17NEEHLmELoaybftRBUSErhqYiQzvEmuB",  # USD1
        "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn",  # jitoSOL
        "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",  # mSOL
    },
    "base": {
        "0x4200000000000000000000000000000000000006",  # WETH
        "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",  # USDC
    },
    "ethereum": {
        "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",  # WETH
        "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",  # USDC
        "0xdac17f958d2ee523a2206206994597c13d831ec7",  # USDT
    },
    "bnb": {
        "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c",  # WBNB
        "0x55d398326f99059ff775485246999027b3197955",  # USDT
        "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d",  # USDC
    },
    "robinhood": {
        # The three most frequent quote tokens in DexScreener pairs on 2026-11-17.
        "0x0bd7d308f8e1639fab988df18a8011f41eacad73",  # WETH
        "0x0000000000000000000000000000000000000000",  # native ETH (zero address)
        "0x5fc5360d0400a0fd4f2af552add042d716f1d168",  # USDG
        # Tokenized stocks (NVDA, TTWO, ...) also appear as quote assets. They are RWAs:
        # bucketed via TEHscreener /rwa in the organic-filter step, not treated as quotes.
    },
}
