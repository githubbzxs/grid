from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Any, Dict, Optional

from app.core.config_store import ConfigStore
from app.core.logbus import LogBus
from app.exchanges.grvt.sdk_ops import fetch_perp_markets as grvt_fetch_perp_markets
from app.exchanges.grvt.trader import GrvtTrader
from app.exchanges.lighter.sdk_ops import fetch_perp_markets as lighter_fetch_perp_markets
from app.exchanges.lighter.trader import LighterTrader
from app.exchanges.paradex.sdk_ops import fetch_perp_markets as paradex_fetch_perp_markets
from app.exchanges.paradex.trader import ParadexTrader
from app.exchanges.types import MarketMeta, Trader
from app.services.history_store import HistoryStore
from app.strategies.grid.ids import (
    CLIENT_ORDER_MAX,
    MAX_LEVEL_PER_SIDE,
    grid_client_order_id,
    grid_client_order_side_level,
    grid_prefix,
    is_grid_client_order,
)

GRID_MODE_DYNAMIC = "dynamic"
GRID_MODE_AS = "as"
DEFAULT_AS_GAMMA = Decimal("0.1")
DEFAULT_AS_K = Decimal("1.5")
DEFAULT_AS_TAU_SECONDS = Decimal("30")
DEFAULT_AS_VOL_POINTS = 60
DEFAULT_AS_STEP_MULT = Decimal("1")


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _fmt_decimal(value: Decimal, digits: int = 4) -> str:
    q = Decimal(1) / (Decimal(10) ** int(digits))
    return str(value.quantize(q, rounding=ROUND_HALF_UP))


def _quantize(value: Decimal, decimals: int, rounding) -> Decimal:
    q = Decimal(1) / (Decimal(10) ** int(decimals))
    return value.quantize(q, rounding=rounding)


def _to_scaled_int(value: Decimal, decimals: int, rounding) -> int:
    v = _quantize(value, decimals, rounding)
    return int(v * (Decimal(10) ** int(decimals)))


def _safe_decimal(v: Any) -> Decimal:
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal(0)


def _safe_int(v: Any, default: int) -> int:
    try:
        if v is None:
            return default
        return int(float(v))
    except Exception:
        return default


def _exchange_name(value: Any) -> str:
    name = str(value or "").strip().lower()
    if name == "paradex":
        return "paradex"
    if name == "grvt":
        return "grvt"
    return "lighter"


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _symbol_tokens(value: Any) -> list[str]:
    text = _normalize_symbol(value)
    tokens: list[str] = []
    buf: list[str] = []
    for ch in text:
        if ch.isalnum():
            buf.append(ch)
            continue
        if buf:
            tokens.append("".join(buf))
            buf = []
    if buf:
        tokens.append("".join(buf))
    return tokens


def _normalize_market_id(exchange: str, value: Any) -> Optional[str | int]:
    if value is None:
        return None
    if exchange in {"paradex", "grvt"}:
        text = str(value).strip()
        return text or None
    try:
        return int(str(value).strip())
    except Exception:
        return None


def _pick_market_item(symbol: str, items: list[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    base = _normalize_symbol(symbol)
    if not base:
        return None

    def _sym(item: Dict[str, Any]) -> str:
        return _normalize_symbol(item.get("symbol"))

    def _base_match(sym: str) -> bool:
        if not sym:
            return False
        if sym == base:
            return True
        tokens = _symbol_tokens(sym)
        if tokens and tokens[0] == base:
            return True
        if sym.startswith(base):
            remainder = sym[len(base) :]
            if not remainder:
                return True
            if remainder[0] in "-_:/":
                return True
            if remainder.startswith(("USDC", "USDT", "USD")):
                return True
        return False

    candidates = [item for item in items if _base_match(_sym(item))]
    if not candidates:
        return None

    def _score(item: Dict[str, Any]) -> int:
        sym = _sym(item)
        score = 0
        if sym == base:
            score += 6
        tokens = _symbol_tokens(sym)
        if tokens and tokens[0] == base:
            score += 4
        if sym.startswith(base):
            score += 2
        if "USDC" in sym:
            score += 3
        elif "USD" in sym:
            score += 2
        elif "USDT" in sym:
            score += 1
        return score

    return max(candidates, key=_score)


def _market_id_matches_symbol(exchange: str, symbol: str, market_id: Any) -> bool:
    if exchange not in {"paradex", "grvt"}:
        return True
    mid = _normalize_symbol(market_id)
    return bool(_pick_market_item(symbol, [{"symbol": mid, "market_id": mid}]))


def _now_ms() -> int:
    return int(time.time() * 1000)


def _parse_iso_ms(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except Exception:
        return None


def _trade_ts_ms(value: Any) -> Optional[int]:
    try:
        ts = int(value)
    except Exception:
        return None
    if ts < 10_000_000_000:
        return ts * 1000
    return ts


def _normalize_grid_mode(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in (
        "as",
        "as_grid",
        "as-grid",
        "as网格",
        "avellaneda",
        "avellaneda_stoikov",
        "avellaneda-stoikov",
        "stoikov",
    ):
        return GRID_MODE_AS
    return GRID_MODE_DYNAMIC


def _as_param_decimal(strat: Dict[str, Any], key: str, default: Decimal) -> Decimal:
    value = _safe_decimal(strat.get(key))
    if value <= 0:
        return default
    return value


def _as_param_int(strat: Dict[str, Any], key: str, default: int, min_value: int) -> int:
    value = _safe_int(strat.get(key), default)
    if value < min_value:
        return default
    return value


def _min_price_step(meta: MarketMeta) -> Decimal:
    return Decimal(1) / (Decimal(10) ** int(meta.price_decimals))


def _calc_base_qty(mode: str, value: Decimal, price: Decimal) -> Decimal:
    if mode == "base":
        return value
    if price <= 0:
        return Decimal(0)
    return value / price


def _order_field(order: Any, name: str) -> Any:
    if isinstance(order, dict):
        return order.get(name)
    return getattr(order, name, None)


def _order_price_decimal(order: Any, meta: MarketMeta) -> Decimal:
    price = _order_field(order, "price")
    if price is not None:
        try:
            return Decimal(str(price))
        except Exception:
            pass
    base_price = _order_field(order, "base_price") or 0
    try:
        return Decimal(int(base_price)) / (Decimal(10) ** int(meta.price_decimals))
    except Exception:
        return Decimal(0)


def _unique_prices(values: list[Decimal]) -> list[Decimal]:
    seen: set[Decimal] = set()
    result: list[Decimal] = []
    for v in values:
        if v in seen:
            continue
        seen.add(v)
        result.append(v)
    return result


def _order_client_id(order: Any) -> Optional[int]:
    for key in ("client_order_index", "client_id", "client_order_id", "clientOrderId"):
        value = _order_field(order, key)
        if value is None:
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            v = value.strip()
            if v.isdigit():
                return int(v)
    return None


def _order_id(order: Any) -> Any:
    for key in ("order_index", "id", "order_id"):
        value = _order_field(order, key)
        if value is None:
            continue
        return value
    return None


def _order_side(order: Any) -> Optional[str]:
    is_ask = _order_field(order, "is_ask")
    if isinstance(is_ask, bool):
        return "ask" if is_ask else "bid"
    is_buying_asset = _order_field(order, "is_buying_asset")
    if isinstance(is_buying_asset, bool):
        return "bid" if is_buying_asset else "ask"
    side = _order_field(order, "side") or _order_field(order, "order_side")
    if isinstance(side, str):
        upper = side.upper()
        if upper in ("SELL", "ASK"):
            return "ask"
        if upper in ("BUY", "BID"):
            return "bid"
    if isinstance(order, dict):
        legs = order.get("legs")
        if isinstance(legs, list) and legs:
            leg0 = legs[0]
            if isinstance(leg0, dict):
                leg_buying = leg0.get("is_buying_asset")
                if isinstance(leg_buying, bool):
                    return "bid" if leg_buying else "ask"
                leg_side = leg0.get("side")
                if isinstance(leg_side, str):
                    upper = leg_side.upper()
                    if upper in ("SELL", "ASK"):
                        return "ask"
                    if upper in ("BUY", "BID"):
                        return "bid"
    return None


@dataclass
class BotStatus:
    symbol: str
    running: bool
    started_at: Optional[str] = None
    last_tick_at: Optional[str] = None
    message: str = ""
    market_id: Optional[str | int] = None
    mid: Optional[str] = None
    center: Optional[str] = None
    desired: int = 0
    existing: int = 0
    delay_count: int = 0
    reduce_mode: bool = False
    stop_signal: bool = False
    stop_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "running": self.running,
            "started_at": self.started_at,
            "last_tick_at": self.last_tick_at,
            "message": self.message,
            "market_id": self.market_id,
            "mid": self.mid,
            "center": self.center,
            "desired": self.desired,
            "existing": self.existing,
            "delay_count": self.delay_count,
            "reduce_mode": self.reduce_mode,
            "stop_signal": self.stop_signal,
            "stop_reason": self.stop_reason,
        }


@dataclass
class SimOrder:
    order_index: int
    client_order_index: int
    price: Decimal
    base_qty: Decimal
    is_ask: bool
    created_at_ms: int

    @property
    def side(self) -> str:
        return "ask" if self.is_ask else "bid"


@dataclass
class SimTrade:
    ts_ms: int
    price: Decimal
    size: Decimal
    side: str


@dataclass
class SimState:
    orders: Dict[int, SimOrder] = field(default_factory=dict)
    trades: list[SimTrade] = field(default_factory=list)
    position_base: Decimal = Decimal(0)
    position_cost: Decimal = Decimal(0)
    realized_pnl: Decimal = Decimal(0)
    last_mid: Decimal = Decimal(0)


@dataclass
class TradePnlState:
    last_ts_ms: int = 0
    position_base: Decimal = Decimal(0)
    position_cost: Decimal = Decimal(0)
    realized_pnl: Decimal = Decimal(0)


class BotManager:
    def __init__(self, logbus: LogBus, config: ConfigStore) -> None:
        self._logbus = logbus
        self._config = config
        self._tasks: Dict[str, asyncio.Task[None]] = {}
        self._status: Dict[str, BotStatus] = {}
        self._lock = asyncio.Lock()
        self._reduce_mode: Dict[str, bool] = {}
        self._manual_stop: set[str] = set()
        self._restart_tasks: Dict[str, asyncio.Task[None]] = {}
        self._restart_times: Dict[str, list[int]] = {}
        self._start_ms: Dict[str, int] = {}
        self._stop_signal: Dict[str, bool] = {}
        self._stop_reason: Dict[str, str] = {}
        self._stop_check_at: Dict[str, int] = {}
        self._pnl_cache: Dict[str, tuple[int, Decimal]] = {}
        self._base_pnl: Dict[str, Decimal] = {}
        self._peak_pnl: Dict[str, Decimal] = {}
        self._sim_states: Dict[str, SimState] = {}
        self._mid_history: Dict[str, list[tuple[int, Decimal]]] = {}
        self._history = HistoryStore(self._config.path.parent / "runtime_history.jsonl")
        self._history_recorded: set[str] = set()
        self._trade_pnl: Dict[str, TradePnlState] = {}
        self._delay_counts: Dict[str, int] = {}
        self._delay_price_marks: Dict[str, set[str]] = {}
        self._create_block_notice: Dict[str, tuple[int, str]] = {}
        self._cid_level_cursor: Dict[str, Dict[str, int]] = {}
        self._markets_cache: Dict[tuple[str, str], tuple[float, list[Dict[str, Any]]]] = {}
        self._market_resolve_next: Dict[tuple[str, str], float] = {}
        self._markets_cache_ttl_s = 60.0
        self._market_resolve_cooldown_s = 20.0

    async def start(self, symbol: str, trader: Trader, manual: bool = True) -> None:
        symbol = symbol.upper()
        async with self._lock:
            if manual:
                self._manual_stop.discard(symbol)
                self._restart_times.pop(symbol, None)
                self._stop_signal.pop(symbol, None)
                self._stop_reason.pop(symbol, None)
                self._stop_check_at.pop(symbol, None)
                self._pnl_cache.pop(symbol, None)
                self._base_pnl.pop(symbol, None)
                self._peak_pnl.pop(symbol, None)
                self._sim_reset(symbol)
                self._trade_pnl_reset(symbol)
                self._delay_counts.pop(symbol, None)
                self._delay_price_marks.pop(symbol, None)
                self._create_block_notice.pop(symbol, None)
                self._history_recorded.discard(symbol)
                self._start_ms[symbol] = _now_ms()
            elif symbol not in self._start_ms:
                self._start_ms[symbol] = _now_ms()
            restart_task = self._restart_tasks.pop(symbol, None)
            if restart_task and not restart_task.done():
                restart_task.cancel()
            task = self._tasks.get(symbol)
            if task and not task.done():
                return
            self._status[symbol] = BotStatus(
                symbol=symbol,
                running=True,
                started_at=_now_iso(),
                last_tick_at=None,
                message="启动中",
            )
            self._tasks[symbol] = asyncio.create_task(self._run(symbol, trader))
        self._logbus.publish(f"bot.start symbol={symbol}")

    async def _load_markets(self, exchange: str, env: str) -> list[Dict[str, Any]]:
        now = time.time()
        key = (exchange, env)
        cached = self._markets_cache.get(key)
        if cached and now - cached[0] <= self._markets_cache_ttl_s:
            return cached[1]
        items: list[Dict[str, Any]] = []
        try:
            if exchange == "paradex":
                items = await paradex_fetch_perp_markets(env)
            elif exchange == "grvt":
                items = await grvt_fetch_perp_markets(env)
            else:
                items = await lighter_fetch_perp_markets(env)
        except Exception as exc:
            self._logbus.publish(f"market.resolve.error exchange={exchange} env={env} err={type(exc).__name__}:{exc}")
            items = []
        self._markets_cache[key] = (now, items)
        return items

    async def _resolve_market_id(
        self,
        symbol: str,
        trader: Trader,
        cfg: Dict[str, Any],
        strat: Dict[str, Any],
    ) -> Optional[str | int]:
        symbol = _normalize_symbol(symbol)
        exchange = _exchange_name(strat.get("exchange") or (cfg.get("exchange", {}) or {}).get("name"))
        if not exchange:
            if isinstance(trader, ParadexTrader):
                exchange = "paradex"
            elif isinstance(trader, GrvtTrader):
                exchange = "grvt"
            else:
                exchange = "lighter"
        env = str((cfg.get("exchange", {}) or {}).get("env") or "mainnet")
        now = time.time()
        cooldown_key = (exchange, symbol)
        next_ts = self._market_resolve_next.get(cooldown_key, 0.0)
        if now < next_ts:
            return None
        self._market_resolve_next[cooldown_key] = now + self._market_resolve_cooldown_s

        items = await self._load_markets(exchange, env)
        if not items and isinstance(trader, GrvtTrader):
            try:
                if not trader._api.markets:
                    await trader._api.load_markets()
                items = [{"symbol": key, "market_id": key} for key in trader._api.markets.keys()]
            except Exception as exc:
                self._logbus.publish(
                    f"market.resolve.error exchange={exchange} env={env} err={type(exc).__name__}:{exc}"
                )

        picked = _pick_market_item(symbol, items)
        if not picked:
            self._logbus.publish(f"market.resolve.miss symbol={symbol} exchange={exchange}")
            return None

        market_id = _normalize_market_id(exchange, picked.get("market_id"))
        if market_id is None:
            self._logbus.publish(f"market.resolve.invalid symbol={symbol} exchange={exchange}")
            return None

        strat["market_id"] = market_id
        if not str(strat.get("exchange") or "").strip():
            strat["exchange"] = exchange
        try:
            cfg = dict(cfg)
            strategies = cfg.get("strategies") or {}
            if isinstance(strategies, dict) and symbol in strategies:
                entry = strategies[symbol]
                if isinstance(entry, dict):
                    entry["market_id"] = market_id
                    if not str(entry.get("exchange") or "").strip():
                        entry["exchange"] = exchange
                    cfg["strategies"] = strategies
                    self._config.write(cfg)
        except Exception as exc:
            self._logbus.publish(
                f"market.resolve.persist.error symbol={symbol} exchange={exchange} err={type(exc).__name__}:{exc}"
            )

        self._logbus.publish(f"market.resolve.ok symbol={symbol} exchange={exchange} market_id={market_id}")
        return market_id

    async def stop(self, symbol: str) -> None:
        symbol = symbol.upper()
        async with self._lock:
            self._manual_stop.add(symbol)
            self._stop_signal.pop(symbol, None)
            self._stop_reason.pop(symbol, None)
            self._stop_check_at.pop(symbol, None)
            self._pnl_cache.pop(symbol, None)
            self._base_pnl.pop(symbol, None)
            self._peak_pnl.pop(symbol, None)
            self._history_recorded.discard(symbol)
            self._start_ms.pop(symbol, None)
            self._trade_pnl_reset(symbol)
            restart_task = self._restart_tasks.pop(symbol, None)
            if restart_task and not restart_task.done():
                restart_task.cancel()
            task = self._tasks.get(symbol)
            if not task:
                self._status[symbol] = BotStatus(symbol=symbol, running=False, message="已停止")
                return
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        async with self._lock:
            self._tasks.pop(symbol, None)
            self._restart_times.pop(symbol, None)
            prev = self._status.get(symbol)
            self._status[symbol] = BotStatus(symbol=symbol, running=False, message="已停止", started_at=prev.started_at if prev else None)
        self._logbus.publish(f"bot.stop symbol={symbol}")

    async def stop_all(self) -> None:
        symbols = list(self._tasks.keys())
        for symbol in symbols:
            await self.stop(symbol)

    def snapshot(self) -> Dict[str, Any]:
        return {k: v.to_dict() for k, v in self._status.items()}

    @staticmethod
    def _sim_enabled(runtime: Dict[str, Any]) -> bool:
        return bool(runtime.get("dry_run", True))

    @staticmethod
    def _sim_fill_enabled(runtime: Dict[str, Any]) -> bool:
        return bool(runtime.get("dry_run", True)) and bool(runtime.get("simulate_fill", False))

    def _sim_state(self, symbol: str) -> SimState:
        sym = symbol.upper()
        state = self._sim_states.get(sym)
        if state is None:
            state = SimState()
            self._sim_states[sym] = state
        return state

    def _sim_reset(self, symbol: str) -> None:
        self._sim_states.pop(symbol.upper(), None)

    def _trade_pnl_state(self, symbol: str) -> TradePnlState:
        sym = symbol.upper()
        state = self._trade_pnl.get(sym)
        if state is None:
            state = TradePnlState()
            self._trade_pnl[sym] = state
        return state

    def _trade_pnl_reset(self, symbol: str) -> None:
        self._trade_pnl.pop(symbol.upper(), None)

    def sim_orders(self, symbol: str) -> list[SimOrder]:
        return list(self._sim_state(symbol).orders.values())

    def sim_open_orders(self, symbol: str) -> int:
        return len(self._sim_state(symbol).orders)

    def sim_position_base(self, symbol: str) -> Decimal:
        return self._sim_state(symbol).position_base

    def sim_last_mid(self, symbol: str) -> Decimal:
        return self._sim_state(symbol).last_mid

    def sim_pnl(self, symbol: str, mid_value: Optional[Decimal] = None) -> Decimal:
        state = self._sim_state(symbol)
        mid = mid_value if mid_value is not None and mid_value > 0 else state.last_mid
        return state.realized_pnl + (mid * state.position_base - state.position_cost)

    def sim_trade_stats(self, symbol: str, start_ms: int, end_ms: int) -> tuple[Decimal, int]:
        state = self._sim_state(symbol)
        total = Decimal(0)
        count = 0
        for trade in state.trades:
            if trade.ts_ms < start_ms or trade.ts_ms > end_ms:
                continue
            total += abs(trade.price * trade.size)
            count += 1
        return total, count

    def _sim_update_mid(self, symbol: str, mid: Decimal) -> None:
        self._sim_state(symbol).last_mid = mid

    def _pick_level_with_cursor(self, symbol: str, side: str, free_levels: list[int]) -> Optional[int]:
        if not free_levels:
            return None
        sym = symbol.upper()
        side_key = "ask" if side == "ask" else "bid"
        cursor = self._cid_level_cursor.get(sym)
        if cursor is None:
            seed = (_now_ms() % MAX_LEVEL_PER_SIDE) + 1
            cursor = {
                "ask": int(seed),
                "bid": int((seed % MAX_LEVEL_PER_SIDE) + 1),
            }
            self._cid_level_cursor[sym] = cursor
        start = int(cursor.get(side_key, 1))
        levels = sorted(free_levels)
        picked: Optional[int] = None
        for lvl in levels:
            if lvl >= start:
                picked = lvl
                break
        if picked is None:
            picked = levels[0]
        next_level = int(picked) + 1
        if next_level > MAX_LEVEL_PER_SIDE:
            next_level = 1
        cursor[side_key] = next_level
        return picked

    def _append_mid_history(self, symbol: str, ts_ms: int, mid: Decimal, max_points: int) -> list[tuple[int, Decimal]]:
        history = self._mid_history.get(symbol)
        if history is None:
            history = []
            self._mid_history[symbol] = history
        history.append((ts_ms, mid))
        if max_points > 0 and len(history) > max_points:
            del history[:-max_points]
        return history

    def _calc_as_sigma(self, history: list[tuple[int, Decimal]]) -> Decimal:
        if len(history) < 2:
            return Decimal(0)
        normalized: list[float] = []
        for (ts0, p0), (ts1, p1) in zip(history, history[1:]):
            dt = (ts1 - ts0) / 1000.0
            if dt <= 0:
                continue
            delta = float(p1 - p0)
            normalized.append(delta / math.sqrt(dt))
        if len(normalized) < 2:
            return Decimal(0)
        mean = sum(normalized) / len(normalized)
        var = sum((x - mean) ** 2 for x in normalized) / (len(normalized) - 1)
        if var < 0:
            var = 0
        sigma = math.sqrt(var)
        return Decimal(str(sigma))

    def _calc_as_center_step(
        self,
        symbol: str,
        mid: Decimal,
        pos_base: Decimal,
        strat: Dict[str, Any],
        meta: MarketMeta,
        now_ms: int,
    ) -> tuple[Decimal, Decimal]:
        gamma = _as_param_decimal(strat, "as_gamma", DEFAULT_AS_GAMMA)
        k = _as_param_decimal(strat, "as_k", DEFAULT_AS_K)
        tau = _as_param_decimal(strat, "as_tau_seconds", DEFAULT_AS_TAU_SECONDS)
        vol_points = _as_param_int(strat, "as_vol_points", DEFAULT_AS_VOL_POINTS, 5)
        step_mult = _as_param_decimal(strat, "as_step_multiplier", DEFAULT_AS_STEP_MULT)

        history = self._append_mid_history(symbol, now_ms, mid, vol_points + 1)
        sigma = self._calc_as_sigma(history)
        tick = _min_price_step(meta)

        gamma_f = float(gamma)
        k_f = float(k)
        tau_f = float(tau)
        sigma_f = float(sigma)
        pos_f = float(pos_base)
        mid_f = float(mid)

        if gamma_f <= 0 or k_f <= 0 or tau_f <= 0:
            center = _quantize(mid, meta.price_decimals, ROUND_HALF_UP)
            step = _quantize(tick, meta.price_decimals, ROUND_HALF_UP)
            return center, step

        # AS 模型：r = S - q * γ * σ^2 * τ，δ* = γ * σ^2 * τ + (2/γ) ln(1 + γ/k)
        spread = gamma_f * (sigma_f ** 2) * tau_f + (2.0 / gamma_f) * math.log(1.0 + (gamma_f / k_f))
        step_mult_f = float(step_mult) if float(step_mult) > 0 else 1.0
        step = Decimal(str(max((spread / 2.0) * step_mult_f, float(tick))))
        step = _quantize(step, meta.price_decimals, ROUND_HALF_UP)

        center = Decimal(str(mid_f - pos_f * gamma_f * (sigma_f ** 2) * tau_f))
        center = _quantize(center, meta.price_decimals, ROUND_HALF_UP)
        return center, step

    def _sim_create_order(
        self,
        symbol: str,
        order_index: int,
        client_order_index: int,
        price: Decimal,
        base_qty: Decimal,
        is_ask: bool,
        created_at_ms: int,
    ) -> None:
        state = self._sim_state(symbol)
        state.orders[order_index] = SimOrder(
            order_index=order_index,
            client_order_index=client_order_index,
            price=price,
            base_qty=base_qty,
            is_ask=is_ask,
            created_at_ms=created_at_ms,
        )

    def _sim_cancel_order(self, symbol: str, order_index: int) -> None:
        state = self._sim_state(symbol)
        state.orders.pop(order_index, None)

    def _sim_apply_trade(self, symbol: str, side: str, price: Decimal, size: Decimal, ts_ms: int) -> None:
        state = self._sim_state(symbol)
        size = abs(size)
        if size <= 0:
            return
        if side == "bid":
            if state.position_base >= 0:
                state.position_base += size
                state.position_cost += price * size
            else:
                short_size = abs(state.position_base)
                cover = min(size, short_size)
                avg_entry = abs(state.position_cost / state.position_base) if state.position_base != 0 else Decimal(0)
                state.realized_pnl += (avg_entry - price) * cover
                remaining = size - cover
                state.position_base += cover
                if state.position_base < 0:
                    state.position_cost = avg_entry * state.position_base
                else:
                    state.position_cost = Decimal(0)
                    if remaining > 0:
                        state.position_base = remaining
                        state.position_cost = price * remaining
        else:
            if state.position_base <= 0:
                state.position_base -= size
                state.position_cost -= price * size
            else:
                cover = min(size, state.position_base)
                avg_entry = abs(state.position_cost / state.position_base) if state.position_base != 0 else Decimal(0)
                state.realized_pnl += (price - avg_entry) * cover
                remaining = size - cover
                state.position_base -= cover
                if state.position_base > 0:
                    state.position_cost = avg_entry * state.position_base
                else:
                    state.position_cost = Decimal(0)
                    if remaining > 0:
                        state.position_base = -remaining
                        state.position_cost = -price * remaining

        state.trades.append(SimTrade(ts_ms=ts_ms, price=price, size=size, side=side))

    def _apply_trade_pnl(self, state: TradePnlState, side: str, price: Decimal, size: Decimal) -> None:
        size = abs(size)
        if size <= 0:
            return
        if side == "bid":
            if state.position_base >= 0:
                state.position_base += size
                state.position_cost += price * size
            else:
                short_size = abs(state.position_base)
                cover = min(size, short_size)
                avg_entry = abs(state.position_cost / state.position_base) if state.position_base != 0 else Decimal(0)
                state.realized_pnl += (avg_entry - price) * cover
                remaining = size - cover
                state.position_base += cover
                if state.position_base < 0:
                    state.position_cost = avg_entry * state.position_base
                else:
                    state.position_cost = Decimal(0)
                    if remaining > 0:
                        state.position_base = remaining
                        state.position_cost = price * remaining
        else:
            if state.position_base <= 0:
                state.position_base -= size
                state.position_cost -= price * size
            else:
                cover = min(size, state.position_base)
                avg_entry = abs(state.position_cost / state.position_base) if state.position_base != 0 else Decimal(0)
                state.realized_pnl += (price - avg_entry) * cover
                remaining = size - cover
                state.position_base -= cover
                if state.position_base > 0:
                    state.position_cost = avg_entry * state.position_base
                else:
                    state.position_cost = Decimal(0)
                    if remaining > 0:
                        state.position_base = -remaining
                        state.position_cost = -price * remaining

    def _trade_pnl_value(self, state: TradePnlState, mid: Decimal) -> Decimal:
        if mid <= 0:
            return state.realized_pnl
        return state.realized_pnl + (mid * state.position_base - state.position_cost)

    async def lighter_trade_pnl(
        self,
        trader: LighterTrader,
        symbol: str,
        market_id: int,
        start_ms: int,
        end_ms: int,
        mid: Decimal,
    ) -> Decimal:
        state = await self._lighter_update_trade_pnl(trader, symbol, market_id, start_ms, end_ms)
        return self._trade_pnl_value(state, mid)

    def _sim_match_orders(self, symbol: str, bid: Decimal, ask: Decimal, now_ms: int) -> None:
        state = self._sim_state(symbol)
        if not state.orders:
            return
        filled: list[SimOrder] = []
        for order in state.orders.values():
            if order.is_ask:
                if bid >= order.price:
                    filled.append(order)
            else:
                if ask <= order.price:
                    filled.append(order)
        if not filled:
            return
        for order in filled:
            self._sim_apply_trade(symbol, order.side, order.price, order.base_qty, now_ms)
            state.orders.pop(order.order_index, None)
            self._logbus.publish(
                f"sim.fill symbol={symbol} side={order.side} price={order.price} size={order.base_qty}"
            )

    def _sim_market_close(self, symbol: str, price: Decimal) -> None:
        state = self._sim_state(symbol)
        size = abs(state.position_base)
        if size <= 0:
            return
        side = "ask" if state.position_base > 0 else "bid"
        self._sim_apply_trade(symbol, side, price, size, _now_ms())

    async def _run(self, symbol: str, trader: Trader) -> None:
        interval_s = 0.01
        try:
            while True:
                await asyncio.sleep(interval_s)
                cfg = self._config.read()
                runtime = cfg.get("runtime", {}) or {}
                dry_run = bool(runtime.get("dry_run", True))
                simulate = self._sim_enabled(runtime)
                simulate_fill = self._sim_fill_enabled(runtime)
                stop_after_minutes = _safe_decimal(runtime.get("stop_after_minutes") or 0)
                stop_after_volume = _safe_decimal(runtime.get("stop_after_volume") or 0)
                stop_check_interval_ms = _safe_int(runtime.get("stop_check_interval_ms"), 1000)
                strat = (cfg.get("strategies", {}) or {}).get(symbol, {}) or {}
                grid_mode = _normalize_grid_mode(strat.get("grid_mode"))

                if not bool(strat.get("enabled", True)):
                    await self._update_status(symbol, running=True, message="已禁用", last_tick_at=_now_iso())
                    continue

                exchange_name = _exchange_name(strat.get("exchange") or (cfg.get("exchange", {}) or {}).get("name"))
                market_id = _normalize_market_id(exchange_name, strat.get("market_id"))
                if market_id is not None and not _market_id_matches_symbol(exchange_name, symbol, market_id):
                    market_id = None
                if market_id is None:
                    market_id = await self._resolve_market_id(symbol, trader, cfg, strat)
                if market_id is None:
                    await self._update_status(symbol, running=True, message="未配置 market_id", last_tick_at=_now_iso())
                    continue

                if symbol not in self._base_pnl:
                    try:
                        pnl_init = await self._position_pnl(trader, market_id, symbol, simulate=simulate)
                        if pnl_init is not None:
                            self._base_pnl[symbol] = pnl_init
                    except Exception as exc:
                        self._logbus.publish(
                            f"pnl.init.error symbol={symbol} market_id={market_id} err={type(exc).__name__}:{exc}"
                        )

                meta = await trader.market_meta(market_id)
                bid, ask = await trader.best_bid_ask(market_id)
                if bid is None or ask is None:
                    await self._update_status(symbol, running=True, message="无法获取盘口", last_tick_at=_now_iso(), market_id=market_id)
                    continue

                mid = (bid + ask) / 2

                now_ms = _now_ms()
                if simulate:
                    self._sim_update_mid(symbol, mid)
                    if simulate_fill:
                        self._sim_match_orders(symbol, bid, ask, now_ms)
                start_ms = self._start_ms.get(symbol)
                if start_ms is None:
                    status = self._status.get(symbol)
                    start_ms = _parse_iso_ms(status.started_at if status else None) or now_ms
                    self._start_ms[symbol] = start_ms

                step_input = _safe_decimal(strat.get("grid_step") or 0)
                if grid_mode == GRID_MODE_AS:
                    min_step = _min_price_step(meta)
                else:
                    if step_input <= 0:
                        await self._update_status(
                            symbol,
                            running=True,
                            message="grid_step 必须大于 0",
                            last_tick_at=_now_iso(),
                            market_id=market_id,
                        )
                        continue
                    min_step = step_input

                stop_signal = bool(self._stop_signal.get(symbol, False))
                stop_reason = self._stop_reason.get(symbol, "")

                if grid_mode == GRID_MODE_AS:
                    max_drawdown = _safe_decimal(strat.get("as_max_drawdown") or 0)
                    if max_drawdown > 0:
                        pnl_now = await self._position_pnl(trader, market_id, symbol, simulate=simulate)
                        if pnl_now is None:
                            pnl_now = Decimal(0)
                        base_pnl = self._base_pnl.get(symbol)
                        if base_pnl is None:
                            self._base_pnl[symbol] = pnl_now
                            base_pnl = pnl_now
                        profit_now = pnl_now - _safe_decimal(base_pnl)
                        peak = self._peak_pnl.get(symbol)
                        if peak is None or profit_now > peak:
                            peak = profit_now
                            self._peak_pnl[symbol] = peak
                        drawdown = peak - profit_now
                        if drawdown >= max_drawdown:
                            self._stop_signal[symbol] = True
                            self._stop_reason[symbol] = "最大回撤触发"
                            await self._cancel_grid_orders(symbol, trader, market_id, simulate=simulate)
                            await self._record_history(
                                trader,
                                [symbol],
                                "as_drawdown",
                                f"drawdown={_fmt_decimal(drawdown)}",
                            )
                            await self._update_status(
                                symbol,
                                running=False,
                                message="AS 回撤触发紧急停止",
                                last_tick_at=_now_iso(),
                                market_id=market_id,
                                mid=str(mid),
                                desired=0,
                                existing=0,
                                reduce_mode=False,
                                stop_signal=True,
                                stop_reason="as_drawdown",
                            )
                            self._logbus.publish(
                                f"as.drawdown.stop symbol={symbol} drawdown={_fmt_decimal(drawdown)} limit={_fmt_decimal(max_drawdown)}"
                            )
                            return

                reduce_mode = False
                reduce_side: Optional[str] = None
                pos_notional: Optional[Decimal] = None
                pos_base: Optional[Decimal] = None
                max_pos = _safe_decimal(strat.get("max_position_notional") or 0)
                reduce_exit = _safe_decimal(strat.get("reduce_position_notional") or 0)
                reduce_mult = _safe_decimal(strat.get("reduce_order_size_multiplier") or 1)
                if grid_mode != GRID_MODE_AS:
                    reduce_mode = self._reduce_mode.get(symbol, False)
                    if reduce_mult < 1:
                        reduce_mult = Decimal(1)
                else:
                    max_pos = Decimal(0)
                    reduce_exit = Decimal(0)
                    reduce_mult = Decimal(1)
                    self._reduce_mode[symbol] = False

                need_position = max_pos > 0 or stop_signal or stop_after_minutes > 0 or stop_after_volume > 0 or grid_mode == GRID_MODE_AS
                if need_position:
                    if simulate:
                        pos_base = self.sim_position_base(symbol)
                        if mid > 0:
                            pos_notional = abs(pos_base * mid)
                    else:
                        try:
                            pos_base = await trader.position_base(market_id)
                            if mid > 0:
                                pos_notional = abs(pos_base * mid)
                        except Exception as exc:
                            self._logbus.publish(
                                f"position.error symbol={symbol} market_id={market_id} err={type(exc).__name__}:{exc}"
                            )

                if grid_mode != GRID_MODE_AS and max_pos > 0 and pos_notional is not None:
                    if reduce_exit <= 0 or reduce_exit >= max_pos:
                        reduce_exit = max_pos * Decimal("0.8")
                    if not reduce_mode and pos_notional >= max_pos:
                        reduce_mode = True
                    if reduce_mode and pos_notional <= reduce_exit:
                        reduce_mode = False
                    self._reduce_mode[symbol] = reduce_mode
                    if reduce_mode and pos_base is not None:
                        if pos_base > 0:
                            reduce_side = "ask"
                        elif pos_base < 0:
                            reduce_side = "bid"

                if grid_mode == GRID_MODE_AS:
                    pos_for_as = pos_base if pos_base is not None else Decimal(0)
                    center, step = self._calc_as_center_step(
                        symbol,
                        mid,
                        pos_for_as,
                        strat,
                        meta,
                        now_ms,
                    )
                else:
                    center = (mid / min_step).to_integral_value(rounding=ROUND_HALF_UP) * min_step
                    center = _quantize(center, meta.price_decimals, ROUND_HALF_UP)
                    step = min_step

                if not stop_signal and (stop_after_minutes > 0 or stop_after_volume > 0):
                    interval_ms = max(200, stop_check_interval_ms)
                    last_check = self._stop_check_at.get(symbol, 0)
                    if (now_ms - last_check) >= interval_ms:
                        reason_parts: list[str] = []
                        if stop_after_minutes > 0:
                            limit_ms = int(stop_after_minutes * Decimal(60_000))
                            if (now_ms - start_ms) >= limit_ms:
                                reason_parts.append("运行时间达到")
                        if stop_after_volume > 0:
                            try:
                                if simulate:
                                    volume, _ = self.sim_trade_stats(symbol, start_ms, now_ms)
                                else:
                                    volume, _ = await self._trade_stats_since(trader, market_id, start_ms, now_ms)
                                if volume >= stop_after_volume:
                                    reason_parts.append("成交量达到")
                            except Exception as exc:
                                self._logbus.publish(
                                    f"stop.volume.error symbol={symbol} market_id={market_id} err={type(exc).__name__}:{exc}"
                                )
                        if reason_parts:
                            stop_signal = True
                            stop_reason = "且".join(reason_parts)
                            self._stop_signal[symbol] = True
                            self._stop_reason[symbol] = stop_reason
                            self._logbus.publish(f"bot.stop_signal symbol={symbol} reason={stop_reason}")
                        self._stop_check_at[symbol] = now_ms

                if stop_signal and pos_base is not None:
                    clear_step = Decimal(1) / (Decimal(10) ** int(meta.size_decimals))
                    clear_threshold = max(meta.min_base_amount, clear_step)
                    if abs(pos_base) <= clear_threshold:
                        await self._cancel_grid_orders(symbol, trader, market_id, simulate=simulate)
                        await self._record_history(trader, [symbol], "stop_signal", stop_reason)
                        await self._update_status(
                            symbol,
                            running=False,
                            message="停止信号已触发，仓位已清空",
                            last_tick_at=_now_iso(),
                            market_id=market_id,
                            mid=str(mid),
                            center=str(center),
                            desired=0,
                            existing=0,
                            reduce_mode=reduce_mode,
                            stop_signal=True,
                            stop_reason=stop_reason,
                        )
                        self._logbus.publish(f"bot.stop.final symbol={symbol} reason=position_clear")
                        return

                    pnl = await self._position_pnl(trader, market_id, symbol, simulate=simulate)
                    if pnl is not None and pnl >= 0:
                        await self._cancel_grid_orders(symbol, trader, market_id, simulate=simulate)
                        if simulate_fill:
                            self._sim_market_close(symbol, mid)
                        elif not simulate:
                            await self._market_close_position(symbol, trader, market_id, pos_base, meta)
                        await self._record_history(trader, [symbol], "stop_signal", stop_reason)
                        await self._update_status(
                            symbol,
                            running=False,
                            message="停止信号已触发，盈亏>=0 市价全平",
                            last_tick_at=_now_iso(),
                            market_id=market_id,
                            mid=str(mid),
                            center=str(center),
                            desired=0,
                            existing=0,
                            reduce_mode=reduce_mode,
                            stop_signal=True,
                            stop_reason=stop_reason,
                        )
                        self._logbus.publish(f"bot.stop.final symbol={symbol} reason=market_close")
                        return

                prefix = grid_prefix(trader.account_key, market_id, symbol)
                if simulate:
                    existing_orders = self.sim_orders(symbol)
                else:
                    existing_orders = await trader.active_orders(market_id)
                existing: Dict[int, Any] = {}
                asks_by_price: Dict[Decimal, list[Any]] = {}
                bids_by_price: Dict[Decimal, list[Any]] = {}
                ask_used_levels: set[int] = set()
                bid_used_levels: set[int] = set()

                for o in existing_orders:
                    cid = _order_client_id(o)
                    if cid is None or cid <= 0:
                        continue
                    if not is_grid_client_order(prefix, cid):
                        continue
                    existing[cid] = o
                    side = _order_side(o)
                    if side is None:
                        continue
                    price = _order_price_decimal(o, meta)
                    price_q = _quantize(price, meta.price_decimals, ROUND_HALF_UP)
                    if side == "ask":
                        asks_by_price.setdefault(price_q, []).append(o)
                    else:
                        bids_by_price.setdefault(price_q, []).append(o)
                    lvl = grid_client_order_side_level(cid)
                    if lvl:
                        if lvl[0] == "ask":
                            ask_used_levels.add(lvl[1])
                        elif lvl[0] == "bid":
                            bid_used_levels.add(lvl[1])

                levels_up = int(strat.get("levels_up") or 0)
                levels_down = int(strat.get("levels_down") or 0)
                if grid_mode == GRID_MODE_AS:
                    levels_up = 1
                    levels_down = 1
                else:
                    levels_up = max(0, min(levels_up, MAX_LEVEL_PER_SIDE))
                    levels_down = max(0, min(levels_down, MAX_LEVEL_PER_SIDE))

                size_mode = str(strat.get("order_size_mode") or "notional")
                size_value = _safe_decimal(strat.get("order_size_value") or 0)
                post_only = bool(strat.get("post_only", True))
                max_open_orders = int(strat.get("max_open_orders") or 0)

                ask_count = sum(len(v) for v in asks_by_price.values())
                bid_count = sum(len(v) for v in bids_by_price.values())
                total_existing = ask_count + bid_count

                desired_asks: list[Decimal] = []
                desired_bids: list[Decimal] = []
                for i in range(1, levels_up + 1):
                    p = center + (step * i)
                    p = _quantize(p, meta.price_decimals, ROUND_HALF_UP)
                    if p > 0:
                        desired_asks.append(p)
                for i in range(1, levels_down + 1):
                    p = center - (step * i)
                    p = _quantize(p, meta.price_decimals, ROUND_HALF_UP)
                    if p > 0:
                        desired_bids.append(p)
                desired_asks = _unique_prices(desired_asks)
                desired_bids = _unique_prices(desired_bids)
                desired_ask_set = set(desired_asks)
                desired_bid_set = set(desired_bids)

                cancel_orders: list[tuple[Any, Decimal]] = []
                keep_ask_prices: set[Decimal] = set()
                if grid_mode == GRID_MODE_AS:
                    target = desired_asks[0] if desired_asks else None
                    for price, orders in asks_by_price.items():
                        if target is not None and price == target:
                            keep_ask_prices.add(price)
                            if len(orders) > 1:
                                for extra in orders[1:]:
                                    cancel_orders.append((extra, price))
                            continue
                        for o in orders:
                            cancel_orders.append((o, price))
                elif desired_asks:
                    ask_max = max(desired_asks)
                    for price, orders in asks_by_price.items():
                        if price in desired_ask_set:
                            keep_ask_prices.add(price)
                            if len(orders) > 1:
                                for extra in orders[1:]:
                                    cancel_orders.append((extra, price))
                            continue
                        if price > ask_max:
                            for o in orders:
                                cancel_orders.append((o, price))
                else:
                    for price, orders in asks_by_price.items():
                        for o in orders:
                            cancel_orders.append((o, price))

                keep_bid_prices: set[Decimal] = set()
                if grid_mode == GRID_MODE_AS:
                    target = desired_bids[0] if desired_bids else None
                    for price, orders in bids_by_price.items():
                        if target is not None and price == target:
                            keep_bid_prices.add(price)
                            if len(orders) > 1:
                                for extra in orders[1:]:
                                    cancel_orders.append((extra, price))
                            continue
                        for o in orders:
                            cancel_orders.append((o, price))
                elif desired_bids:
                    bid_min = min(desired_bids)
                    for price, orders in bids_by_price.items():
                        if price in desired_bid_set:
                            keep_bid_prices.add(price)
                            if len(orders) > 1:
                                for extra in orders[1:]:
                                    cancel_orders.append((extra, price))
                            continue
                        if price < bid_min:
                            for o in orders:
                                cancel_orders.append((o, price))
                else:
                    for price, orders in bids_by_price.items():
                        for o in orders:
                            cancel_orders.append((o, price))

                missing_ask_prices = [p for p in desired_asks if p not in keep_ask_prices]
                missing_bid_prices = [p for p in desired_bids if p not in keep_bid_prices]
                missing_asks = len(missing_ask_prices)
                missing_bids = len(missing_bid_prices)

                delay_count = self._delay_counts.get(symbol, 0)
                if grid_mode == GRID_MODE_DYNAMIC:
                    delay_marks = self._delay_price_marks.get(symbol)
                    if delay_marks is None:
                        delay_marks = set()
                        self._delay_price_marks[symbol] = delay_marks
                    active_missing: set[str] = set()
                    for price in missing_ask_prices:
                        price_q = _quantize(price, meta.price_decimals, ROUND_HALF_UP)
                        key = f"ask:{price_q}"
                        active_missing.add(key)
                        if mid >= price_q and key not in delay_marks:
                            delay_marks.add(key)
                            delay_count += 1
                    for price in missing_bid_prices:
                        price_q = _quantize(price, meta.price_decimals, ROUND_HALF_UP)
                        key = f"bid:{price_q}"
                        active_missing.add(key)
                        if mid <= price_q and key not in delay_marks:
                            delay_marks.add(key)
                            delay_count += 1
                    if delay_marks:
                        delay_marks.intersection_update(active_missing)
                    self._delay_counts[symbol] = delay_count
                else:
                    self._delay_price_marks.pop(symbol, None)

                if cancel_orders or (missing_asks + missing_bids) > 0:
                    self._logbus.publish(
                        f"grid.reconcile symbol={symbol} market_id={market_id} existing={total_existing} cancel={len(cancel_orders)} missing_asks={missing_asks} missing_bids={missing_bids}"
                    )

                remaining_after_cancel = max(0, total_existing - len(cancel_orders))
                available_slots = missing_asks + missing_bids
                if max_open_orders > 0:
                    available_slots = max(0, max_open_orders - remaining_after_cancel)

                if cancel_orders:
                    for o, price_q in cancel_orders:
                        order_index = _order_id(o)
                        client_index = _order_client_id(o) or 0
                        if order_index is None or (isinstance(order_index, int) and order_index <= 0):
                            self._logbus.publish(
                                f"order.cancel.error symbol={symbol} market_id={market_id} client_id={client_index} err=missing_order_index"
                            )
                            continue
                        if simulate:
                            try:
                                order_id = int(order_index)
                            except Exception:
                                self._logbus.publish(
                                    f"sim.cancel.error symbol={symbol} market_id={market_id} client_id={client_index} err=bad_order_id"
                                )
                                continue
                            self._sim_cancel_order(symbol, order_id)
                            self._logbus.publish(
                                f"sim.cancel symbol={symbol} market_id={market_id} order={order_id} client_id={client_index} price={price_q}"
                            )
                        elif dry_run:
                            self._logbus.publish(
                                f"dry_run cancel symbol={symbol} market_id={market_id} order={order_index} client_id={client_index} price={price_q}"
                            )
                        else:
                            try:
                                await trader.cancel_order(market_id, order_index)
                                self._logbus.publish(
                                    f"order.cancel symbol={symbol} market_id={market_id} order={order_index} client_id={client_index}"
                                )
                            except Exception as exc:
                                self._logbus.publish(
                                    f"order.cancel.error symbol={symbol} market_id={market_id} order={order_index} err={type(exc).__name__}:{exc}"
                                )

                created_attempts = 0
                create_block_reasons: set[str] = set()
                create_block_tip = ""
                if available_slots > 0 and (missing_asks + missing_bids) > 0:
                    plan_candidates: list[tuple[Decimal, str, Decimal]] = []
                    for price in missing_ask_prices:
                        plan_candidates.append((abs(price - center), "ask", price))
                    for price in missing_bid_prices:
                        plan_candidates.append((abs(price - center), "bid", price))
                    plan_candidates.sort(key=lambda item: (item[0], 0 if item[1] == "ask" else 1))
                    create_plan: list[tuple[str, Decimal]] = [
                        (side, price) for _, side, price in plan_candidates[:available_slots]
                    ]

                    free_ask_levels = [i for i in range(1, MAX_LEVEL_PER_SIDE + 1) if i not in ask_used_levels]
                    free_bid_levels = [i for i in range(1, MAX_LEVEL_PER_SIDE + 1) if i not in bid_used_levels]

                    for side, price in create_plan:
                        if price <= 0:
                            continue
                        if side == "ask":
                            if not free_ask_levels:
                                self._logbus.publish(f"grid.no_free_id symbol={symbol} side=ask")
                                continue
                            if isinstance(trader, GrvtTrader):
                                level = self._pick_level_with_cursor(symbol, "ask", free_ask_levels)
                                if level is None:
                                    self._logbus.publish(f"grid.no_free_id symbol={symbol} side=ask")
                                    continue
                                free_ask_levels.remove(level)
                            else:
                                level = free_ask_levels.pop(0)
                        else:
                            if not free_bid_levels:
                                self._logbus.publish(f"grid.no_free_id symbol={symbol} side=bid")
                                continue
                            if isinstance(trader, GrvtTrader):
                                level = self._pick_level_with_cursor(symbol, "bid", free_bid_levels)
                                if level is None:
                                    self._logbus.publish(f"grid.no_free_id symbol={symbol} side=bid")
                                    continue
                                free_bid_levels.remove(level)
                            else:
                                level = free_bid_levels.pop(0)

                        price_q = _quantize(price, meta.price_decimals, ROUND_HALF_UP)
                        size_value_effective = size_value
                        if reduce_mode and reduce_side == side and reduce_mult > 1:
                            size_value_effective = size_value * reduce_mult
                        base_qty = _calc_base_qty(size_mode, size_value_effective, price_q)
                        base_qty_q = _quantize(base_qty, meta.size_decimals, ROUND_DOWN)
                        if base_qty_q <= 0:
                            create_block_reasons.add("qty_non_positive")
                            continue
                        if base_qty_q < meta.min_base_amount:
                            create_block_reasons.add(f"below_min_base[{base_qty_q}<{meta.min_base_amount}]")
                            continue
                        quote_notional = base_qty_q * price_q
                        if quote_notional < meta.min_quote_amount:
                            create_block_reasons.add(f"below_min_quote[{quote_notional}<{meta.min_quote_amount}]")
                            continue

                        oid = grid_client_order_id(prefix, side, level)
                        if oid in existing:
                            create_block_reasons.add("client_id_collision")
                            continue
                        if oid > CLIENT_ORDER_MAX:
                            create_block_reasons.add("client_id_overflow")
                            continue
                        price_int = _to_scaled_int(price_q, meta.price_decimals, ROUND_HALF_UP)
                        base_int = _to_scaled_int(base_qty_q, meta.size_decimals, ROUND_DOWN)

                        if simulate:
                            self._sim_create_order(
                                symbol,
                                order_index=int(oid),
                                client_order_index=int(oid),
                                price=price_q,
                                base_qty=base_qty_q,
                                is_ask=(side == "ask"),
                                created_at_ms=now_ms,
                            )
                            self._logbus.publish(
                                f"sim.create symbol={symbol} market_id={market_id} id={oid} ask={side == 'ask'} price={price_int} size={base_int}"
                            )
                            created_attempts += 1
                        elif dry_run:
                            self._logbus.publish(
                                f"dry_run create symbol={symbol} market_id={market_id} id={oid} ask={side == 'ask'} price={price_int} size={base_int}"
                            )
                            created_attempts += 1
                        else:
                            try:
                                await trader.create_limit_order(
                                    market_id=market_id,
                                    client_order_index=oid,
                                    base_amount=int(base_int),
                                    price=int(price_int),
                                    is_ask=(side == "ask"),
                                    post_only=post_only,
                                )
                                self._logbus.publish(f"order.create symbol={symbol} market_id={market_id} id={oid}")
                                created_attempts += 1
                            except Exception as exc:
                                self._logbus.publish(f"order.create.error symbol={symbol} id={oid} err={type(exc).__name__}:{exc}")
                if created_attempts > 0:
                    self._create_block_notice.pop(symbol, None)
                elif create_block_reasons:
                    create_block_tip = sorted(create_block_reasons)[0]
                    reason_text = ",".join(sorted(create_block_reasons))
                    prev = self._create_block_notice.get(symbol)
                    should_log = True
                    if prev:
                        prev_ms, prev_reason = prev
                        if prev_reason == reason_text and (now_ms - prev_ms) < 3000:
                            should_log = False
                    if should_log:
                        self._logbus.publish(
                            "order.create.blocked "
                            f"symbol={symbol} market_id={market_id} "
                            f"size_mode={size_mode} size_value={size_value} "
                            f"min_base={meta.min_base_amount} min_quote={meta.min_quote_amount} "
                            f"reasons={reason_text}"
                        )
                    self._create_block_notice[symbol] = (now_ms, reason_text)

                if cancel_orders or created_attempts > 0:
                    self._logbus.publish(
                        f"grid.reconcile.done symbol={symbol} market_id={market_id} canceled={len(cancel_orders)} created={created_attempts}"
                    )

                if simulate_fill:
                    msg = "模拟成交"
                else:
                    msg = "模拟运行" if dry_run else "实盘运行"
                if reduce_mode:
                    suffix = "减仓模式"
                    if pos_notional is not None:
                        suffix = f"{suffix} 仓位={pos_notional:.4f}"
                    msg = f"{msg} | {suffix}"
                if stop_signal:
                    stop_tip = "停止信号"
                    if stop_reason:
                        stop_tip = f"停止信号:{stop_reason}"
                    msg = f"{msg} | {stop_tip}"
                if create_block_tip:
                    msg = f"{msg} | blocked:{create_block_tip}"
                await self._update_status(
                    symbol,
                    running=True,
                    message=msg,
                    last_tick_at=_now_iso(),
                    market_id=market_id,
                    mid=str(mid),
                    center=str(center),
                    desired=(len(desired_asks) + len(desired_bids)),
                    existing=len(existing),
                    delay_count=delay_count,
                    reduce_mode=reduce_mode,
                    stop_signal=stop_signal,
                    stop_reason=stop_reason,
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._logbus.publish(f"bot.error symbol={symbol} err={type(exc).__name__}:{exc}")
            await self._update_status(symbol, running=False, message="异常退出", last_tick_at=_now_iso())
            await self._schedule_restart(symbol, trader)

    async def _trade_stats_since(
        self, trader: Trader, market_id: str | int, start_ms: int, end_ms: int
    ) -> tuple[Decimal, int]:
        if isinstance(trader, LighterTrader):
            return await self._lighter_trades_since(trader, int(market_id), start_ms)
        if isinstance(trader, ParadexTrader):
            return self._paradex_fills_since(trader, str(market_id), start_ms, end_ms)
        if isinstance(trader, GrvtTrader):
            return await trader.fills_since(str(market_id), start_ms, end_ms)
        return Decimal(0), 0

    async def _lighter_trades_since(
        self,
        trader: LighterTrader,
        market_id: int,
        start_ms: int,
        max_pages: int = 5,
    ) -> tuple[Decimal, int]:
        total = Decimal(0)
        count = 0
        auth_token = await trader.auth_token()
        cursor = None
        pages = 0
        reached_old = False
        while pages < max_pages and not reached_old:
            resp = await trader._call_with_retry(
                trader._order_api.trades,
                sort_by="timestamp",
                limit=100,
                market_id=int(market_id),
                account_index=int(trader.account_index),
                sort_dir="desc",
                cursor=cursor,
                auth=auth_token,
            )
            trades = getattr(resp, "trades", None)
            if trades is None and isinstance(resp, dict):
                trades = resp.get("trades")
            trades = trades or []
            for t in trades:
                ts = _trade_ts_ms(_order_field(t, "timestamp"))
                if ts is not None and ts < start_ms:
                    reached_old = True
                    break
                usd_amount = _safe_decimal(_order_field(t, "usd_amount") or 0)
                if usd_amount == 0:
                    price = _safe_decimal(_order_field(t, "price") or 0)
                    size = _safe_decimal(_order_field(t, "size") or 0)
                    usd_amount = price * size
                total += abs(usd_amount)
                count += 1
            cursor = getattr(resp, "next_cursor", None) if not isinstance(resp, dict) else resp.get("next_cursor")
            if not cursor:
                break
            pages += 1
        return total, count

    async def _lighter_update_trade_pnl(
        self,
        trader: LighterTrader,
        symbol: str,
        market_id: int,
        start_ms: int,
        end_ms: int,
        max_pages: int = 20,
    ) -> TradePnlState:
        state = self._trade_pnl_state(symbol)
        if state.last_ts_ms <= 0 or state.last_ts_ms < start_ms:
            state.last_ts_ms = start_ms - 1

        auth_token = await trader.auth_token()
        cursor = None
        pages = 0
        processed = 0
        while pages < max_pages:
            resp = await trader._call_with_retry(
                trader._order_api.trades,
                sort_by="timestamp",
                limit=200,
                market_id=int(market_id),
                account_index=int(trader.account_index),
                sort_dir="asc",
                cursor=cursor,
                auth=auth_token,
            )
            trades = getattr(resp, "trades", None)
            if trades is None and isinstance(resp, dict):
                trades = resp.get("trades")
            trades = trades or []
            for t in trades:
                ts = _trade_ts_ms(_order_field(t, "timestamp"))
                if ts is None:
                    continue
                if ts <= state.last_ts_ms:
                    continue
                if ts < start_ms or ts > end_ms:
                    continue
                side = _order_side(t)
                if side is None:
                    continue
                price = _safe_decimal(_order_field(t, "price") or 0)
                size = _safe_decimal(_order_field(t, "size") or _order_field(t, "base_amount") or _order_field(t, "amount") or 0)
                if price <= 0 or size <= 0:
                    continue
                self._apply_trade_pnl(state, side, price, size)
                state.last_ts_ms = max(state.last_ts_ms, ts)
                processed += 1

            cursor = getattr(resp, "next_cursor", None) if not isinstance(resp, dict) else resp.get("next_cursor")
            if not cursor:
                break
            pages += 1

        if pages >= max_pages and cursor:
            self._logbus.publish(f"lighter.trade_pnl.truncated symbol={symbol} market_id={market_id}")
        if processed:
            self._logbus.publish(
                f"lighter.trade_pnl.update symbol={symbol} market_id={market_id} trades={processed} last_ts={state.last_ts_ms}"
            )
        return state

    def _paradex_fills_since(
        self,
        trader: ParadexTrader,
        market: str,
        start_ms: int,
        end_ms: int,
        max_pages: int = 5,
    ) -> tuple[Decimal, int]:
        total = Decimal(0)
        count = 0
        cursor = None
        pages = 0
        while pages < max_pages:
            params: Dict[str, Any] = {"market": market, "start_at": int(start_ms), "end_at": int(end_ms), "page_size": 200}
            if cursor:
                params["cursor"] = cursor
            data = trader._api.fetch_fills(params)
            results = list(data.get("results") or [])
            for item in results:
                if not isinstance(item, dict):
                    continue
                price = _safe_decimal(item.get("price") or 0)
                size = _safe_decimal(item.get("size") or 0)
                total += abs(price * size)
                count += 1
            cursor = data.get("next") or data.get("next_cursor")
            if not cursor:
                break
            pages += 1
        return total, count

    async def _position_pnl(
        self,
        trader: Trader,
        market_id: str | int,
        symbol: str,
        simulate: bool = False,
    ) -> Optional[Decimal]:
        now_ms = _now_ms()
        if not simulate:
            cached = self._pnl_cache.get(symbol)
            if cached and (now_ms - cached[0]) <= 2000:
                return cached[1]

        pnl: Optional[Decimal] = None
        if simulate:
            pnl = self.sim_pnl(symbol)
        elif isinstance(trader, LighterTrader):
            resp = await trader._account_api.account(by="index", value=str(int(trader.account_index)))
            if hasattr(resp, "model_dump"):
                data = resp.model_dump()
            elif hasattr(resp, "to_dict"):
                data = resp.to_dict()
            else:
                data = getattr(resp, "__dict__", {})

            positions = []
            if isinstance(data, dict):
                accounts = data.get("accounts")
                if isinstance(accounts, list) and accounts:
                    first = accounts[0] or {}
                    if isinstance(first, dict):
                        positions = first.get("positions") or []
                elif isinstance(data.get("positions"), list):
                    positions = data.get("positions") or []

            target_id = int(market_id)
            for pos in positions or []:
                if not isinstance(pos, dict):
                    continue
                mid = pos.get("market_id")
                try:
                    mid = int(mid)
                except Exception:
                    continue
                if mid != target_id:
                    continue
                pnl = _safe_decimal(pos.get("realized_pnl") or 0) + _safe_decimal(pos.get("unrealized_pnl") or 0)
                break
        elif isinstance(trader, ParadexTrader):
            data = trader._api.fetch_positions()
            results = list(data.get("results") or [])
            target = str(market_id)
            for item in results:
                if not isinstance(item, dict):
                    continue
                if str(item.get("market") or "") != target:
                    continue
                pnl = _safe_decimal(item.get("realized_positional_pnl") or 0) + _safe_decimal(item.get("unrealized_pnl") or 0)
                break
        elif isinstance(trader, GrvtTrader):
            positions = await trader.positions_snapshot()
            item = positions.get(str(market_id))
            if item:
                pnl = _safe_decimal(item.get("pnl"))

        if pnl is not None and not simulate:
            self._pnl_cache[symbol] = (now_ms, pnl)
        return pnl

    async def _market_close_position(
        self,
        symbol: str,
        trader: Trader,
        market_id: str | int,
        pos_base: Decimal,
        meta: MarketMeta,
    ) -> None:
        if pos_base == 0:
            return
        side = "ask" if pos_base > 0 else "bid"
        base_qty = abs(pos_base)
        base_int = _to_scaled_int(base_qty, meta.size_decimals, ROUND_HALF_UP)
        if base_int <= 0:
            return
        try:
            await trader.create_market_order(
                market_id=market_id,
                base_amount=int(base_int),
                is_ask=(side == "ask"),
                reduce_only=True,
            )
            self._logbus.publish(f"order.market_close symbol={symbol} market_id={market_id} side={side} size={base_int}")
        except Exception as exc:
            self._logbus.publish(
                f"order.market_close.error symbol={symbol} market_id={market_id} err={type(exc).__name__}:{exc}"
            )

    async def _cancel_grid_orders(
        self,
        symbol: str,
        trader: Trader,
        market_id: str | int,
        simulate: bool = False,
    ) -> None:
        if simulate:
            state = self._sim_state(symbol)
            canceled = len(state.orders)
            state.orders.clear()
            if canceled:
                self._logbus.publish(f"sim.cancel.done symbol={symbol} market_id={market_id} canceled={canceled}")
            return

        prefix = grid_prefix(trader.account_key, market_id, symbol)
        try:
            orders = await trader.active_orders(market_id)
        except Exception as exc:
            self._logbus.publish(f"stop.cancel.list.error symbol={symbol} market_id={market_id} err={type(exc).__name__}:{exc}")
            return

        canceled = 0
        for o in orders:
            cid = _order_client_id(o)
            if cid is None or cid <= 0:
                continue
            if not is_grid_client_order(prefix, cid):
                continue
            oid = _order_id(o)
            if oid is None:
                continue
            if isinstance(oid, int) and oid <= 0:
                continue
            try:
                await trader.cancel_order(market_id, oid)
                canceled += 1
            except Exception as exc:
                self._logbus.publish(
                    f"stop.cancel.error symbol={symbol} market_id={market_id} id={cid} err={type(exc).__name__}:{exc}"
                )
        if canceled:
            self._logbus.publish(f"stop.cancel.done symbol={symbol} market_id={market_id} canceled={canceled}")

    async def capture_history(self, trader: Trader, symbols: list[str], reason: str) -> None:
        await self._record_history(trader, symbols, reason, "")

    async def _record_history(
        self,
        trader: Trader,
        symbols: list[str],
        reason: str,
        stop_reason: str,
    ) -> None:
        record, recorded = await self._build_history_record(trader, symbols, reason, stop_reason)
        if not record:
            return
        try:
            self._history.append(record)
        except Exception as exc:
            self._logbus.publish(f"history.append.error err={type(exc).__name__}:{exc}")
            return
        async with self._lock:
            for symbol in recorded:
                self._history_recorded.add(symbol)

    async def _build_history_record(
        self,
        trader: Trader,
        symbols: list[str],
        reason: str,
        stop_reason: str,
    ) -> tuple[Optional[Dict[str, Any]], list[str]]:
        cfg = self._config.read()
        simulate = self._sim_enabled(cfg.get("runtime", {}) or {})
        exchange = "paradex" if isinstance(trader, ParadexTrader) else "lighter"
        now_iso = _now_iso()
        now_ms = _now_ms()
        totals_profit = Decimal(0)
        totals_volume = Decimal(0)
        totals_trades = 0
        totals_position = Decimal(0)
        totals_orders = 0
        reduce_symbols: list[str] = []
        symbols_data: Dict[str, Any] = {}
        recorded_symbols: list[str] = []

        for symbol in symbols:
            sym = symbol.upper()
            async with self._lock:
                if sym in self._history_recorded:
                    continue
                status = self._status.get(sym)
                if not status or not status.running:
                    continue
                started_at = status.started_at
                start_ms = self._start_ms.get(sym) or _parse_iso_ms(started_at) or now_ms
                self._start_ms[sym] = int(start_ms)

            data = await self._symbol_runtime_snapshot(trader, sym, status, int(start_ms), now_ms, simulate)
            if not data:
                continue
            symbols_data[sym] = data
            recorded_symbols.append(sym)

            profit_v = _safe_decimal(data.get("profit") or 0)
            volume_v = _safe_decimal(data.get("volume") or 0)
            position_v = _safe_decimal(data.get("position_notional") or 0)
            totals_profit += profit_v
            totals_volume += volume_v
            totals_trades += int(data.get("trade_count") or 0)
            totals_position += position_v
            totals_orders += int(data.get("open_orders") or 0)
            if data.get("reduce_mode"):
                reduce_symbols.append(sym)

        if not symbols_data:
            return None, []

        record: Dict[str, Any] = {
            "created_at": now_iso,
            "exchange": exchange,
            "reason": reason,
            "stop_reason": stop_reason,
            "totals": {
                "profit": _fmt_decimal(totals_profit),
                "volume": _fmt_decimal(totals_volume),
                "trade_count": totals_trades,
                "position_notional": _fmt_decimal(totals_position),
                "open_orders": totals_orders,
                "reduce_symbols": reduce_symbols,
                "running": len(symbols_data),
            },
            "symbols": symbols_data,
        }
        return record, recorded_symbols

    async def _symbol_runtime_snapshot(
        self,
        trader: Trader,
        symbol: str,
        status: BotStatus,
        start_ms: int,
        now_ms: int,
        simulate: bool = False,
    ) -> Optional[Dict[str, Any]]:
        cfg = self._config.read()
        strat = (cfg.get("strategies", {}) or {}).get(symbol, {}) or {}
        market_id = strat.get("market_id")
        if market_id is None or (isinstance(market_id, str) and not market_id.strip()):
            market_id = status.market_id
        if market_id is None or (isinstance(market_id, str) and not str(market_id).strip()):
            return None

        if isinstance(trader, ParadexTrader):
            market_id = str(market_id)
        elif isinstance(trader, LighterTrader) and isinstance(market_id, str):
            try:
                market_id = int(market_id)
            except Exception:
                pass

        pnl_now: Optional[Decimal] = None
        use_base = True
        if simulate:
            pnl_now = self.sim_pnl(symbol)
            use_base = False
        elif isinstance(trader, LighterTrader):
            use_base = False
        else:
            pnl_now = await self._position_pnl(trader, market_id, symbol, simulate=simulate)
        if pnl_now is None:
            pnl_now = Decimal(0)

        volume = Decimal(0)
        trade_count = 0
        try:
            if simulate:
                volume, trade_count = self.sim_trade_stats(symbol, start_ms, now_ms)
            else:
                volume, trade_count = await self._trade_stats_since(trader, market_id, start_ms, now_ms)
        except Exception as exc:
            self._logbus.publish(
                f"history.trades.error symbol={symbol} market_id={market_id} err={type(exc).__name__}:{exc}"
            )

        pos_base = Decimal(0)
        if simulate:
            pos_base = self.sim_position_base(symbol)
        else:
            try:
                pos_base = await trader.position_base(market_id)
            except Exception:
                pos_base = Decimal(0)

        mid_value = _safe_decimal(status.mid or 0)
        if mid_value <= 0 and simulate:
            mid_value = self.sim_last_mid(symbol)
        if mid_value <= 0:
            try:
                bid, ask = await trader.best_bid_ask(market_id)
                if bid is not None and ask is not None:
                    mid_value = (bid + ask) / 2
            except Exception:
                mid_value = Decimal(0)

        if isinstance(trader, LighterTrader) and not simulate:
            try:
                state = await self._lighter_update_trade_pnl(trader, symbol, int(market_id), start_ms, now_ms)
                pnl_now = self._trade_pnl_value(state, mid_value)
            except Exception as exc:
                self._logbus.publish(
                    f"lighter.trade_pnl.error symbol={symbol} market_id={market_id} err={type(exc).__name__}:{exc}"
                )
                fallback = await self._position_pnl(trader, market_id, symbol, simulate=simulate)
                if fallback is not None:
                    pnl_now = fallback

        if use_base:
            base_pnl = self._base_pnl.get(symbol)
            if base_pnl is None:
                self._base_pnl[symbol] = pnl_now
                base_pnl = pnl_now
            profit = pnl_now - _safe_decimal(base_pnl)
        else:
            profit = pnl_now

        position_notional = abs(pos_base * mid_value) if mid_value > 0 else Decimal(0)
        open_orders = self.sim_open_orders(symbol) if simulate else int(status.existing or 0)
        reduce_mode = bool(status.reduce_mode)

        return {
            "symbol": symbol,
            "market_id": market_id,
            "started_at": status.started_at,
            "profit": _fmt_decimal(profit),
            "volume": _fmt_decimal(volume),
            "trade_count": trade_count,
            "position_notional": _fmt_decimal(position_notional),
            "open_orders": open_orders,
            "reduce_mode": reduce_mode,
        }

    async def _schedule_restart(self, symbol: str, trader: Trader) -> None:
        cfg = self._config.read()
        runtime = cfg.get("runtime", {}) or {}
        if not bool(runtime.get("auto_restart", True)):
            return

        delay_ms = _safe_int(runtime.get("restart_delay_ms"), 1000)
        max_times = _safe_int(runtime.get("restart_max"), 5)
        window_ms = _safe_int(runtime.get("restart_window_ms"), 60000)
        if delay_ms < 0:
            delay_ms = 0
        delay_s = max(0.05, delay_ms / 1000.0)

        now_ms = _now_ms()
        limit_reached = False
        attempts = 0
        async with self._lock:
            if symbol in self._manual_stop:
                return
            times = list(self._restart_times.get(symbol) or [])
            if window_ms > 0:
                times = [t for t in times if now_ms - t <= window_ms]
            times.append(now_ms)
            self._restart_times[symbol] = times
            attempts = len(times)
            if max_times > 0 and attempts > max_times:
                limit_reached = True
            else:
                task = self._restart_tasks.get(symbol)
                if task and not task.done():
                    return
                self._restart_tasks[symbol] = asyncio.create_task(
                    self._restart_after_delay(symbol, trader, delay_s)
                )

        if limit_reached:
            self._logbus.publish(f"bot.restart.limit symbol={symbol} count={attempts}")
            await self._update_status(symbol, running=False, message="自动重连已达上限", last_tick_at=_now_iso())

    async def _restart_after_delay(self, symbol: str, trader: Trader, delay_s: float) -> None:
        try:
            await asyncio.sleep(delay_s)
            cfg = self._config.read()
            runtime = cfg.get("runtime", {}) or {}
            if not bool(runtime.get("auto_restart", True)):
                return
            async with self._lock:
                if symbol in self._manual_stop:
                    return
                task = self._tasks.get(symbol)
                if task and not task.done():
                    return
            await self.start(symbol, trader, manual=False)
            self._logbus.publish(f"bot.restart symbol={symbol}")
        except asyncio.CancelledError:
            raise
        finally:
            async with self._lock:
                task = self._restart_tasks.get(symbol)
                if task is asyncio.current_task():
                    self._restart_tasks.pop(symbol, None)

    async def _update_status(self, symbol: str, **patch: Any) -> None:
        async with self._lock:
            current = self._status.get(symbol) or BotStatus(symbol=symbol, running=False)
            data = current.to_dict()
            data.update(patch)
            self._status[symbol] = BotStatus(**data)
