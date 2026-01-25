from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.core.logbus import LogBus


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@dataclass
class BotStatus:
    symbol: str
    running: bool
    started_at: Optional[str] = None
    last_tick_at: Optional[str] = None
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "running": self.running,
            "started_at": self.started_at,
            "last_tick_at": self.last_tick_at,
            "message": self.message,
        }


class BotManager:
    def __init__(self, logbus: LogBus) -> None:
        self._logbus = logbus
        self._tasks: Dict[str, asyncio.Task[None]] = {}
        self._status: Dict[str, BotStatus] = {}
        self._lock = asyncio.Lock()

    async def start(self, symbol: str) -> None:
        async with self._lock:
            task = self._tasks.get(symbol)
            if task and not task.done():
                return
            self._status[symbol] = BotStatus(
                symbol=symbol,
                running=True,
                started_at=_now_iso(),
                last_tick_at=None,
                message="运行中",
            )
            self._tasks[symbol] = asyncio.create_task(self._run(symbol))
            self._logbus.publish(f"bot.start symbol={symbol}")

    async def stop(self, symbol: str) -> None:
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
            self._status[symbol] = BotStatus(symbol=symbol, running=False, message="已停止")
        self._logbus.publish(f"bot.stop symbol={symbol}")

    async def stop_all(self) -> None:
        symbols = list(self._tasks.keys())
        for symbol in symbols:
            await self.stop(symbol)

    def snapshot(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for symbol, status in self._status.items():
            result[symbol] = status.to_dict()
        return result

    async def _run(self, symbol: str) -> None:
        try:
            while True:
                await asyncio.sleep(1.0)
                async with self._lock:
                    status = self._status.get(symbol)
                    if status:
                        status.last_tick_at = _now_iso()
                        status.message = "运行中"
                self._logbus.publish(f"bot.tick symbol={symbol}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._logbus.publish(f"bot.error symbol={symbol} err={type(exc).__name__}:{exc}")
            async with self._lock:
                self._status[symbol] = BotStatus(symbol=symbol, running=False, message="异常退出")

