from __future__ import annotations

from decimal import Decimal

from app.core.config_store import ConfigStore
from app.core.logbus import LogBus
from app.services.bot_manager import (
    BotManager,
    _is_rate_limited_error,
    _split_cancel_keep_by_target,
)


def _manager(tmp_path) -> BotManager:
    cfg = ConfigStore(tmp_path / "config.json")
    return BotManager(LogBus(), cfg)


def test_is_rate_limited_error_match() -> None:
    exc = RuntimeError("ApiException: (429) Too Many Requests! code=23000")
    assert _is_rate_limited_error(exc) is True


def test_is_rate_limited_error_not_match() -> None:
    exc = RuntimeError("network timeout")
    assert _is_rate_limited_error(exc) is False


def test_rate_limit_backoff_and_clear(tmp_path) -> None:
    manager = _manager(tmp_path)

    delay1, streak1 = manager._mark_rate_limited("ETH", 1_000)
    assert delay1 == 500
    assert streak1 == 1
    assert manager._rate_limit_wait_ms("ETH", 1_200) == 300

    delay2, streak2 = manager._mark_rate_limited("ETH", 1_200)
    assert delay2 == 1000
    assert streak2 == 2
    assert manager._rate_limit_wait_ms("ETH", 1_700) == 500

    manager._clear_rate_limited("ETH")
    assert manager._rate_limit_wait_ms("ETH", 1_700) == 0


def test_split_cancel_keep_by_target_keep_one_and_cancel_rest() -> None:
    o1 = {"id": "o1"}
    o2 = {"id": "o2"}
    o3 = {"id": "o3"}
    o4 = {"id": "o4"}

    orders = {
        Decimal("100"): [o1, o2],
        Decimal("101"): [o3],
        Decimal("102"): [o4],
    }
    targets = {Decimal("100"), Decimal("102")}

    cancel_orders, keep_prices = _split_cancel_keep_by_target(orders, targets)

    assert keep_prices == {Decimal("100"), Decimal("102")}
    assert len(cancel_orders) == 2
    assert (o2, Decimal("100")) in cancel_orders
    assert (o3, Decimal("101")) in cancel_orders


def test_split_cancel_keep_by_target_empty_target_cancel_all() -> None:
    o1 = {"id": "o1"}
    o2 = {"id": "o2"}
    orders = {
        Decimal("99"): [o1],
        Decimal("98"): [o2],
    }

    cancel_orders, keep_prices = _split_cancel_keep_by_target(orders, set())

    assert keep_prices == set()
    assert len(cancel_orders) == 2
    assert (o1, Decimal("99")) in cancel_orders
    assert (o2, Decimal("98")) in cancel_orders
