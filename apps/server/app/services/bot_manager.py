from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Any, Dict, Optional

from app.core.config_store import ConfigStore
from app.core.logbus import LogBus
from app.exchanges.lighter.trader import LighterTrader, MarketMeta
from app.strategies.grid.ids import (
    CLIENT_ORDER_MAX,
    MAX_LEVEL_PER_SIDE,
    grid_client_order_id,
    grid_client_order_side_level,
    grid_prefix,
    is_grid_client_order,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


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


def _calc_base_qty(mode: str, value: Decimal, price: Decimal) -> Decimal:
    if mode == "base":
        return value
    if price <= 0:
        return Decimal(0)
    return value / price


def _order_price_decimal(order: Any, meta: MarketMeta) -> Decimal:
    price = getattr(order, "price", None)
    if price is not None:
        try:
            return Decimal(str(price))
        except Exception:
            pass
    base_price = getattr(order, "base_price", 0)
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


@dataclass
class BotStatus:
    symbol: str
    running: bool
    started_at: Optional[str] = None
    last_tick_at: Optional[str] = None
    message: str = ""
    market_id: Optional[int] = None
    mid: Optional[str] = None
    center: Optional[str] = None
    desired: int = 0
    existing: int = 0

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
        }


class BotManager:
    def __init__(self, logbus: LogBus, config: ConfigStore) -> None:
        self._logbus = logbus
        self._config = config
        self._tasks: Dict[str, asyncio.Task[None]] = {}
        self._status: Dict[str, BotStatus] = {}
        self._lock = asyncio.Lock()

    async def start(self, symbol: str, trader: LighterTrader) -> None:
        symbol = symbol.upper()
        async with self._lock:
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

    async def stop(self, symbol: str) -> None:
        symbol = symbol.upper()
        async with self._lock:
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
            prev = self._status.get(symbol)
            self._status[symbol] = BotStatus(symbol=symbol, running=False, message="已停止", started_at=prev.started_at if prev else None)
        self._logbus.publish(f"bot.stop symbol={symbol}")

    async def stop_all(self) -> None:
        symbols = list(self._tasks.keys())
        for symbol in symbols:
            await self.stop(symbol)

    def snapshot(self) -> Dict[str, Any]:
        return {k: v.to_dict() for k, v in self._status.items()}

    async def _run(self, symbol: str, trader: LighterTrader) -> None:
        interval_s = 0.1
        try:
            while True:
                await asyncio.sleep(interval_s)
                cfg = self._config.read()
                runtime = cfg.get("runtime", {})
                dry_run = bool(runtime.get("dry_run", True))
                interval_ms = runtime.get("loop_interval_ms", 100)
                try:
                    interval_ms = float(interval_ms)
                except Exception:
                    interval_ms = 100.0
                if interval_ms <= 0:
                    interval_ms = 100.0
                interval_s = max(0.01, interval_ms / 1000.0)
                strat = (cfg.get("strategies", {}) or {}).get(symbol, {}) or {}

                if not bool(strat.get("enabled", True)):
                    await self._update_status(symbol, running=True, message="已禁用", last_tick_at=_now_iso())
                    continue

                market_id = strat.get("market_id")
                if not isinstance(market_id, int):
                    await self._update_status(symbol, running=True, message="未配置 market_id", last_tick_at=_now_iso())
                    continue

                step = _safe_decimal(strat.get("grid_step") or 0)
                if step <= 0:
                    await self._update_status(symbol, running=True, message="grid_step 必须大于 0", last_tick_at=_now_iso(), market_id=market_id)
                    continue

                meta = await trader.market_meta(market_id)
                bid, ask = await trader.best_bid_ask(market_id)
                if bid is None or ask is None:
                    await self._update_status(symbol, running=True, message="无法获取盘口", last_tick_at=_now_iso(), market_id=market_id)
                    continue

                mid = (bid + ask) / 2
                center = (mid / step).to_integral_value(rounding=ROUND_HALF_UP) * step
                center = _quantize(center, meta.price_decimals, ROUND_HALF_UP)

                prefix = grid_prefix(trader.account_index, market_id, symbol)
                existing_orders = await trader.active_orders(market_id)
                existing: Dict[int, Any] = {}
                asks_by_price: Dict[Decimal, list[Any]] = {}
                bids_by_price: Dict[Decimal, list[Any]] = {}
                ask_used_levels: set[int] = set()
                bid_used_levels: set[int] = set()

                for o in existing_orders:
                    cid = int(getattr(o, "client_order_index", 0) or 0)
                    if cid <= 0:
                        continue
                    if not is_grid_client_order(prefix, cid):
                        continue
                    existing[cid] = o
                    side = "ask" if bool(getattr(o, "is_ask", False)) else "bid"
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
                for price, orders in asks_by_price.items():
                    if price in desired_ask_set:
                        keep_ask_prices.add(price)
                        if len(orders) > 1:
                            for extra in orders[1:]:
                                cancel_orders.append((extra, price))
                    else:
                        for o in orders:
                            cancel_orders.append((o, price))

                keep_bid_prices: set[Decimal] = set()
                for price, orders in bids_by_price.items():
                    if price in desired_bid_set:
                        keep_bid_prices.add(price)
                        if len(orders) > 1:
                            for extra in orders[1:]:
                                cancel_orders.append((extra, price))
                    else:
                        for o in orders:
                            cancel_orders.append((o, price))

                missing_ask_prices = [p for p in desired_asks if p not in keep_ask_prices]
                missing_bid_prices = [p for p in desired_bids if p not in keep_bid_prices]
                missing_asks = len(missing_ask_prices)
                missing_bids = len(missing_bid_prices)

                remaining_after_cancel = max(0, total_existing - len(cancel_orders))
                available_slots = missing_asks + missing_bids
                if max_open_orders > 0:
                    available_slots = max(0, max_open_orders - remaining_after_cancel)

                if cancel_orders:
                    for o, price_q in cancel_orders:
                        order_index = int(getattr(o, "order_index", 0) or 0)
                        client_index = int(getattr(o, "client_order_index", 0) or 0)
                        if order_index <= 0:
                            self._logbus.publish(
                                f"order.cancel.error symbol={symbol} market_id={market_id} client_id={client_index} err=missing_order_index"
                            )
                            continue
                        if dry_run:
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

                if available_slots > 0 and (missing_asks + missing_bids) > 0:
                    create_plan: list[tuple[str, Decimal]] = []
                    a_idx = 0
                    b_idx = 0
                    while len(create_plan) < available_slots and (a_idx < len(missing_ask_prices) or b_idx < len(missing_bid_prices)):
                        if a_idx < len(missing_ask_prices):
                            create_plan.append(("ask", missing_ask_prices[a_idx]))
                            a_idx += 1
                            if len(create_plan) >= available_slots:
                                break
                        if b_idx < len(missing_bid_prices):
                            create_plan.append(("bid", missing_bid_prices[b_idx]))
                            b_idx += 1

                    free_ask_levels = [i for i in range(1, MAX_LEVEL_PER_SIDE + 1) if i not in ask_used_levels]
                    free_bid_levels = [i for i in range(1, MAX_LEVEL_PER_SIDE + 1) if i not in bid_used_levels]

                    for side, price in create_plan:
                        if price <= 0:
                            continue
                        if side == "ask":
                            if not free_ask_levels:
                                self._logbus.publish(f"grid.no_free_id symbol={symbol} side=ask")
                                continue
                            level = free_ask_levels.pop(0)
                        else:
                            if not free_bid_levels:
                                self._logbus.publish(f"grid.no_free_id symbol={symbol} side=bid")
                                continue
                            level = free_bid_levels.pop(0)

                        price_q = _quantize(price, meta.price_decimals, ROUND_HALF_UP)
                        base_qty = _calc_base_qty(size_mode, size_value, price_q)
                        base_qty_q = _quantize(base_qty, meta.size_decimals, ROUND_DOWN)
                        if base_qty_q <= 0:
                            continue
                        if base_qty_q < meta.min_base_amount:
                            continue
                        if (base_qty_q * price_q) < meta.min_quote_amount:
                            continue

                        oid = grid_client_order_id(prefix, side, level)
                        if oid in existing:
                            continue
                        if oid > CLIENT_ORDER_MAX:
                            continue
                        price_int = _to_scaled_int(price_q, meta.price_decimals, ROUND_HALF_UP)
                        base_int = _to_scaled_int(base_qty_q, meta.size_decimals, ROUND_DOWN)

                        if dry_run:
                            self._logbus.publish(
                                f"dry_run create symbol={symbol} market_id={market_id} id={oid} ask={side == 'ask'} price={price_int} size={base_int}"
                            )
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
                            except Exception as exc:
                                self._logbus.publish(f"order.create.error symbol={symbol} id={oid} err={type(exc).__name__}:{exc}")

                msg = "模拟运行" if dry_run else "实盘运行"
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
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._logbus.publish(f"bot.error symbol={symbol} err={type(exc).__name__}:{exc}")
            await self._update_status(symbol, running=False, message="异常退出", last_tick_at=_now_iso())

    async def _update_status(self, symbol: str, **patch: Any) -> None:
        async with self._lock:
            current = self._status.get(symbol) or BotStatus(symbol=symbol, running=False)
            data = current.to_dict()
            data.update(patch)
            self._status[symbol] = BotStatus(**data)
