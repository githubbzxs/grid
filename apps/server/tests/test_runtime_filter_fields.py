from __future__ import annotations

from app.main import _runtime_filter_fields


def test_runtime_filter_fields_use_market_indicators_first() -> None:
    status = {
        "filter_state": "pass",
        "filter_reason": "ok",
        "market_indicator_atr": "18.123456",
        "market_indicator_adx": "25.6789",
        "filter_atr_pct": "0.002",
        "filter_adx": "28",
        "bid": "2456.123456",
        "ask": "2456.223456",
    }

    fields = _runtime_filter_fields(status)
    assert fields["filter_state"] == "pass"
    assert fields["filter_reason"] == "ok"
    assert fields["filter_atr_pct"] == "18.123456"
    assert fields["filter_adx"] == "25.6789"


def test_runtime_filter_fields_fallback_to_filter_values() -> None:
    status = {
        "filter_state": "block",
        "filter_reason": "atr_low",
        "filter_atr_pct": "0.00123456",
        "filter_adx": "12.34567",
    }

    fields = _runtime_filter_fields(status)
    assert fields["filter_state"] == "block"
    assert fields["filter_reason"] == "atr_low"
    assert fields["filter_atr_pct"] == "0.001235"
    assert fields["filter_adx"] == "12.3457"


def test_runtime_filter_fields_with_only_bid_ask_should_empty() -> None:
    status = {
        "filter_state": "pass",
        "filter_reason": "ok",
        "bid": "2456.1000",
        "ask": "2456.2000",
    }

    fields = _runtime_filter_fields(status)
    assert fields["filter_atr_pct"] is None
    assert fields["filter_adx"] is None
