from trench import evm_swaps as ev


def _w(*xs, bits=256):
    return "0x" + "".join(format(x % (1 << 256), "064x") for x in xs)


def _log(topics, data, addr="0xPool"):
    return {"address": addr, "topics": topics, "data": data, "blockNumber": "0x10",
            "blockTimestamp": "0x6553f100", "transactionHash": "0xABC", "logIndex": "0x1"}


def test_v2_trader_deltas():
    # trader pays 5 of token0, receives 7 of token1
    r = ev.decode(_log([ev.TOPIC_V2, "0x" + "0" * 24 + "aa" * 20, "0x" + "0" * 24 + "bb" * 20],
                       _w(5, 0, 0, 7)), "base")
    assert (r["d0"], r["d1"], r["kind"]) == ("-5", "7", "v2")
    assert r["recipient"] == "0x" + "bb" * 20 and r["tx_hash"] == "0xabc"


def test_v3_pool_perspective_is_flipped():
    # pool received 5 token0 (positive) and paid 7 token1 (negative)
    r = ev.decode(_log([ev.TOPIC_V3, "0x" + "0" * 64, "0x" + "0" * 64],
                       _w(5, -7, 1, 1, 1)), "base")
    assert (r["d0"], r["d1"]) == ("-5", "7")


def test_v4_swapper_perspective_kept_and_pool_id_from_topic():
    pid = "0x" + "12" * 32
    r = ev.decode(_log([ev.TOPIC_V4, pid, "0x" + "0" * 24 + "cc" * 20],
                       _w(-5, 7, 1, 1, 1, 3000)), "robinhood")
    assert (r["d0"], r["d1"], r["pool_id"], r["kind"]) == ("-5", "7", pid, "v4")
    assert r["block_timestamp"] == 0x6553F100


def test_unknown_topic_ignored():
    assert ev.decode(_log(["0x" + "ff" * 32], "0x"), "base") is None
