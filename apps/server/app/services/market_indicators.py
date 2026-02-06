from __future__ import annotations

import asyncio
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Iterable, Optional

from app.core.logbus import LogBus


@dataclass(frozen=True)
class MarketIndicator:
    atr: Decimal
    adx: Decimal


class TradingViewIndicatorService:
    def __init__(
        self,
        logbus: LogBus,
        interval: str = "15",
        cache_ttl_s: float = 10.0,
        timeout_s: float = 8.0,
    ) -> None:
        self._logbus = logbus
        self._interval = str(interval or "15")
        self._cache_ttl_s = float(cache_ttl_s)
        self._timeout_s = float(timeout_s)
        self._cache: Dict[str, tuple[float, MarketIndicator]] = {}
        self._url = "https://scanner.tradingview.com/crypto/scan"
        self._last_error_log_ms = 0

    async def fetch(self, symbols: Iterable[str]) -> Dict[str, MarketIndicator]:
        normalized = sorted({self._normalize_symbol(s) for s in symbols if self._normalize_symbol(s)})
        if not normalized:
            return {}

        now = time.time()
        result: Dict[str, MarketIndicator] = {}
        stale: list[str] = []
        for symbol in normalized:
            cached = self._cache.get(symbol)
            if cached and (now - cached[0]) < self._cache_ttl_s:
                result[symbol] = cached[1]
            else:
                stale.append(symbol)

        if not stale:
            return result

        fresh: Dict[str, MarketIndicator] = {}
        try:
            fresh = await asyncio.to_thread(self._fetch_sync, stale)
        except Exception as exc:
            self._log_error_once(f"market.indicator.error err={type(exc).__name__}:{exc}")

        now2 = time.time()
        for symbol, indicator in fresh.items():
            self._cache[symbol] = (now2, indicator)
            result[symbol] = indicator

        for symbol in stale:
            if symbol in result:
                continue
            cached = self._cache.get(symbol)
            if cached:
                result[symbol] = cached[1]
        return result

    def _fetch_sync(self, symbols: list[str]) -> Dict[str, MarketIndicator]:
        tickers: list[str] = []
        ticker_map: Dict[str, tuple[str, int]] = {}
        for symbol in symbols:
            for priority, ticker in enumerate(self._candidate_tickers(symbol)):
                if ticker in ticker_map:
                    continue
                ticker_map[ticker] = (symbol, priority)
                tickers.append(ticker)
        if not tickers:
            return {}

        payload = {
            "symbols": {"tickers": tickers, "query": {"types": []}},
            "columns": [f"ATR|{self._interval}", f"ADX|{self._interval}"],
        }
        raw = self._post_scan(payload)
        rows = raw.get("data") or []

        picked: Dict[str, tuple[int, MarketIndicator]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            ticker = str(row.get("s") or "")
            mapping = ticker_map.get(ticker)
            if mapping is None:
                continue
            values = row.get("d")
            if not isinstance(values, list) or len(values) < 2:
                continue
            atr = self._to_decimal(values[0])
            adx = self._to_decimal(values[1])
            symbol, priority = mapping
            current = picked.get(symbol)
            indicator = MarketIndicator(atr=atr, adx=adx)
            if current is None or priority < current[0]:
                picked[symbol] = (priority, indicator)

        return {symbol: item[1] for symbol, item in picked.items()}

    def _post_scan(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        req = urllib.request.Request(
            self._url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
            text = resp.read().decode("utf-8")
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        return {}

    def _candidate_tickers(self, symbol: str) -> list[str]:
        sym = self._normalize_symbol(symbol)
        if not sym:
            return []
        return [
            f"BINANCE:{sym}USDT",
            f"BYBIT:{sym}USDT.P",
            f"OKX:{sym}USDT.P",
            f"BITGET:{sym}USDT.P",
        ]

    @staticmethod
    def _normalize_symbol(value: Any) -> str:
        return str(value or "").strip().upper()

    @staticmethod
    def _to_decimal(value: Any) -> Decimal:
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal(0)

    def _log_error_once(self, text: str) -> None:
        now_ms = int(time.time() * 1000)
        if now_ms - self._last_error_log_ms < 10_000:
            return
        self._last_error_log_ms = now_ms
        self._logbus.publish(text)
