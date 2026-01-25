from __future__ import annotations

import asyncio
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Any, Dict, Optional

from app.core.config_store import ConfigStore
from app.core.logbus import LogBus
from app.exchanges.lighter.trader import LighterTrader, MarketMeta


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _crc32(text: str) -> int:
    return zlib.crc32(text.encode("utf-8")) & 0x7FFFFFFF


def _bot_prefix(account_index: int, market_id: int, symbol: str) -> int:
    return _crc32(f"{account_index}:{market_id}:{symbol}")


def _bot_base_id(prefix: int) -> int:
    return int(prefix) * 1_000_000


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


def _desired_orders(
    symbol: str,
    market_id: int,
    center: Decimal,
    step: Decimal,
    strat: Dict[str, Any],
    meta: MarketMeta,
    bot_prefix: int,
) -> Dict[int, Dict[str, Any]]:
    levels_up = int(strat.get("levels_up") or 0)
    levels_down = int(strat.get("levels_down") or 0)
    levels_up = max(0, min(levels_up, 50))
    levels_down = max(0, min(levels_down, 50))

    size_mode = str(strat.get("order_size_mode") or "notional")
    size_value = _safe_decimal(strat.get("order_size_value") or 0)
    post_only = bool(strat.get("post_only", True))

    bot_base = _bot_base_id(bot_prefix)
    result: Dict[int, Dict[str, Any]] = {}

    for i in range(1, levels_up + 1):
        price = center + (step * i)
        if price <= 0:
            continue
        price_q = _quantize(price, meta.price_decimals, ROUND_HALF_UP)
        base_qty = _calc_base_qty(size_mode, size_value, price_q)
        base_qty_q = _quantize(base_qty, meta.size_decimals, ROUND_DOWN)
        if base_qty_q <= 0:
            continue
        if base_qty_q < meta.min_base_amount:
            continue
        if (base_qty_q * price_q) < meta.min_quote_amount:
            continue
        oid = bot_base + 1000 + i
        result[oid] = {
            "symbol": symbol,
            "market_id": market_id,
            "client_order_index": oid,
            "is_ask": True,
            "price_int": _to_scaled_int(price_q, meta.price_decimals, ROUND_HALF_UP),
            "base_amount_int": _to_scaled_int(base_qty_q, meta.size_decimals, ROUND_DOWN),
            "post_only": post_only,
        }

    for i in range(1, levels_down + 1):
        price = center - (step * i)
        if price <= 0:
            continue
        price_q = _quantize(price, meta.price_decimals, ROUND_HALF_UP)
        base_qty = _calc_base_qty(size_mode, size_value, price_q)
        base_qty_q = _quantize(base_qty, meta.size_decimals, ROUND_DOWN)
        if base_qty_q <= 0:
            continue
        if base_qty_q < meta.min_base_amount:
            continue
        if (base_qty_q * price_q) < meta.min_quote_amount:
            continue
        oid = bot_base + 2000 + i
        result[oid] = {
            "symbol": symbol,
            "market_id": market_id,
            "client_order_index": oid,
            "is_ask": False,
            "price_int": _to_scaled_int(price_q, meta.price_decimals, ROUND_HALF_UP),
            "base_amount_int": _to_scaled_int(base_qty_q, meta.size_decimals, ROUND_DOWN),
            "post_only": post_only,
        }

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
        interval_s = 2.0
        try:
            while True:
                await asyncio.sleep(interval_s)
                cfg = self._config.read()
                runtime = cfg.get("runtime", {})
                dry_run = bool(runtime.get("dry_run", True))
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

                prefix = _bot_prefix(trader.account_index, market_id, symbol)
                desired = _desired_orders(symbol, market_id, center, step, strat, meta, prefix)
                max_open_orders = int(strat.get("max_open_orders") or 0)
                if max_open_orders > 0 and len(desired) > max_open_orders:
                    keep = sorted(desired.items(), key=lambda kv: (kv[0] % 1000, kv[0]))[:max_open_orders]
                    desired = dict(keep)

                existing_orders = await trader.active_orders(market_id)
                existing: Dict[int, Any] = {}
                for o in existing_orders:
                    cid = int(getattr(o, "client_order_index", 0) or 0)
                    if cid <= 0:
                        continue
                    if (cid // 1_000_000) != prefix:
                        continue
                    existing[cid] = o

                cancels: Dict[int, int] = {}
                creates: Dict[int, Dict[str, Any]] = {}

                for cid, o in existing.items():
                    if cid not in desired:
                        cancels[cid] = cid

                for cid, spec in desired.items():
                    o = existing.get(cid)
                    if not o:
                        creates[cid] = spec
                        continue
                    is_ask = bool(getattr(o, "is_ask", False))
                    base_price = int(getattr(o, "base_price", 0) or 0)
                    base_size = int(getattr(o, "base_size", 0) or 0)
                    if is_ask != bool(spec["is_ask"]) or base_price != int(spec["price_int"]) or base_size != int(spec["base_amount_int"]):
                        cancels[cid] = cid

                max_actions = 10
                actions_done = 0

                for cid in list(cancels.keys()):
                    if actions_done >= max_actions:
                        break
                    if dry_run:
                        self._logbus.publish(f"dry_run cancel symbol={symbol} market_id={market_id} id={cid}")
                    else:
                        try:
                            await trader.cancel_order(market_id, cid)
                            self._logbus.publish(f"order.cancel symbol={symbol} market_id={market_id} id={cid}")
                        except Exception as exc:
                            self._logbus.publish(f"order.cancel.error symbol={symbol} id={cid} err={type(exc).__name__}:{exc}")
                    actions_done += 1

                for cid, spec in list(creates.items()):
                    if actions_done >= max_actions:
                        break
                    if dry_run:
                        self._logbus.publish(
                            f"dry_run create symbol={symbol} market_id={market_id} id={cid} ask={spec['is_ask']} price={spec['price_int']} size={spec['base_amount_int']}"
                        )
                    else:
                        try:
                            await trader.create_limit_order(
                                market_id=market_id,
                                client_order_index=cid,
                                base_amount=int(spec["base_amount_int"]),
                                price=int(spec["price_int"]),
                                is_ask=bool(spec["is_ask"]),
                                post_only=bool(spec["post_only"]),
                            )
                            self._logbus.publish(f"order.create symbol={symbol} market_id={market_id} id={cid}")
                        except Exception as exc:
                            self._logbus.publish(f"order.create.error symbol={symbol} id={cid} err={type(exc).__name__}:{exc}")
                    actions_done += 1

                msg = "模拟运行" if dry_run else "实盘运行"
                await self._update_status(
                    symbol,
                    running=True,
                    message=msg,
                    last_tick_at=_now_iso(),
                    market_id=market_id,
                    mid=str(mid),
                    center=str(center),
                    desired=len(desired),
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
