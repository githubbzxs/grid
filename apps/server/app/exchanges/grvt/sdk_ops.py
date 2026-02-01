from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List


def _env_value(env: str):
    from pysdk.grvt_ccxt_env import GrvtEnv

    name = str(env or "").strip().lower()
    if name in {"testnet", "test"}:
        return GrvtEnv.TESTNET
    if name in {"staging", "stage"}:
        return GrvtEnv.STAGING
    if name in {"dev", "development"}:
        return GrvtEnv.DEV
    if name in {"mainnet", "prod", "production"}:
        return GrvtEnv.PROD
    return GrvtEnv.PROD


def _decimals_from_step(step: Any) -> int:
    try:
        d = Decimal(str(step))
    except Exception:
        return 0
    if d <= 0:
        return 0
    return max(0, -d.as_tuple().exponent)


def _safe_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(0)


async def fetch_perp_markets(env: str) -> List[Dict[str, Any]]:
    """获取 GRVT 永续合约列表。"""
    from pysdk.grvt_ccxt_pro import GrvtCcxtPro
    from pysdk.grvt_ccxt_types import GrvtInstrumentKind

    client = GrvtCcxtPro(env=_env_value(env))
    try:
        items = await client.fetch_markets(params={"kind": GrvtInstrumentKind.PERPETUAL, "is_active": True, "limit": 1000})
        results: List[Dict[str, Any]] = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            instrument = str(item.get("instrument") or "").strip()
            if not instrument:
                continue
            tick_size = item.get("tick_size") or "0"
            base_decimals = int(item.get("base_decimals") or 0)
            size_decimals = max(0, int(base_decimals))
            price_decimals = _decimals_from_step(tick_size)
            min_size = _safe_decimal(item.get("min_size") or 0)
            min_quote = Decimal(0)
            if min_size > 0:
                try:
                    min_quote = min_size * _safe_decimal(tick_size)
                except Exception:
                    min_quote = Decimal(0)

            results.append(
                {
                    "market_id": instrument,
                    "symbol": instrument,
                    "market_type": "PERPETUAL",
                    "supported_size_decimals": size_decimals,
                    "supported_price_decimals": price_decimals,
                    "min_base_amount": str(min_size),
                    "min_quote_amount": str(min_quote),
                    "tick_size": str(tick_size),
                    "base_decimals": base_decimals,
                    "min_size": str(min_size),
                    "max_position_size": item.get("max_position_size"),
                }
            )
        results.sort(key=lambda x: x.get("symbol") or "")
        return results
    finally:
        await client._session.close()


async def test_connection(
    env: str,
    account_id: str,
    api_key: str,
    private_key: str,
) -> Dict[str, Any]:
    """测试 GRVT 连接与鉴权。"""
    from pysdk.grvt_ccxt_pro import GrvtCcxtPro

    client = GrvtCcxtPro(
        env=_env_value(env),
        parameters={
            "trading_account_id": str(account_id),
            "api_key": str(api_key),
            "private_key": str(private_key),
        },
    )
    try:
        summary = await client.get_account_summary()
        markets = await client.fetch_markets(params={"is_active": True, "limit": 5})
        return {
            "env": str(env),
            "account_summary": summary,
            "markets_preview": markets,
        }
    finally:
        await client._session.close()
