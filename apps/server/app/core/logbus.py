from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import AsyncIterator, Deque, List


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _to_sse(data: str) -> str:
    safe = data.replace("\r", "").replace("\n", "\\n")
    return f"data: {safe}\n\n"


@dataclass
class LogBus:
    max_items: int = 2000
    _items: Deque[str] = field(default_factory=lambda: deque(maxlen=2000))
    _queue: "asyncio.Queue[str]" = field(default_factory=asyncio.Queue)

    def publish(self, message: str) -> None:
        line = f"[{_now_iso()}] {message}"
        self._items.append(line)
        try:
            self._queue.put_nowait(line)
        except asyncio.QueueFull:
            pass

    def recent(self, limit: int = 200) -> List[str]:
        if limit <= 0:
            return []
        return list(self._items)[-limit:]

    async def stream(self) -> AsyncIterator[str]:
        for line in self.recent():
            yield _to_sse(line)
        while True:
            line = await self._queue.get()
            yield _to_sse(line)
