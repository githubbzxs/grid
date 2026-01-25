from __future__ import annotations

import asyncio
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from app.exchanges.types import MarketMeta


def _env_value(env: str) -> str:
    return "testnet" if env == "testnet" else "prod"


def _decimals_from_step(step: Any) -> int:
    try:
        d = Decimal(str(step))
    except Exception:
        return 0
    return max(0, -d.as_tuple().exponent)


def _safe_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(0)


class ParadexTrader:
    def __init__(
        self,
        env: str,
        l1_address: Optional[str],
        l1_private_key: Optional[str],
        l2_address: Optional[str],
        l2_private_key: Optional[str],
    ) -> None:
        from paradex_py import Paradex, ParadexSubkey

        self.env = env
        self._env = _env_value(env)
        self._market_cache: Dict[str, MarketMeta] = {}

        if l2_private_key and l2_address:
            self._client = ParadexSubkey(env=self._env, l2_private_key=l2_private_key, l2_address=l2_address)
            self.account_key = l2_address
        elif l1_address and l1_private_key:
            self._client = Paradex(env=self._env, l1_address=l1_address, l1_private_key=l1_private_key)
            self.account_key = l1_address
        else:
            raise ValueError("缺少 Paradex 凭据")

        self._api = self._client.api_client
        self._positions_lock = asyncio.Lock()
        self._positions_cached_at = 0.0
        self._positions_cache: Dict[str, Decimal] = {}
        self._positions_ttl_s = 2.0

    def check_client(self) -> Optional[str]:
        try:
            self._api.fetch_account_summary()
        except Exception as exc:
            return f"{type(exc).__name__}:{exc}"
        return None

    async def close(self) -> None:
        await self._client.close()

    async def market_meta(self, market_id: str | int) -> MarketMeta:
        market = str(market_id)
        cached = self._market_cache.get(market)
        if cached:
            return cached

        data = self._api.fetch_markets({"market": market})
        items = list(data.get("results") or [])
        if not items:
            data = self._api.fetch_markets()
            items = list(data.get("results") or [])

        target = None
        for item in items:
            if str(item.get("symbol") or "") == market:
                target = item
                break
        if target is None:
            raise KeyError(f"未知 market: {market}")

        price_step = target.get("price_tick_size") or "0"
        size_step = target.get("order_size_increment") or "0"
        meta = MarketMeta(
            market_id=market,
            symbol=str(target.get("symbol") or market),
            size_decimals=_decimals_from_step(size_step),
            price_decimals=_decimals_from_step(price_step),
            min_base_amount=_safe_decimal(size_step),
            min_quote_amount=_safe_decimal(target.get("min_notional") or 0),
        )
        self._market_cache[market] = meta
        return meta

    async def best_bid_ask(self, market_id: str | int) -> Tuple[Optional[Decimal], Optional[Decimal]]:
        market = str(market_id)
        data = self._api.fetch_bbo(market)
        bid = data.get("bid")
        ask = data.get("ask")
        bid_v = _safe_decimal(bid) if bid is not None else None
        ask_v = _safe_decimal(ask) if ask is not None else None
        return bid_v, ask_v

    async def active_orders(self, market_id: str | int) -> List[Any]:
        market = str(market_id)
        data = self._api.fetch_orders({"market": market})
        return list(data.get("results") or [])

    async def position_base(self, market_id: str | int) -> Decimal:
        market = str(market_id)
        now = time.time()
        if (now - self._positions_cached_at) < self._positions_ttl_s:
            return self._positions_cache.get(market, Decimal(0))

        async with self._positions_lock:
            now = time.time()
            if (now - self._positions_cached_at) < self._positions_ttl_s:
                return self._positions_cache.get(market, Decimal(0))

            data = self._api.fetch_positions()
            results = list(data.get("results") or [])
            cache: Dict[str, Decimal] = {}
            for item in results:
                if not isinstance(item, dict):
                    continue
                mkt = str(item.get("market") or "")
                if not mkt:
                    continue
                size = _safe_decimal(item.get("size") or 0)
                cache[mkt] = size

            self._positions_cache = cache
            self._positions_cached_at = now
            return cache.get(market, Decimal(0))

    async def create_limit_order(
        self,
        market_id: str | int,
        client_order_index: int,
        base_amount: int,
        price: int,
        is_ask: bool,
        post_only: bool = True,
        reduce_only: bool = False,
    ) -> None:
        from paradex_py.common.order import Order, OrderSide, OrderType

        meta = await self.market_meta(market_id)
        price_dec = Decimal(int(price)) / (Decimal(10) ** int(meta.price_decimals))
        size_dec = Decimal(int(base_amount)) / (Decimal(10) ** int(meta.size_decimals))
        instruction = "POST_ONLY" if post_only else "GTC"
        side = OrderSide.Sell if is_ask else OrderSide.Buy
        order = Order(
            market=str(market_id),
            order_type=OrderType.Limit,
            order_side=side,
            size=size_dec,
            limit_price=price_dec,
            client_id=str(client_order_index),
            instruction=instruction,
            reduce_only=reduce_only,
        )
        self._api.submit_order(order)

    async def create_market_order(
        self,
        market_id: str | int,
        base_amount: int,
        is_ask: bool,
        reduce_only: bool = False,
    ) -> None:
        from paradex_py.common.order import Order, OrderSide, OrderType

        meta = await self.market_meta(market_id)
        size_dec = Decimal(int(base_amount)) / (Decimal(10) ** int(meta.size_decimals))
        side = OrderSide.Sell if is_ask else OrderSide.Buy
        order_type = getattr(OrderType, "Market", None) or getattr(OrderType, "MARKET", None)
        if order_type is None:
            raise RuntimeError("未找到市价单类型")

        order_kwargs = {
            "market": str(market_id),
            "order_type": order_type,
            "order_side": side,
            "size": size_dec,
            "client_id": str(int(time.time() * 1000)),
            "reduce_only": reduce_only,
        }
        try:
            order = Order(**order_kwargs)
        except TypeError:
            order_kwargs["instruction"] = "IOC"
            order = Order(**order_kwargs)
        self._api.submit_order(order)

    async def cancel_order(self, market_id: str | int, order_index: Any) -> None:
        self._api.cancel_order(str(order_index))
