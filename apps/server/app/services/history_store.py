from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class HistoryStore:
    path: Path
    lock: threading.Lock = field(default_factory=threading.Lock)

    def append(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False)
        with self.lock:
            with self.path.open("a", encoding="utf-8") as fp:
                fp.write(line + "\n")

    def read(self, limit: int = 200) -> list[dict[str, Any]]:
        if limit == 0:
            limit = -1
        if not self.path.exists():
            return []
        with self.lock:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        if limit > 0:
            lines = lines[-limit:]
        items: list[dict[str, Any]] = []
        for line in lines:
            if not line.strip():
                continue
            try:
                items.append(json.loads(line))
            except Exception:
                continue
        return items
