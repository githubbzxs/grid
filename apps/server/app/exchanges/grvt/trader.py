from __future__ import annotations

import time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from app.exchanges.grvt.market_ws import GrvtMarketData, _parse_price
from app.exchanges.types import MarketMeta


def _env_value(env: str):
    from pysdk.grvt_ccxt_env import GrvtEnv

    name = str(env or "").strip().lower()
    if name in {"testnet", "test"}:
        return GrvtEnv.TESTNET
    if name in {"staging", "stage"}:
        return GrvtEnv.STAGING
    if name in {"dev", "development"}:
        return GrvtEnv.DEV
    if name in {"mainnet", "prod", "production"}:
        return GrvtEnv.PROD
    return GrvtEnv.PROD


def _decimals_from_step(step: Any) -> int:
    try:
        d = Decimal(str(step))
    except Exception:
        return 0
    if d <= 0:
        return 0
    return max(0, -d.as_tuple().exponent)


def _safe_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(0)


def _trade_ts_ms(value: Any) -> Optional[int]:
    try:
        ts = int(value)
    except Exception:
        return None
    if ts > 10_000_000_000_000:
        return ts // 1_000_000
    if ts > 10_000_000_000:
        return ts
    return ts * 1000


class GrvtTrader:
    def __init__(
        self,
        env: str,
        trading_account_id: str,
        api_key: str,
        private_key: str,
    ) -> None:
        from pysdk.grvt_ccxt_pro import GrvtCcxtPro

        self.env = env
        self.account_key = str(trading_account_id)
        self._api = GrvtCcxtPro(
            env=_env_value(env),
            parameters={
                "trading_account_id": str(trading_account_id),
                "api_key": str(api_key),
                "private_key": str(private_key),
            },
        )
        self._market_cache: Dict[str, MarketMeta] = {}
        self._positions_cache: Dict[str, Decimal] = {}
        self._positions_cached_at = 0.0
        self._positions_ttl_s = 2.0
        self._market_ws = GrvtMarketData(env)

    def check_client(self) -> Optional[str]:
        return None

    async def verify(self) -> Optional[str]:
        try:
            await self._api.get_account_summary()
        except Exception as exc:
            return f"{type(exc).__name__}:{exc}"
        return None

    async def close(self) -> None:
        await self._market_ws.close()
        await self._api._session.close()

    async def market_meta(self, market_id: str | int) -> MarketMeta:
        symbol = str(market_id)
        cached = self._market_cache.get(symbol)
        if cached:
            return cached

        if not self._api.markets:
            await self._api.load_markets()
        item = self._api.markets.get(symbol)
        if not item:
            raise KeyError(f"未知 instrument: {symbol}")

        tick_size = item.get("tick_size") or "0"
        base_decimals = int(item.get("base_decimals") or 0)
        size_decimals = max(0, int(base_decimals))
        price_decimals = _decimals_from_step(tick_size)
        min_size = _safe_decimal(item.get("min_size") or 0)
        min_quote = Decimal(0)
        if min_size > 0:
            try:
                min_quote = min_size * _safe_decimal(tick_size)
            except Exception:
                min_quote = Decimal(0)

        meta = MarketMeta(
            market_id=symbol,
            symbol=symbol,
            size_decimals=size_decimals,
            price_decimals=price_decimals,
            min_base_amount=min_size,
            min_quote_amount=min_quote,
        )
        self._market_cache[symbol] = meta
        return meta

    async def best_bid_ask(self, market_id: str | int) -> Tuple[Optional[Decimal], Optional[Decimal]]:
        instrument = str(market_id)
        bid, ask = await self._market_ws.best_bid_ask(instrument)
        if bid is not None or ask is not None:
            return bid, ask
        try:
            data = await self._api.fetch_mini_ticker(instrument)
            bid = _parse_price(data.get("best_bid_price") or data.get("bestBidPrice"))
            ask = _parse_price(data.get("best_ask_price") or data.get("bestAskPrice"))
            return bid, ask
        except Exception:
            return None, None

    async def active_orders(self, market_id: str | int) -> List[Any]:
        symbol = str(market_id)
        orders = await self._api.fetch_open_orders(symbol)
        results: List[Any] = []
        for order in orders or []:
            if not isinstance(order, dict):
                results.append(order)
                continue
            meta = order.get("metadata") if isinstance(order.get("metadata"), dict) else {}
            if meta and meta.get("client_order_id") is not None:
                order["client_order_id"] = meta.get("client_order_id")
            legs = order.get("legs") if isinstance(order.get("legs"), list) else []
            if legs:
                leg = legs[0] if isinstance(legs[0], dict) else {}
                if leg and leg.get("limit_price") is not None:
                    order["price"] = leg.get("limit_price")
            results.append(order)
        return results

    async def position_base(self, market_id: str | int) -> Decimal:
        symbol = str(market_id)
        now = time.time()
        if (now - self._positions_cached_at) < self._positions_ttl_s:
            return self._positions_cache.get(symbol, Decimal(0))

        positions = await self._api.fetch_positions([symbol])
        cache: Dict[str, Decimal] = {}
        for item in positions or []:
            if not isinstance(item, dict):
                continue
            inst = str(item.get("instrument") or "")
            if not inst:
                continue
            cache[inst] = _safe_decimal(item.get("size") or 0)

        self._positions_cache = cache
        self._positions_cached_at = now
        return cache.get(symbol, Decimal(0))

    async def positions_snapshot(self) -> Dict[str, Dict[str, Decimal]]:
        positions = await self._api.fetch_positions()
        result: Dict[str, Dict[str, Decimal]] = {}
        for item in positions or []:
            if not isinstance(item, dict):
                continue
            inst = str(item.get("instrument") or "")
            if not inst:
                continue
            base = _safe_decimal(item.get("size") or 0)
            total_pnl = item.get("total_pnl")
            if total_pnl is None:
                total_pnl = _safe_decimal(item.get("realized_pnl") or 0) + _safe_decimal(
                    item.get("unrealized_pnl") or 0
                )
            pnl = _safe_decimal(total_pnl)
            result[inst] = {"base": base, "pnl": pnl}
        return result

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
        meta = await self.market_meta(market_id)
        size_dec = Decimal(int(base_amount)) / (Decimal(10) ** int(meta.size_decimals))
        price_dec = Decimal(int(price)) / (Decimal(10) ** int(meta.price_decimals))
        params = {
            "client_order_id": str(client_order_index),
            "post_only": bool(post_only),
            "reduce_only": bool(reduce_only),
        }
        await self._api.create_order(
            symbol=str(market_id),
            order_type="limit",
            side="sell" if is_ask else "buy",
            amount=str(size_dec),
            price=str(price_dec),
            params=params,
        )

    async def create_market_order(
        self,
        market_id: str | int,
        base_amount: int,
        is_ask: bool,
        reduce_only: bool = False,
    ) -> None:
        meta = await self.market_meta(market_id)
        size_dec = Decimal(int(base_amount)) / (Decimal(10) ** int(meta.size_decimals))
        params = {
            "post_only": False,
            "reduce_only": bool(reduce_only),
        }
        await self._api.create_order(
            symbol=str(market_id),
            order_type="market",
            side="sell" if is_ask else "buy",
            amount=str(size_dec),
            price=None,
            params=params,
        )

    async def fills_since(
        self,
        market_id: str | int,
        start_ms: int,
        end_ms: int,
        max_pages: int = 5,
    ) -> Tuple[Decimal, int]:
        total = Decimal(0)
        count = 0
        cursor = None
        pages = 0
        start_ns = int(start_ms) * 1_000_000
        end_ns = int(end_ms) * 1_000_000
        symbol = str(market_id)

        while pages < max_pages:
            params: Dict[str, Any] = {"end_time": end_ns}
            if cursor:
                params = {"cursor": cursor}
            resp = await self._api.fetch_my_trades(symbol=symbol, since=start_ns, limit=200, params=params)
            results = resp.get("result") if isinstance(resp, dict) else None
            results = results or []
            for item in results:
                if not isinstance(item, dict):
                    continue
                ts_ms = _trade_ts_ms(item.get("event_time") or item.get("timestamp") or item.get("time"))
                if ts_ms is not None and (ts_ms < start_ms or ts_ms > end_ms):
                    continue
                price = _parse_price(item.get("price") or item.get("fill_price"))
                if price is None:
                    price = _safe_decimal(item.get("price") or 0)
                size = _safe_decimal(item.get("size") or item.get("amount") or 0)
                total += abs(price * size)
                count += 1

            cursor = resp.get("next") if isinstance(resp, dict) else None
            if not cursor:
                cursor = resp.get("next_cursor") if isinstance(resp, dict) else None
            if not cursor:
                break
            pages += 1
        return total, count

    async def cancel_order(self, market_id: str | int, order_index: Any) -> None:
        order_id = str(order_index)
        await self._api.cancel_order(id=order_id)
