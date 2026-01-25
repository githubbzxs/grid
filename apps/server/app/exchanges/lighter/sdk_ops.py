from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.exchanges.lighter.public_api import base_url


async def fetch_perp_markets(env: str) -> List[Dict[str, Any]]:
    import lighter

    url = base_url(env)
    api_client = lighter.ApiClient(configuration=lighter.Configuration(host=url))
    try:
        order_api = lighter.OrderApi(api_client)
        resp = await order_api.order_books()
        items = []
        for ob in getattr(resp, "order_books", []) or []:
            if getattr(ob, "market_type", "") != "perp":
                continue
            items.append(
                {
                    "market_id": getattr(ob, "market_id", None),
                    "symbol": getattr(ob, "symbol", None),
                    "market_type": getattr(ob, "market_type", None),
                    "supported_size_decimals": getattr(ob, "supported_size_decimals", None),
                    "supported_price_decimals": getattr(ob, "supported_price_decimals", None),
                    "min_base_amount": getattr(ob, "min_base_amount", None),
                    "min_quote_amount": getattr(ob, "min_quote_amount", None),
                    "maker_fee": getattr(ob, "maker_fee", None),
                    "taker_fee": getattr(ob, "taker_fee", None),
                }
            )
        items.sort(key=lambda x: (x.get("symbol") or "", x.get("market_id") or 0))
        return items
    finally:
        await api_client.close()


async def test_connection(
    env: str,
    account_index: int,
    api_key_index: int,
    api_private_key: str,
) -> Dict[str, Any]:
    import lighter

    url = base_url(env)
    signer = lighter.SignerClient(
        url=url,
        account_index=account_index,
        api_private_keys={int(api_key_index): str(api_private_key)},
    )
    api_client = lighter.ApiClient(configuration=lighter.Configuration(host=url))
    try:
        check_err = signer.check_client()
        auth_token, auth_err = signer.create_auth_token_with_expiry(api_key_index=int(api_key_index))
        order_api = lighter.OrderApi(api_client)
        stats = await order_api.exchange_stats()
        if hasattr(stats, "model_dump"):
            stats_dict = stats.model_dump()
        elif hasattr(stats, "to_dict"):
            stats_dict = stats.to_dict()
        else:
            stats_dict = {"raw": str(stats)}
        return {
            "base_url": url,
            "check_client_error": check_err,
            "auth_token_error": auth_err,
            "auth_token_preview": (auth_token[:12] + "…") if isinstance(auth_token, str) else None,
            "exchange_stats": stats_dict,
        }
    finally:
        await signer.close()
        await api_client.close()
