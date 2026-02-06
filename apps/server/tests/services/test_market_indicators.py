from __future__ import annotations

import asyncio
import time
from decimal import Decimal

from app.core.logbus import LogBus
from app.services.market_indicators import MarketIndicator, TradingViewIndicatorService


def test_fetch_sync_choose_higher_priority_source(monkeypatch) -> None:
    service = TradingViewIndicatorService(LogBus(), cache_ttl_s=0)

    def fake_post_scan(_payload):
        return {
            "data": [
                {"s": "BYBIT:ETHUSDT.P", "d": [Decimal("11.1"), Decimal("22.2")]},
                {"s": "BINANCE:ETHUSDT", "d": [Decimal("1.1"), Decimal("2.2")]},
            ]
        }

    monkeypatch.setattr(service, "_post_scan", fake_post_scan)
    result = service._fetch_sync(["ETH"])
    assert "ETH" in result
    assert result["ETH"].atr == Decimal("1.1")
    assert result["ETH"].adx == Decimal("2.2")


def test_fetch_use_recent_cache_when_not_expired(monkeypatch) -> None:
    service = TradingViewIndicatorService(LogBus(), cache_ttl_s=60)
    service._cache["BTC"] = (time.time(), MarketIndicator(atr=Decimal("9.9"), adx=Decimal("8.8")))

    def fake_fetch_sync(_symbols):
        raise AssertionError("缓存未过期时不应触发远程请求")

    monkeypatch.setattr(service, "_fetch_sync", fake_fetch_sync)
    result = asyncio.run(service.fetch(["BTC"]))
    assert "BTC" in result
    assert result["BTC"].atr == Decimal("9.9")
    assert result["BTC"].adx == Decimal("8.8")
