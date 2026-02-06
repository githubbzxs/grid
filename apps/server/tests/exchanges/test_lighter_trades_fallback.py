from __future__ import annotations

import asyncio

import pytest

from app.exchanges.lighter.trader import LighterTrader


class _FakeOrderApi:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.calls: list[dict] = []

    async def trades(self, **kwargs):
        self.calls.append(dict(kwargs))
        if len(self.calls) == 1:
            raise self.exc
        return {"trades": [], "next_cursor": None}


def _make_trader(api: _FakeOrderApi) -> LighterTrader:
    trader = object.__new__(LighterTrader)
    trader.account_index = 7
    trader._order_api = api
    trader._trades_with_account_index = True
    trader._log = lambda _: None

    async def _call_with_retry(func, **kwargs):
        return await func(**kwargs)

    trader._call_with_retry = _call_with_retry
    return trader


def test_fetch_trades_invalid_param_will_drop_account_index() -> None:
    api = _FakeOrderApi(RuntimeError("code=20001 message='invalid param '"))
    trader = _make_trader(api)

    result = asyncio.run(
        trader.fetch_trades(
            sort_by="timestamp",
            limit=50,
            market_id=0,
            sort_dir="desc",
            auth="token",
        )
    )

    assert result == {"trades": [], "next_cursor": None}
    assert len(api.calls) == 2
    assert api.calls[0].get("account_index") == 7
    assert "account_index" not in api.calls[1]
    assert trader._trades_with_account_index is False


def test_fetch_trades_non_invalid_param_error_keeps_account_index() -> None:
    api = _FakeOrderApi(RuntimeError("network timeout"))
    trader = _make_trader(api)

    with pytest.raises(RuntimeError, match="network timeout"):
        asyncio.run(
            trader.fetch_trades(
                sort_by="timestamp",
                limit=50,
                market_id=0,
                sort_dir="desc",
                auth="token",
            )
        )

    assert len(api.calls) == 1
    assert api.calls[0].get("account_index") == 7
    assert trader._trades_with_account_index is True
