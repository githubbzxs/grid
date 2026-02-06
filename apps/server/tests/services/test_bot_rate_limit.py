from __future__ import annotations

from app.core.config_store import ConfigStore
from app.core.logbus import LogBus
from app.services.bot_manager import BotManager, _is_rate_limited_error


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
