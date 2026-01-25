from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol, Tuple


@dataclass
class MarketMeta:
    market_id: str | int
    symbol: str
    size_decimals: int
    price_decimals: int
    min_base_amount: Decimal
    min_quote_amount: Decimal


class Trader(Protocol):
    env: str
    account_key: str | int

    def check_client(self) -> str | None: ...

    async def close(self) -> None: ...

    async def market_meta(self, market_id: str | int) -> MarketMeta: ...

    async def best_bid_ask(self, market_id: str | int) -> Tuple[Decimal | None, Decimal | None]: ...

    async def active_orders(self, market_id: str | int) -> list[Any]: ...

    async def create_limit_order(
        self,
        market_id: str | int,
        client_order_index: int,
        base_amount: int,
        price: int,
        is_ask: bool,
        post_only: bool = True,
        reduce_only: bool = False,
    ) -> None: ...

    async def cancel_order(self, market_id: str | int, order_index: Any) -> None: ...
