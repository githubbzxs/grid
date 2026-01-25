from __future__ import annotations

import asyncio
import time
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

from app.exchanges.lighter.public_api import base_url
from app.exchanges.types import MarketMeta


def _parse_auth_expiry(auth_token: str) -> Optional[int]:
    try:
        first = auth_token.split(":", 1)[0]
        return int(first)
    except Exception:
        return None


class LighterTrader:
    def __init__(
        self,
        env: str,
        account_index: int,
        api_key_index: int,
        api_private_key: str,
    ) -> None:
        import lighter

        self.env = env
        self.url = base_url(env)
        self.account_index = int(account_index)
        self.api_key_index = int(api_key_index)
        self.account_key = self.account_index

        self._nonce_lock = asyncio.Lock()
        self._signer = lighter.SignerClient(
            url=self.url,
            account_index=self.account_index,
            api_private_keys={self.api_key_index: str(api_private_key)},
        )
        self._order_api = self._signer.order_api
        self._account_api = lighter.AccountApi(self._signer.api_client)

        self._auth_token: Optional[str] = None
        self._auth_expiry_unix: int = 0
        self._market_cache: Dict[int, MarketMeta] = {}
        self._positions_lock = asyncio.Lock()
        self._positions_cached_at = 0.0
        self._positions_cache: Dict[int, Decimal] = {}
        self._positions_ttl_s = 2.0

    def check_client(self) -> Optional[str]:
        return self._signer.check_client()

    async def close(self) -> None:
        await self._signer.close()

    async def auth_token(self) -> str:
        now = int(time.time())
        if self._auth_token and (self._auth_expiry_unix - now) > 60:
            return self._auth_token

        token, err = self._signer.create_auth_token_with_expiry(deadline=60 * 60, api_key_index=self.api_key_index)
        if err or not token:
            raise RuntimeError(err or "auth token 为空")

        expiry = _parse_auth_expiry(token) or (now + 60 * 60)
        self._auth_token = token
        self._auth_expiry_unix = expiry
        return token

    async def market_meta(self, market_id: int) -> MarketMeta:
        market_id = int(market_id)
        cached = self._market_cache.get(market_id)
        if cached:
            return cached

        resp = await self._order_api.order_books()
        for ob in getattr(resp, "order_books", []) or []:
            if getattr(ob, "market_type", "") != "perp":
                continue
            if int(getattr(ob, "market_id", -1)) != market_id:
                continue
            meta = MarketMeta(
                market_id=market_id,
                symbol=str(getattr(ob, "symbol", "")),
                size_decimals=int(getattr(ob, "supported_size_decimals", 0)),
                price_decimals=int(getattr(ob, "supported_price_decimals", 0)),
                min_base_amount=Decimal(str(getattr(ob, "min_base_amount", "0"))),
                min_quote_amount=Decimal(str(getattr(ob, "min_quote_amount", "0"))),
            )
            self._market_cache[market_id] = meta
            return meta

        raise KeyError(f"未知 market_id: {market_id}")

    async def best_bid_ask(self, market_id: int) -> Tuple[Optional[Decimal], Optional[Decimal]]:
        resp = await self._order_api.order_book_orders(market_id=int(market_id), limit=1)
        bids = getattr(resp, "bids", []) or []
        asks = getattr(resp, "asks", []) or []
        bid = Decimal(str(getattr(bids[0], "price"))) if bids else None
        ask = Decimal(str(getattr(asks[0], "price"))) if asks else None
        return bid, ask

    async def active_orders(self, market_id: int) -> List[Any]:
        token = await self.auth_token()
        resp = await self._order_api.account_active_orders(
            account_index=self.account_index,
            market_id=int(market_id),
            auth=token,
        )
        return list(getattr(resp, "orders", []) or [])

    async def position_base(self, market_id: int) -> Decimal:
        market_id = int(market_id)
        now = time.time()
        if (now - self._positions_cached_at) < self._positions_ttl_s:
            return self._positions_cache.get(market_id, Decimal(0))

        async with self._positions_lock:
            now = time.time()
            if (now - self._positions_cached_at) < self._positions_ttl_s:
                return self._positions_cache.get(market_id, Decimal(0))

            resp = await self._account_api.account(by="index", value=str(int(self.account_index)))
            if hasattr(resp, "model_dump"):
                data = resp.model_dump()
            elif hasattr(resp, "to_dict"):
                data = resp.to_dict()
            else:
                data = getattr(resp, "__dict__", {})

            positions = []
            if isinstance(data, dict):
                accounts = data.get("accounts")
                if isinstance(accounts, list) and accounts:
                    first = accounts[0] or {}
                    if isinstance(first, dict):
                        positions = first.get("positions") or []
                elif isinstance(data.get("positions"), list):
                    positions = data.get("positions") or []

            cache: Dict[int, Decimal] = {}
            for pos in positions or []:
                if not isinstance(pos, dict):
                    continue
                mid = pos.get("market_id")
                if not isinstance(mid, int):
                    try:
                        mid = int(str(mid))
                    except Exception:
                        continue
                sign = pos.get("sign", 1)
                try:
                    sign_v = int(sign) if int(sign) != 0 else 1
                except Exception:
                    sign_v = 1
                qty = Decimal(str(pos.get("position") or "0"))
                cache[mid] = qty * Decimal(sign_v)

            self._positions_cache = cache
            self._positions_cached_at = now
            return cache.get(market_id, Decimal(0))

    async def create_limit_order(
        self,
        market_id: int,
        client_order_index: int,
        base_amount: int,
        price: int,
        is_ask: bool,
        post_only: bool = True,
        reduce_only: bool = False,
    ) -> None:
        tif = self._signer.ORDER_TIME_IN_FORCE_POST_ONLY if post_only else self._signer.ORDER_TIME_IN_FORCE_GOOD_TILL_TIME
        async with self._nonce_lock:
            _, resp, err = await self._signer.create_order(
                market_index=int(market_id),
                client_order_index=int(client_order_index),
                base_amount=int(base_amount),
                price=int(price),
                is_ask=bool(is_ask),
                order_type=self._signer.ORDER_TYPE_LIMIT,
                time_in_force=tif,
                reduce_only=bool(reduce_only),
            )
        if err is not None:
            raise RuntimeError(err)
        if getattr(resp, "code", 0) not in (0, 200):
            raise RuntimeError(f"send_tx code={getattr(resp, 'code', None)} msg={getattr(resp, 'message', None)}")

    async def create_market_order(
        self,
        market_id: int,
        base_amount: int,
        is_ask: bool,
        reduce_only: bool = False,
    ) -> None:
        meta = await self.market_meta(market_id)
        bid, ask = await self.best_bid_ask(market_id)
        if bid is None and ask is None:
            raise RuntimeError("无法获取盘口")
        if bid is None:
            avg_price = ask
        elif ask is None:
            avg_price = bid
        else:
            avg_price = (bid + ask) / 2
        q = Decimal(1) / (Decimal(10) ** int(meta.price_decimals))
        price_q = Decimal(str(avg_price)).quantize(q, rounding=ROUND_HALF_UP)
        price_int = int(price_q * (Decimal(10) ** int(meta.price_decimals)))
        async with self._nonce_lock:
            _, resp, err = await self._signer.create_market_order(
                market_index=int(market_id),
                client_order_index=0,
                base_amount=int(base_amount),
                avg_execution_price=int(price_int),
                is_ask=bool(is_ask),
                reduce_only=bool(reduce_only),
            )
        if err is not None:
            raise RuntimeError(err)
        if getattr(resp, "code", 0) not in (0, 200):
            raise RuntimeError(f"send_tx code={getattr(resp, 'code', None)} msg={getattr(resp, 'message', None)}")

    async def cancel_order(self, market_id: int, order_index: int) -> None:
        async with self._nonce_lock:
            _, resp, err = await self._signer.cancel_order(
                market_index=int(market_id),
                order_index=int(order_index),
            )
        if err is not None:
            raise RuntimeError(err)
        if getattr(resp, "code", 0) not in (0, 200):
            raise RuntimeError(f"send_tx code={getattr(resp, 'code', None)} msg={getattr(resp, 'message', None)}")
