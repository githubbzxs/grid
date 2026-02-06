from __future__ import annotations

import asyncio

from app.exchanges.paradex.trader import ParadexTrader


class _FakeMarketWs:
    def __init__(self, result=None, exc: Exception | None = None) -> None:
        self.result = result
        self.exc = exc
        self.calls = 0

    async def best_bid_ask(self, market: str):
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        return self.result


class _FakeApi:
    def __init__(self) -> None:
        self.calls = 0

    def fetch_bbo(self, market: str):
        self.calls += 1
        return {"bid": "200.1", "ask": "200.2"}


def _make_trader(ws_result=None, ws_exc: Exception | None = None):
    trader = object.__new__(ParadexTrader)
    trader._market_ws = _FakeMarketWs(result=ws_result, exc=ws_exc)
    trader._api = _FakeApi()
    return trader


def test_best_bid_ask_ws_first() -> None:
    trader = _make_trader(ws_result=(1, 2))
    bid, ask = asyncio.run(trader.best_bid_ask("ETH-USD-PERP"))
    assert bid == 1
    assert ask == 2
    assert trader._market_ws.calls == 1
    assert trader._api.calls == 0


def test_best_bid_ask_ws_empty_then_rest_fallback() -> None:
    trader = _make_trader(ws_result=(None, None))
    bid, ask = asyncio.run(trader.best_bid_ask("ETH-USD-PERP"))
    assert str(bid) == "200.1"
    assert str(ask) == "200.2"
    assert trader._market_ws.calls == 1
    assert trader._api.calls == 1


def test_best_bid_ask_ws_error_then_rest_fallback() -> None:
    trader = _make_trader(ws_exc=RuntimeError("ws down"))
    bid, ask = asyncio.run(trader.best_bid_ask("ETH-USD-PERP"))
    assert str(bid) == "200.1"
    assert str(ask) == "200.2"
    assert trader._market_ws.calls == 1
    assert trader._api.calls == 1
