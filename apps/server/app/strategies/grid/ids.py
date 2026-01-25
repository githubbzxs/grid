from __future__ import annotations

import zlib

CLIENT_ORDER_PREFIX_MOD = 10_000
CLIENT_ORDER_BLOCK = 10_000
CLIENT_ORDER_OFFSET_ASK = 1_000
CLIENT_ORDER_OFFSET_BID = 6_000
MAX_LEVEL_PER_SIDE = 3_999
CLIENT_ORDER_MAX = 281_474_976_710_655


def grid_prefix(account_key: str | int, market_id: str | int, symbol: str) -> int:
    raw = f"{account_key}:{market_id}:{symbol}".encode("utf-8")
    return zlib.crc32(raw) % CLIENT_ORDER_PREFIX_MOD


def grid_client_order_id(prefix: int, side: str, level: int) -> int:
    base = prefix * CLIENT_ORDER_BLOCK
    offset = CLIENT_ORDER_OFFSET_ASK if side == "ask" else CLIENT_ORDER_OFFSET_BID
    return base + offset + int(level)


def is_grid_client_order(prefix: int, client_order_index: int) -> bool:
    try:
        cid = int(client_order_index)
    except Exception:
        return False
    return cid // CLIENT_ORDER_BLOCK == int(prefix)


def grid_client_order_side_level(client_order_index: int) -> tuple[str, int] | None:
    within = int(client_order_index) % CLIENT_ORDER_BLOCK
    if within >= CLIENT_ORDER_OFFSET_BID:
        level = within - CLIENT_ORDER_OFFSET_BID
        if 1 <= level <= MAX_LEVEL_PER_SIDE:
            return "bid", level
        return None
    if within >= CLIENT_ORDER_OFFSET_ASK:
        level = within - CLIENT_ORDER_OFFSET_ASK
        if 1 <= level <= MAX_LEVEL_PER_SIDE:
            return "ask", level
        return None
    return None
