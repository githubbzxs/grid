from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.exchanges.lighter.trader import LighterTrader


class _FakeMarketWs:
    def __init__(self, result=None, exc: Exception | None = None) -> None:
        self.result = result
        self.exc = exc
        self.calls = 0

    async def best_bid_ask(self, market_id: int):
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        return self.result


class _FakeOrderApi:
    def __init__(self) -> None:
        self.calls = 0

    async def order_book_orders(self, market_id: int, limit: int):
        self.calls += 1
        return SimpleNamespace(
            bids=[SimpleNamespace(price="100.1")],
            asks=[SimpleNamespace(price="100.2")],
        )


def _make_trader(ws_result=None, ws_exc: Exception | None = None):
    trader = object.__new__(LighterTrader)
    trader._market_ws = _FakeMarketWs(result=ws_result, exc=ws_exc)
    trader._order_api = _FakeOrderApi()
    trader._log = lambda _text: None

    async def _call_with_retry(func, **kwargs):
        return await func(**kwargs)

    trader._call_with_retry = _call_with_retry
    return trader


def test_best_bid_ask_ws_first() -> None:
    trader = _make_trader(ws_result=(1, 2))
    bid, ask = asyncio.run(trader.best_bid_ask(7))
    assert bid == 1
    assert ask == 2
    assert trader._market_ws.calls == 1
    assert trader._order_api.calls == 0


def test_best_bid_ask_ws_empty_then_rest_fallback() -> None:
    trader = _make_trader(ws_result=(None, None))
    bid, ask = asyncio.run(trader.best_bid_ask(7))
    assert str(bid) == "100.1"
    assert str(ask) == "100.2"
    assert trader._market_ws.calls == 1
    assert trader._order_api.calls == 1


def test_best_bid_ask_ws_error_then_rest_fallback() -> None:
    trader = _make_trader(ws_exc=RuntimeError("ws down"))
    bid, ask = asyncio.run(trader.best_bid_ask(7))
    assert str(bid) == "100.1"
    assert str(ask) == "100.2"
    assert trader._market_ws.calls == 1
    assert trader._order_api.calls == 1
