from __future__ import annotations

from decimal import Decimal

from app.strategies.grid.market_filter import (
    BAR_INTERVAL_MS,
    MarketFilterConfig,
    MarketFilterRuntime,
    OhlcBar,
    calc_adx,
    calc_atr_pct,
    completed_bars,
    evaluate_market_filter,
    update_ohlc_bars,
)


def _trend_bars(count: int, start: Decimal = Decimal("100")) -> list[OhlcBar]:
    bars: list[OhlcBar] = []
    price = start
    for i in range(count):
        open_price = price
        close_price = price + Decimal("0.8")
        high = close_price + Decimal("0.3")
        low = open_price - Decimal("0.2")
        bars.append(
            OhlcBar(
                ts_ms=i * BAR_INTERVAL_MS,
                open=open_price,
                high=high,
                low=low,
                close=close_price,
            )
        )
        price = close_price
    return bars


def _sideways_bars(count: int, start: Decimal = Decimal("100")) -> list[OhlcBar]:
    bars: list[OhlcBar] = []
    price = start
    for i in range(count):
        delta = Decimal("0.3") if (i % 2 == 0) else Decimal("-0.3")
        open_price = price
        close_price = price + delta
        high = max(open_price, close_price) + Decimal("0.2")
        low = min(open_price, close_price) - Decimal("0.2")
        bars.append(
            OhlcBar(
                ts_ms=i * BAR_INTERVAL_MS,
                open=open_price,
                high=high,
                low=low,
                close=close_price,
            )
        )
        price = close_price
    return bars


def _flat_bars(count: int, price: Decimal = Decimal("100")) -> list[OhlcBar]:
    return [
        OhlcBar(
            ts_ms=i * BAR_INTERVAL_MS,
            open=price,
            high=price,
            low=price,
            close=price,
        )
        for i in range(count)
    ]


def test_update_ohlc_bars_and_completed_bars() -> None:
    bars: list[OhlcBar] = []
    update_ohlc_bars(bars, 1_000, Decimal("100"))
    update_ohlc_bars(bars, 20_000, Decimal("102"))
    update_ohlc_bars(bars, 35_000, Decimal("99"))
    assert len(bars) == 1
    assert bars[0].open == Decimal("100")
    assert bars[0].high == Decimal("102")
    assert bars[0].low == Decimal("99")
    assert bars[0].close == Decimal("99")

    update_ohlc_bars(bars, BAR_INTERVAL_MS + 5_000, Decimal("101"))
    assert len(bars) == 2
    done = completed_bars(bars, BAR_INTERVAL_MS + 10_000)
    assert len(done) == 1
    assert done[0].close == Decimal("99")


def test_calc_atr_pct_returns_positive_value() -> None:
    bars = _trend_bars(40)
    atr_pct = calc_atr_pct(bars, 14)
    assert atr_pct is not None
    assert atr_pct > Decimal("0")
    assert atr_pct < Decimal("0.2")


def test_calc_adx_trend_higher_than_sideways() -> None:
    trend = calc_adx(_trend_bars(80), 14)
    sideways = calc_adx(_sideways_bars(80), 14)
    assert trend is not None
    assert sideways is not None
    assert trend > sideways


def test_evaluate_filter_disabled_returns_off() -> None:
    cfg = MarketFilterConfig(enabled=False)
    runtime = MarketFilterRuntime()
    decision = evaluate_market_filter(cfg, runtime, _trend_bars(50), now_ms=5_000_000)
    assert decision.state == "off"
    assert decision.close_only is False
    assert decision.timeout_stop is False


def test_evaluate_filter_warmup_when_bars_not_enough() -> None:
    cfg = MarketFilterConfig(enabled=True, atr_period=14, adx_period=14)
    runtime = MarketFilterRuntime()
    decision = evaluate_market_filter(cfg, runtime, _trend_bars(10), now_ms=5_000_000)
    assert decision.state == "warmup"
    assert decision.close_only is True
    assert decision.timeout_stop is False


def test_evaluate_filter_block_when_atr_too_low() -> None:
    cfg = MarketFilterConfig(
        enabled=True,
        atr_period=14,
        adx_period=14,
        atr_pct_min=Decimal("0.002"),
        atr_pct_max=Decimal("0.05"),
        adx_max=Decimal("80"),
    )
    runtime = MarketFilterRuntime()
    decision = evaluate_market_filter(cfg, runtime, _flat_bars(60), now_ms=5_000_000)
    assert decision.state == "block"
    assert "atr_low" in decision.reason
    assert decision.close_only is True
    assert decision.timeout_stop is False


def test_evaluate_filter_recover_requires_pass_streak() -> None:
    runtime = MarketFilterRuntime()
    block_cfg = MarketFilterConfig(
        enabled=True,
        atr_period=14,
        adx_period=14,
        atr_pct_min=Decimal("0.002"),
        atr_pct_max=Decimal("0.05"),
        adx_max=Decimal("80"),
        recover_pass_count=2,
    )
    evaluate_market_filter(block_cfg, runtime, _flat_bars(60), now_ms=6_000_000)
    assert runtime.state == "block"

    pass_cfg = MarketFilterConfig(
        enabled=True,
        atr_period=14,
        adx_period=14,
        atr_pct_min=Decimal("0.001"),
        atr_pct_max=Decimal("0.05"),
        adx_max=Decimal("100"),
        recover_pass_count=2,
    )
    d1 = evaluate_market_filter(pass_cfg, runtime, _trend_bars(80), now_ms=6_060_000)
    assert d1.state == "warmup"
    assert d1.close_only is True
    assert d1.pass_streak == 1

    d2 = evaluate_market_filter(pass_cfg, runtime, _trend_bars(80), now_ms=6_120_000)
    assert d2.state == "pass"
    assert d2.close_only is False
    assert d2.pass_streak == 0


def test_evaluate_filter_timeout_stop_trigger() -> None:
    cfg = MarketFilterConfig(
        enabled=True,
        atr_period=14,
        adx_period=14,
        atr_pct_min=Decimal("0.002"),
        atr_pct_max=Decimal("0.05"),
        adx_max=Decimal("80"),
        block_timeout_minutes=Decimal("1"),
    )
    runtime = MarketFilterRuntime(state="block", block_started_ms=1)
    decision = evaluate_market_filter(cfg, runtime, _flat_bars(80), now_ms=120_000)
    assert decision.state == "block"
    assert decision.close_only is True
    assert decision.block_seconds >= 60
    assert decision.timeout_stop is True
