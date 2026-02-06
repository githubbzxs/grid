from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from app.exchanges.lighter.public_api import base_url


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


def _best_prices(order_book: Dict[str, Any]) -> Tuple[Optional[Decimal], Optional[Decimal]]:
    bids = order_book.get("bids") if isinstance(order_book, dict) else None
    asks = order_book.get("asks") if isinstance(order_book, dict) else None
    best_bid: Optional[Decimal] = None
    best_ask: Optional[Decimal] = None

    for item in bids or []:
        price = _parse_decimal(item.get("price") if isinstance(item, dict) else getattr(item, "price", None))
        if price is None:
            continue
        if best_bid is None or price > best_bid:
            best_bid = price

    for item in asks or []:
        price = _parse_decimal(item.get("price") if isinstance(item, dict) else getattr(item, "price", None))
        if price is None:
            continue
        if best_ask is None or price < best_ask:
            best_ask = price

    return best_bid, best_ask


@dataclass
class _WsStream:
    client: Any
    task: asyncio.Task[None]
    event: asyncio.Event


class LighterMarketData:
    """使用 Lighter WS 订阅盘口，失败时由上层回退 REST。"""

    def __init__(self, env: str, logger: Optional[logging.Logger] = None) -> None:
        self._env = env
        self._host = base_url(env).replace("https://", "").replace("http://", "")
        self._logger = logger or logging.getLogger(__name__)
        self._lock = asyncio.Lock()
        self._streams: Dict[int, _WsStream] = {}
        self._prices: Dict[int, Tuple[Optional[Decimal], Optional[Decimal]]] = {}

    def _on_order_book_update(self, market_id: Any, order_book: Dict[str, Any]) -> None:
        try:
            mid = int(str(market_id))
        except Exception:
            return
        bid, ask = _best_prices(order_book)
        if bid is None and ask is None:
            return
        self._prices[mid] = (bid, ask)
        stream = self._streams.get(mid)
        if stream:
            stream.event.set()

    async def _run_stream(self, market_id: int, ws_client: Any) -> None:
        try:
            await ws_client.run_async()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._logger.debug("lighter.ws.stream.error market_id=%s err=%s:%s", market_id, type(exc).__name__, exc)

    async def _ensure_stream(self, market_id: int) -> _WsStream:
        current = self._streams.get(market_id)
        if current and not current.task.done():
            return current

        async with self._lock:
            current = self._streams.get(market_id)
            if current and not current.task.done():
                return current

            import lighter

            event = asyncio.Event()
            ws_client = lighter.WsClient(
                host=self._host,
                order_book_ids=[int(market_id)],
                on_order_book_update=self._on_order_book_update,
                on_account_update=None,
            )
            task = asyncio.create_task(self._run_stream(int(market_id), ws_client))
            stream = _WsStream(client=ws_client, task=task, event=event)
            self._streams[int(market_id)] = stream
            return stream

    async def best_bid_ask(self, market_id: int) -> Tuple[Optional[Decimal], Optional[Decimal]]:
        mid = int(market_id)
        stream = await self._ensure_stream(mid)
        if mid not in self._prices and not stream.event.is_set():
            try:
                await asyncio.wait_for(stream.event.wait(), timeout=1.0)
            except Exception:
                pass
        return self._prices.get(mid, (None, None))

    async def close(self) -> None:
        streams = list(self._streams.values())
        self._streams.clear()
        for stream in streams:
            stream.task.cancel()
        for stream in streams:
            ws = getattr(stream.client, "ws", None)
            if ws is None:
                continue
            close_fn = getattr(ws, "close", None)
            if close_fn is None:
                continue
            try:
                result = close_fn()
                if inspect.isawaitable(result):
                    await result
            except Exception:
                continue
        if streams:
            await asyncio.gather(*(s.task for s in streams), return_exceptions=True)
