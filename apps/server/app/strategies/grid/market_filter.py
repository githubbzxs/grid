from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

BAR_INTERVAL_MS = 60_000


@dataclass
class OhlcBar:
    ts_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


@dataclass
class MarketFilterConfig:
    enabled: bool = False
    atr_period: int = 14
    adx_period: int = 14
    atr_pct_min: Decimal = Decimal("0.002")
    atr_pct_max: Decimal = Decimal("0.02")
    adx_max: Decimal = Decimal("28")
    recover_pass_count: int = 3
    block_timeout_minutes: Decimal = Decimal("30")


@dataclass
class MarketFilterRuntime:
    state: str = "off"
    reason: str = "disabled"
    pass_streak: int = 0
    block_started_ms: int = 0
    block_seconds: int = 0
    atr_pct: Optional[Decimal] = None
    adx: Optional[Decimal] = None


@dataclass
class MarketFilterDecision:
    state: str
    reason: str
    atr_pct: Optional[Decimal]
    adx: Optional[Decimal]
    pass_streak: int
    block_seconds: int
    close_only: bool
    timeout_stop: bool


def update_ohlc_bars(
    bars: list[OhlcBar],
    ts_ms: int,
    price: Decimal,
    max_bars: int = 600,
) -> list[OhlcBar]:
    bucket = int(ts_ms) - (int(ts_ms) % BAR_INTERVAL_MS)
    if not bars or bars[-1].ts_ms != bucket:
        bars.append(
            OhlcBar(
                ts_ms=bucket,
                open=price,
                high=price,
                low=price,
                close=price,
            )
        )
    else:
        bar = bars[-1]
        if price > bar.high:
            bar.high = price
        if price < bar.low:
            bar.low = price
        bar.close = price
    if max_bars > 0 and len(bars) > max_bars:
        del bars[:-max_bars]
    return bars


def completed_bars(bars: list[OhlcBar], now_ms: int) -> list[OhlcBar]:
    if not bars:
        return []
    current_bucket = int(now_ms) - (int(now_ms) % BAR_INTERVAL_MS)
    if bars[-1].ts_ms == current_bucket:
        return bars[:-1]
    return bars


def required_bar_count(atr_period: int, adx_period: int) -> int:
    # ATR 需要 period+1 根，ADX 需要 2*period 根。
    return max(int(atr_period) + 1, int(adx_period) * 2)


def calc_atr_pct(bars: list[OhlcBar], period: int) -> Optional[Decimal]:
    if period <= 0 or len(bars) < period + 1:
        return None
    trs: list[Decimal] = []
    for i in range(1, len(bars)):
        prev_close = bars[i - 1].close
        curr = bars[i]
        tr = max(
            curr.high - curr.low,
            abs(curr.high - prev_close),
            abs(curr.low - prev_close),
        )
        trs.append(tr)
    if len(trs) < period:
        return None

    atr = sum(trs[:period], Decimal(0)) / Decimal(period)
    for tr in trs[period:]:
        atr = ((atr * Decimal(period - 1)) + tr) / Decimal(period)

    last_close = bars[-1].close
    if last_close <= 0:
        return None
    return atr / last_close


def calc_adx(bars: list[OhlcBar], period: int) -> Optional[Decimal]:
    if period <= 0 or len(bars) < (period * 2):
        return None

    trs: list[Decimal] = []
    plus_dm: list[Decimal] = []
    minus_dm: list[Decimal] = []

    for i in range(1, len(bars)):
        prev = bars[i - 1]
        curr = bars[i]
        up_move = curr.high - prev.high
        down_move = prev.low - curr.low

        pdm = up_move if up_move > 0 and up_move > down_move else Decimal(0)
        mdm = down_move if down_move > 0 and down_move > up_move else Decimal(0)
        tr = max(
            curr.high - curr.low,
            abs(curr.high - prev.close),
            abs(curr.low - prev.close),
        )
        trs.append(tr)
        plus_dm.append(pdm)
        minus_dm.append(mdm)

    if len(trs) < (period * 2 - 1):
        return None

    tr_s = sum(trs[:period], Decimal(0))
    pdm_s = sum(plus_dm[:period], Decimal(0))
    mdm_s = sum(minus_dm[:period], Decimal(0))

    dx_values: list[Decimal] = []

    def _dx(tr_sum: Decimal, pdm_sum: Decimal, mdm_sum: Decimal) -> Decimal:
        if tr_sum <= 0:
            return Decimal(0)
        plus_di = (Decimal(100) * pdm_sum) / tr_sum
        minus_di = (Decimal(100) * mdm_sum) / tr_sum
        denom = plus_di + minus_di
        if denom <= 0:
            return Decimal(0)
        return (Decimal(100) * abs(plus_di - minus_di)) / denom

    dx_values.append(_dx(tr_s, pdm_s, mdm_s))

    for i in range(period, len(trs)):
        tr_s = tr_s - (tr_s / Decimal(period)) + trs[i]
        pdm_s = pdm_s - (pdm_s / Decimal(period)) + plus_dm[i]
        mdm_s = mdm_s - (mdm_s / Decimal(period)) + minus_dm[i]
        dx_values.append(_dx(tr_s, pdm_s, mdm_s))

    if len(dx_values) < period:
        return None

    adx = sum(dx_values[:period], Decimal(0)) / Decimal(period)
    for dx in dx_values[period:]:
        adx = ((adx * Decimal(period - 1)) + dx) / Decimal(period)
    return adx


def evaluate_market_filter(
    cfg: MarketFilterConfig,
    runtime: MarketFilterRuntime,
    bars: list[OhlcBar],
    now_ms: int,
) -> MarketFilterDecision:
    if not cfg.enabled:
        runtime.state = "off"
        runtime.reason = "disabled"
        runtime.pass_streak = 0
        runtime.block_started_ms = 0
        runtime.block_seconds = 0
        runtime.atr_pct = None
        runtime.adx = None
        return MarketFilterDecision(
            state=runtime.state,
            reason=runtime.reason,
            atr_pct=runtime.atr_pct,
            adx=runtime.adx,
            pass_streak=runtime.pass_streak,
            block_seconds=runtime.block_seconds,
            close_only=False,
            timeout_stop=False,
        )

    need = required_bar_count(cfg.atr_period, cfg.adx_period)
    if len(bars) < need:
        runtime.state = "warmup"
        runtime.reason = f"warmup:{len(bars)}/{need}"
        runtime.pass_streak = 0
        runtime.block_started_ms = 0
        runtime.block_seconds = 0
        runtime.atr_pct = None
        runtime.adx = None
        return MarketFilterDecision(
            state=runtime.state,
            reason=runtime.reason,
            atr_pct=runtime.atr_pct,
            adx=runtime.adx,
            pass_streak=runtime.pass_streak,
            block_seconds=runtime.block_seconds,
            close_only=True,
            timeout_stop=False,
        )

    atr_pct = calc_atr_pct(bars, cfg.atr_period)
    adx = calc_adx(bars, cfg.adx_period)
    runtime.atr_pct = atr_pct
    runtime.adx = adx

    if atr_pct is None or adx is None:
        runtime.state = "warmup"
        runtime.reason = "indicator_not_ready"
        runtime.pass_streak = 0
        runtime.block_started_ms = 0
        runtime.block_seconds = 0
        return MarketFilterDecision(
            state=runtime.state,
            reason=runtime.reason,
            atr_pct=runtime.atr_pct,
            adx=runtime.adx,
            pass_streak=runtime.pass_streak,
            block_seconds=runtime.block_seconds,
            close_only=True,
            timeout_stop=False,
        )

    block_reasons: list[str] = []
    if atr_pct < cfg.atr_pct_min:
        block_reasons.append("atr_low")
    if atr_pct > cfg.atr_pct_max:
        block_reasons.append("atr_high")
    if adx > cfg.adx_max:
        block_reasons.append("adx_high")

    if block_reasons:
        runtime.state = "block"
        runtime.reason = ",".join(block_reasons)
        runtime.pass_streak = 0
        if runtime.block_started_ms <= 0:
            runtime.block_started_ms = int(now_ms)
        runtime.block_seconds = max(0, int((int(now_ms) - runtime.block_started_ms) / 1000))
        timeout_stop = False
        if cfg.block_timeout_minutes > 0:
            timeout_s = int(cfg.block_timeout_minutes * Decimal(60))
            timeout_stop = runtime.block_seconds >= timeout_s
        return MarketFilterDecision(
            state=runtime.state,
            reason=runtime.reason,
            atr_pct=runtime.atr_pct,
            adx=runtime.adx,
            pass_streak=runtime.pass_streak,
            block_seconds=runtime.block_seconds,
            close_only=True,
            timeout_stop=timeout_stop,
        )

    prev_state = runtime.state
    if prev_state in {"block", "warmup"}:
        runtime.pass_streak += 1
        if runtime.pass_streak < max(1, cfg.recover_pass_count):
            runtime.state = "warmup"
            runtime.reason = f"recovering:{runtime.pass_streak}/{max(1, cfg.recover_pass_count)}"
            runtime.block_started_ms = 0
            runtime.block_seconds = 0
            return MarketFilterDecision(
                state=runtime.state,
                reason=runtime.reason,
                atr_pct=runtime.atr_pct,
                adx=runtime.adx,
                pass_streak=runtime.pass_streak,
                block_seconds=runtime.block_seconds,
                close_only=True,
                timeout_stop=False,
            )

    runtime.state = "pass"
    runtime.reason = "ok"
    runtime.pass_streak = 0
    runtime.block_started_ms = 0
    runtime.block_seconds = 0
    return MarketFilterDecision(
        state=runtime.state,
        reason=runtime.reason,
        atr_pct=runtime.atr_pct,
        adx=runtime.adx,
        pass_streak=runtime.pass_streak,
        block_seconds=runtime.block_seconds,
        close_only=False,
        timeout_stop=False,
    )
