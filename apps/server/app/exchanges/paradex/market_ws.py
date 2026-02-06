from __future__ import annotations

import asyncio
from contextlib import suppress
import logging
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple


def _parse_decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except Exception:
        return None


class ParadexMarketData:
    """使用 Paradex WS 订阅 BBO，失败时由上层回退 REST。"""

    def __init__(self, ws_client: Any, logger: Optional[logging.Logger] = None) -> None:
        self._ws_client = ws_client
        self._logger = logger or logging.getLogger(__name__)
        self._lock = asyncio.Lock()
        self._prices: Dict[str, Tuple[Optional[Decimal], Optional[Decimal]]] = {}
        self._events: Dict[str, asyncio.Event] = {}
        self._subscriptions: set[str] = set()
        self._connected = False

    async def _on_message(self, _ws_channel: Any, message: Dict[str, Any]) -> None:
        if not isinstance(message, dict):
            return
        params = message.get("params")
        if not isinstance(params, dict):
            return
        data = params.get("data")
        if not isinstance(data, dict):
            return
        channel = str(params.get("channel") or "")
        market = str(data.get("market") or "")
        if not market and channel.startswith("bbo."):
            market = channel.split(".", 1)[1]
        if not market:
            return
        bid = _parse_decimal(data.get("bid"))
        ask = _parse_decimal(data.get("ask"))
        if bid is None and ask is None:
            return
        self._prices[market] = (bid, ask)
        event = self._events.get(market)
        if event:
            event.set()

    async def _ensure_subscribed(self, market: str) -> None:
        if market in self._subscriptions:
            return
        if self._ws_client is None:
            return
        async with self._lock:
            if market in self._subscriptions:
                return
            if not self._connected:
                connected = await self._ws_client.connect()
                self._connected = bool(connected)
            if not self._connected:
                return
            from paradex_py.api.ws_client import ParadexWebsocketChannel

            self._events.setdefault(market, asyncio.Event())
            await self._ws_client.subscribe(
                channel=ParadexWebsocketChannel.BBO,
                callback=self._on_message,
                params={"market": market},
            )
            self._subscriptions.add(market)

    async def best_bid_ask(self, market: str) -> Tuple[Optional[Decimal], Optional[Decimal]]:
        market_key = str(market)
        await self._ensure_subscribed(market_key)
        event = self._events.get(market_key)
        if market_key not in self._prices and event is not None and not event.is_set():
            try:
                await asyncio.wait_for(event.wait(), timeout=1.0)
            except Exception:
                pass
        return self._prices.get(market_key, (None, None))

    async def close(self) -> None:
        if self._ws_client is None:
            return
        try:
            if self._subscriptions:
                for market in list(self._subscriptions):
                    with suppress(Exception):
                        await self._ws_client.unsubscribe_by_name(f"bbo.{market}")
        except Exception as exc:
            self._logger.debug("paradex.ws.unsubscribe.error err=%s:%s", type(exc).__name__, exc)
        self._subscriptions.clear()
