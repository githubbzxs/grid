from __future__ import annotations

import zlib

CLIENT_ORDER_PREFIX_MOD = 10_000
CLIENT_ORDER_BLOCK = 10_000
CLIENT_ORDER_OFFSET_ASK = 1_000
CLIENT_ORDER_OFFSET_BID = 2_000
CLIENT_ORDER_MAX = 281_474_976_710_655


def grid_prefix(account_index: int, market_id: int, symbol: str) -> int:
    raw = f"{account_index}:{market_id}:{symbol}".encode("utf-8")
    return zlib.crc32(raw) % CLIENT_ORDER_PREFIX_MOD


def grid_client_order_id(prefix: int, side: str, level: int) -> int:
    base = prefix * CLIENT_ORDER_BLOCK
    offset = CLIENT_ORDER_OFFSET_ASK if side == "ask" else CLIENT_ORDER_OFFSET_BID
    return base + offset + int(level)


def is_grid_client_order(prefix: int, client_order_index: int) -> bool:
    return int(client_order_index) // CLIENT_ORDER_BLOCK == int(prefix)

