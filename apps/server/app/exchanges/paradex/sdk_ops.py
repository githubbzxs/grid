from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional


def _env_value(env: str) -> str:
    return "testnet" if env == "testnet" else "prod"


def _decimals_from_step(step: Any) -> int:
    try:
        d = Decimal(str(step))
    except Exception:
        return 0
    return max(0, -d.as_tuple().exponent)


def _get_fee(item: Dict[str, Any], key: str) -> Optional[str]:
    fee_cfg = item.get("fee_config") or {}
    api_fee = fee_cfg.get("api_fee") or {}
    entry = api_fee.get(key) or {}
    fee = entry.get("fee")
    return None if fee is None else str(fee)


async def fetch_perp_markets(env: str) -> List[Dict[str, Any]]:
    from paradex_py.api.api_client import ParadexApiClient

    api = ParadexApiClient(env=_env_value(env))
    data = api.fetch_markets()
    items = list(data.get("results") or [])
    results: List[Dict[str, Any]] = []
    for item in items:
        if str(item.get("asset_kind") or "") != "PERP":
            continue
        symbol = str(item.get("symbol") or "")
        price_step = item.get("price_tick_size") or "0"
        size_step = item.get("order_size_increment") or "0"
        results.append(
            {
                "market_id": symbol,
                "symbol": symbol,
                "market_type": item.get("asset_kind"),
                "supported_size_decimals": _decimals_from_step(size_step),
                "supported_price_decimals": _decimals_from_step(price_step),
                "min_base_amount": item.get("order_size_increment"),
                "min_quote_amount": item.get("min_notional"),
                "maker_fee": _get_fee(item, "maker_fee"),
                "taker_fee": _get_fee(item, "taker_fee"),
            }
        )
    results.sort(key=lambda x: x.get("symbol") or "")
    return results


async def test_connection(
    env: str,
    l1_address: Optional[str],
    l1_private_key: Optional[str],
    l2_address: Optional[str],
    l2_private_key: Optional[str],
) -> Dict[str, Any]:
    from app.exchanges.paradex.trader import ParadexTrader

    trader = ParadexTrader(
        env=env,
        l1_address=l1_address,
        l1_private_key=l1_private_key,
        l2_address=l2_address,
        l2_private_key=l2_private_key,
    )
    try:
        summary = trader._api.fetch_account_summary()
        if hasattr(summary, "model_dump"):
            data = summary.model_dump()
        elif hasattr(summary, "to_dict"):
            data = summary.to_dict()
        else:
            data = getattr(summary, "__dict__", {"raw": str(summary)})
        return {"env": env, "summary": data}
    finally:
        await trader.close()
