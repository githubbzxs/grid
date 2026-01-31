from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def default_data_dir() -> Path:
    env = os.getenv("GRID_DATA_DIR")
    if env:
        return Path(env).expanduser().resolve()
    return _repo_root() / "data"


def default_config() -> dict[str, Any]:
    return {
        "auth": {
            "password_salt_b64": "",
            "password_hash_b64": "",
            "kdf_salt_b64": "",
        },
        "runtime": {
            "dry_run": True,
            "simulate_fill": False,
            "loop_interval_ms": 100,
            "status_refresh_ms": 1000,
            "auto_restart": True,
            "restart_delay_ms": 1000,
            "restart_max": 5,
            "restart_window_ms": 60000,
            "stop_after_minutes": 0.0,
            "stop_after_volume": 0.0,
            "stop_check_interval_ms": 1000,
        },
        "server": {
            "host": "0.0.0.0",
            "port": 9999,
        },
        "exchange": {
            "name": "lighter",
            "env": "mainnet",
            "l1_address": "",
            "account_index": None,
            "api_key_index": None,
            "remember_secrets": True,
            "api_private_key_enc": "",
            "eth_private_key_enc": "",
            "paradex_l1_address": "",
            "paradex_l2_address": "",
            "paradex_l1_private_key_enc": "",
            "paradex_l2_private_key_enc": "",
        },
        "strategies": {
            "BTC": {
                "enabled": True,
                "market_id": None,
                "grid_step": 0.0,
                "levels_up": 10,
                "levels_down": 10,
                "order_size_mode": "notional",
                "order_size_value": 5.0,
                "post_only": True,
                "max_open_orders": 50,
                "max_position_notional": 20.0,
                "reduce_position_notional": 0.0,
                "reduce_order_size_multiplier": 1.0,
            },
            "ETH": {
                "enabled": True,
                "market_id": None,
                "grid_step": 0.0,
                "levels_up": 10,
                "levels_down": 10,
                "order_size_mode": "notional",
                "order_size_value": 5.0,
                "post_only": True,
                "max_open_orders": 50,
                "max_position_notional": 20.0,
                "reduce_position_notional": 0.0,
                "reduce_order_size_multiplier": 1.0,
            },
            "SOL": {
                "enabled": True,
                "market_id": None,
                "grid_step": 0.0,
                "levels_up": 10,
                "levels_down": 10,
                "order_size_mode": "notional",
                "order_size_value": 5.0,
                "post_only": True,
                "max_open_orders": 50,
                "max_position_notional": 20.0,
                "reduce_position_notional": 0.0,
                "reduce_order_size_multiplier": 1.0,
            },
        },
    }


@dataclass
class ConfigStore:
    path: Path
    lock: threading.Lock = field(default_factory=threading.Lock)

    def ensure(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write(default_config())

    def read(self) -> dict[str, Any]:
        self.ensure()
        with self.lock:
            return json.loads(self.path.read_text(encoding="utf-8"))

    def write(self, config: dict[str, Any]) -> None:
        self.ensure()
        with self.lock:
            self._write(config)

    def update(self, patch: dict[str, Any]) -> dict[str, Any]:
        current = self.read()
        merged = _deep_merge(current, patch)
        self.write(merged)
        return merged

    def _write(self, config: dict[str, Any]) -> None:
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self.path)


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged
