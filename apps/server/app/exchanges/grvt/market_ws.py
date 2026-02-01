from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import Dict, Optional, Tuple


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


def _parse_price(value: Optional[str | int | float | Decimal]) -> Optional[Decimal]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        num = Decimal(text)
    except Exception:
        return None
    if "." in text:
        return num
    return num / Decimal(1_000_000_000)


class GrvtMarketData:
    """使用 WS 获取 GRVT 行情。"""

    def __init__(self, env: str, logger: Optional[logging.Logger] = None) -> None:
        self._env_name = env
        self._logger = logger or logging.getLogger(__name__)
        self._ws = None
        self._ready = False
        self._lock = asyncio.Lock()
        self._prices: Dict[str, Tuple[Optional[Decimal], Optional[Decimal]]] = {}
        self._events: Dict[str, asyncio.Event] = {}
        self._subscriptions: set[str] = set()

    async def _ensure_ws(self) -> None:
        if self._ready:
            return
        async with self._lock:
            if self._ready:
                return
            from pysdk.grvt_ccxt_ws import GrvtCcxtWS

            self._ws = GrvtCcxtWS(
                env=_env_value(self._env_name),
                loop=asyncio.get_running_loop(),
                logger=self._logger,
                parameters={},
            )
            await self._ws.initialize()
            self._ready = True

    async def _subscribe_mini(self, instrument: str) -> None:
        if instrument in self._subscriptions:
            return
        await self._ensure_ws()
        event = asyncio.Event()
        self._events[instrument] = event

        async def _handler(message: dict) -> None:
            feed = message.get("feed") if isinstance(message, dict) else None
            if not isinstance(feed, dict):
                return
            instrument_key = str(feed.get("instrument") or "").strip()
            if not instrument_key:
                selector = str(message.get("selector") or "")
                instrument_key = selector.split("@")[0] if selector else ""
            if not instrument_key:
                instrument_key = instrument
            bid = _parse_price(feed.get("best_bid_price") or feed.get("bestBidPrice"))
            ask = _parse_price(feed.get("best_ask_price") or feed.get("bestAskPrice"))
            if bid is None and ask is None:
                return
            self._prices[instrument_key] = (bid, ask)
            if instrument_key in self._events:
                self._events[instrument_key].set()

        await self._ws.subscribe(
            "mini.s",
            _handler,
            params={"instrument": instrument, "rate": 500},
        )
        self._subscriptions.add(instrument)

    async def best_bid_ask(self, instrument: str) -> Tuple[Optional[Decimal], Optional[Decimal]]:
        await self._subscribe_mini(instrument)
        event = self._events.get(instrument)
        if event and not event.is_set():
            try:
                await asyncio.wait_for(event.wait(), timeout=1.0)
            except Exception:
                pass
        return self._prices.get(instrument, (None, None))

    async def close(self) -> None:
        if not self._ws:
            return
        try:
            for endpoint in getattr(self._ws, "endpoint_types", []) or []:
                try:
                    await self._ws._close_connection(endpoint)
                except Exception:
                    continue
        finally:
            try:
                await self._ws._session.close()
            except Exception:
                pass
