from __future__ import annotations

import hashlib
import secrets
import time
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet
from fastapi import Body, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from app.core.config_store import ConfigStore, default_data_dir
from app.core.logbus import LogBus
from app.core.security import decrypt_str, derive_fernet, encrypt_str, new_salt_b64, password_hash_b64, verify_password
from app.exchanges.grvt.market_ws import _parse_price as grvt_parse_price
from app.exchanges.grvt.sdk_ops import fetch_perp_markets as grvt_fetch_perp_markets, test_connection as grvt_test_connection
from app.exchanges.grvt.trader import GrvtTrader
from app.exchanges.lighter.public_api import LighterPublicClient, base_url as lighter_base_url
from app.exchanges.lighter.sdk_ops import fetch_perp_markets as lighter_fetch_perp_markets, test_connection as lighter_test_connection
from app.exchanges.lighter.trader import LighterTrader
from app.exchanges.paradex.sdk_ops import fetch_perp_markets as paradex_fetch_perp_markets, test_connection as paradex_test_connection
from app.exchanges.paradex.trader import ParadexTrader
from app.exchanges.types import Trader
from app.services.bot_manager import BotManager
from app.services.history_store import HistoryStore
from app.strategies.grid.ids import grid_prefix, is_grid_client_order


WEB_DIR = Path(__file__).resolve().parent / "web"


class PasswordBody(BaseModel):
    password: str = Field(min_length=8, max_length=200)


class BotSymbolsBody(BaseModel):
    symbols: list[str] = Field(default_factory=list)


class ResolveAccountIndexBody(BaseModel):
    env: str = Field(default="mainnet")
    l1_address: str = Field(min_length=1, max_length=200)


def _session_token(request: Request) -> Optional[str]:
    return request.cookies.get("grid_session")


def require_auth(request: Request) -> str:
    token = _session_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    sessions: Dict[str, Any] = request.app.state.sessions
    if token not in sessions:
        raise HTTPException(status_code=401, detail="会话失效")
    return token


def require_unlocked(request: Request) -> Fernet:
    require_auth(request)
    fernet: Optional[Fernet] = request.app.state.fernet
    if not fernet:
        raise HTTPException(status_code=401, detail="已锁定")
    return fernet


def _exchange_name(config: Dict[str, Any], override: Optional[str] = None) -> str:
    raw = override if override is not None else (config.get("exchange", {}) or {}).get("name")
    name = str(raw or "lighter").strip().lower()
    if name == "paradex":
        return "paradex"
    if name == "grvt":
        return "grvt"
    return "lighter"


def _strategy_exchange(config: Dict[str, Any], strat: Dict[str, Any]) -> str:
    raw = str(strat.get("exchange") or "").strip()
    return _exchange_name(config, raw if raw else None)


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _symbol_tokens(value: Any) -> list[str]:
    text = _normalize_symbol(value)
    tokens: list[str] = []
    buf: list[str] = []
    for ch in text:
        if ch.isalnum():
            buf.append(ch)
            continue
        if buf:
            tokens.append("".join(buf))
            buf = []
    if buf:
        tokens.append("".join(buf))
    return tokens


def _normalize_market_id(exchange: str, value: Any) -> Optional[str | int]:
    if value is None:
        return None
    if exchange in {"paradex", "grvt"}:
        text = str(value).strip()
        return text or None
    try:
        return int(str(value).strip())
    except Exception:
        return None


def _pick_market_item(symbol: str, items: list[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    base = _normalize_symbol(symbol)
    if not base:
        return None

    def _sym(item: Dict[str, Any]) -> str:
        return _normalize_symbol(item.get("symbol"))

    def _base_match(sym: str) -> bool:
        if not sym:
            return False
        if sym == base:
            return True
        tokens = _symbol_tokens(sym)
        if tokens and tokens[0] == base:
            return True
        if sym.startswith(base):
            remainder = sym[len(base) :]
            if not remainder:
                return True
            if remainder[0] in "-_:/":
                return True
            if remainder.startswith(("USDC", "USDT", "USD")):
                return True
        return False

    candidates = [item for item in items if _base_match(_sym(item))]
    if not candidates:
        return None

    def _score(item: Dict[str, Any]) -> int:
        sym = _sym(item)
        score = 0
        if sym == base:
            score += 6
        tokens = _symbol_tokens(sym)
        if tokens and tokens[0] == base:
            score += 4
        if sym.startswith(base):
            score += 2
        if "USDC" in sym:
            score += 3
        elif "USD" in sym:
            score += 2
        elif "USDT" in sym:
            score += 1
        return score

    return max(candidates, key=_score)


def _market_id_matches_symbol(exchange: str, symbol: str, market_id: Any) -> bool:
    if exchange not in {"paradex", "grvt"}:
        return True
    mid = _normalize_symbol(market_id)
    return bool(_pick_market_item(symbol, [{"symbol": mid, "market_id": mid}]))


async def _fetch_markets_for_exchange(exchange: str, env: str) -> list[Dict[str, Any]]:
    if exchange == "paradex":
        return await paradex_fetch_perp_markets(env)
    if exchange == "grvt":
        return await grvt_fetch_perp_markets(env)
    return await lighter_fetch_perp_markets(env)


async def _resolve_market_id(
    request: Request,
    exchange: str,
    env: str,
    symbol: str,
    cache: Dict[tuple[str, str], list[Dict[str, Any]]],
) -> Optional[str | int]:
    key = (exchange, env)
    if key not in cache:
        try:
            cache[key] = await _fetch_markets_for_exchange(exchange, env)
        except Exception as exc:
            request.app.state.logbus.publish(
                f"market.resolve.error exchange={exchange} env={env} err={type(exc).__name__}:{exc}"
            )
            cache[key] = []
    items = cache.get(key) or []
    picked = _pick_market_item(symbol, items)
    if not picked:
        return None
    return _normalize_market_id(exchange, picked.get("market_id"))


async def _fill_strategy_market_ids(
    request: Request,
    config: Dict[str, Any],
    symbols: Optional[set[str]] = None,
) -> bool:
    strategies = config.get("strategies") or {}
    if not isinstance(strategies, dict):
        return False
    env = str((config.get("exchange", {}) or {}).get("env") or "mainnet")
    cache: Dict[tuple[str, str], list[Dict[str, Any]]] = {}
    updated = False
    symbol_set = {s for s in (_normalize_symbol(x) for x in symbols) if s} if symbols else None
    for key, strat in strategies.items():
        if not isinstance(strat, dict):
            continue
        symbol = _normalize_symbol(key)
        if not symbol:
            continue
        if symbol_set is not None and symbol not in symbol_set:
            continue
        exchange = _strategy_exchange(config, strat)
        if not str(strat.get("exchange") or "").strip():
            strat["exchange"] = exchange
            updated = True
        market_id = _normalize_market_id(exchange, strat.get("market_id"))
        if market_id is not None and not _market_id_matches_symbol(exchange, symbol, market_id):
            market_id = None
        if market_id is None:
            resolved = await _resolve_market_id(request, exchange, env, symbol, cache)
            if resolved is not None:
                strat["market_id"] = resolved
                updated = True
        else:
            if market_id != strat.get("market_id"):
                strat["market_id"] = market_id
                updated = True
    return updated


def _safe_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(str(value).strip())
    except Exception:
        return None


def _secret_fingerprint(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _now_ms() -> int:
    return int(time.time() * 1000)


def _parse_iso_ms(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except Exception:
        return None


def _safe_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(0)


def _deep_merge(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _fmt_decimal(value: Decimal, digits: int = 4) -> str:
    q = Decimal(1) / (Decimal(10) ** int(digits))
    return str(value.quantize(q, rounding=ROUND_HALF_UP))


def _order_field(order: Any, name: str) -> Any:
    if isinstance(order, dict):
        return order.get(name)
    return getattr(order, name, None)


def _order_client_id(order: Any) -> Optional[int]:
    for key in ("client_order_index", "client_id", "client_order_id", "clientOrderId"):
        value = _order_field(order, key)
        if value is None:
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            v = value.strip()
            if v.isdigit():
                return int(v)
    return None


def _order_id(order: Any) -> Any:
    for key in ("order_index", "id", "order_id"):
        value = _order_field(order, key)
        if value is None:
            continue
        return value
    return None


def _order_side(order: Any) -> Optional[str]:
    is_ask = _order_field(order, "is_ask")
    if isinstance(is_ask, bool):
        return "ask" if is_ask else "bid"
    side = _order_field(order, "side") or _order_field(order, "order_side")
    if isinstance(side, str):
        upper = side.upper()
        if upper in ("SELL", "ASK"):
            return "ask"
        if upper in ("BUY", "BID"):
            return "bid"
    return None


def _order_to_dict(order: Any) -> Dict[str, Any]:
    if isinstance(order, dict):
        data = dict(order)
    elif hasattr(order, "model_dump"):
        data = order.model_dump()
    elif hasattr(order, "to_dict"):
        data = order.to_dict()
    elif hasattr(order, "__dict__"):
        data = dict(order.__dict__)
    else:
        data = {"raw": str(order)}

    data.setdefault("client_id", _order_client_id(order))
    data.setdefault("order_id", _order_id(order))
    data.setdefault("side", _order_side(order))
    return data


def _trade_ts_ms(value: Any) -> Optional[int]:
    try:
        ts = int(value)
    except Exception:
        return None
    if ts < 10_000_000_000:
        return ts * 1000
    return ts


async def _lighter_positions_map(trader: LighterTrader) -> Dict[int, Dict[str, Decimal]]:
    resp = await trader._account_api.account(by="index", value=str(int(trader.account_index)))
    if hasattr(resp, "model_dump"):
        data = resp.model_dump()
    elif hasattr(resp, "to_dict"):
        data = resp.to_dict()
    else:
        data = getattr(resp, "__dict__", {})

    positions = []
    if isinstance(data, dict):
        accounts = data.get("accounts")
        picked = None
        if isinstance(accounts, list):
            for item in accounts:
                if not isinstance(item, dict):
                    continue
                idx = item.get("account_index") or item.get("accountIndex") or item.get("index")
                try:
                    if idx is not None and int(idx) == int(trader.account_index):
                        picked = item
                        break
                except Exception:
                    continue
            if picked is None and accounts:
                picked = accounts[0] if isinstance(accounts[0], dict) else None
        if isinstance(picked, dict):
            positions = picked.get("positions") or []
        elif isinstance(data.get("positions"), list):
            positions = data.get("positions") or []

    result: Dict[int, Dict[str, Decimal]] = {}
    for pos in positions or []:
        if not isinstance(pos, dict):
            continue
        mid = pos.get("market_id")
        if not isinstance(mid, int):
            try:
                mid = int(str(mid))
            except Exception:
                continue
        sign = pos.get("sign", 1)
        try:
            sign_v = int(sign) if int(sign) != 0 else 1
        except Exception:
            sign_v = 1
        base = _safe_decimal(pos.get("position") or 0) * Decimal(sign_v)
        pnl = _safe_decimal(pos.get("realized_pnl") or 0) + _safe_decimal(pos.get("unrealized_pnl") or 0)
        result[mid] = {"base": base, "pnl": pnl}
    return result


def _paradex_positions_map(trader: ParadexTrader) -> Dict[str, Dict[str, Decimal]]:
    data = trader._api.fetch_positions()
    results = list(data.get("results") or [])
    result: Dict[str, Dict[str, Decimal]] = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        market = str(item.get("market") or "")
        if not market:
            continue
        base = _safe_decimal(item.get("size") or 0)
        pnl = _safe_decimal(item.get("realized_positional_pnl") or 0) + _safe_decimal(item.get("unrealized_pnl") or 0)
        result[market] = {"base": base, "pnl": pnl}
    return result


async def _grvt_positions_map(trader: GrvtTrader) -> Dict[str, Dict[str, Decimal]]:
    return await trader.positions_snapshot()


async def _grvt_trades_since(
    trader: GrvtTrader,
    market: str,
    start_ms: int,
    end_ms: int,
    max_pages: int = 5,
) -> tuple[Decimal, int]:
    total = Decimal(0)
    count = 0
    cursor = None
    pages = 0
    start_ns = int(start_ms) * 1_000_000
    end_ns = int(end_ms) * 1_000_000

    while pages < max_pages:
        params: Dict[str, Any] = {"end_time": end_ns}
        if cursor:
            params = {"cursor": cursor}
        resp = await trader._api.fetch_my_trades(symbol=str(market), since=start_ns, limit=200, params=params)
        results = resp.get("result") if isinstance(resp, dict) else None
        results = results or []
        for item in results:
            if not isinstance(item, dict):
                continue
            ts_raw = item.get("event_time") or item.get("timestamp") or item.get("time")
            try:
                ts_val = int(ts_raw)
            except Exception:
                ts_val = None
            ts_ms = None
            if ts_val is not None:
                if ts_val > 10_000_000_000_000:
                    ts_ms = ts_val // 1_000_000
                elif ts_val > 10_000_000_000:
                    ts_ms = ts_val
                else:
                    ts_ms = ts_val * 1000
            if ts_ms is not None and (ts_ms < start_ms or ts_ms > end_ms):
                continue
            price = grvt_parse_price(item.get("price") or item.get("fill_price"))
            if price is None:
                price = _safe_decimal(item.get("price") or 0)
            size = _safe_decimal(item.get("size") or item.get("amount") or 0)
            total += abs(price * size)
            count += 1

        cursor = resp.get("next") if isinstance(resp, dict) else None
        if not cursor:
            cursor = resp.get("next_cursor") if isinstance(resp, dict) else None
        if not cursor:
            break
        pages += 1
    return total, count


async def _lighter_trades_since(
    trader: LighterTrader,
    market_id: int,
    start_ms: int,
    max_pages: int = 5,
) -> tuple[Decimal, int]:
    total = Decimal(0)
    count = 0
    auth_token = await trader.auth_token()
    cursor = None
    pages = 0
    reached_old = False
    while pages < max_pages and not reached_old:
        resp = await trader._call_with_retry(
            trader._order_api.trades,
            sort_by="timestamp",
            limit=100,
            market_id=int(market_id),
            account_index=int(trader.account_index),
            sort_dir="desc",
            cursor=cursor,
            auth=auth_token,
        )
        trades = getattr(resp, "trades", None)
        if trades is None and isinstance(resp, dict):
            trades = resp.get("trades")
        trades = trades or []
        for t in trades:
            ts = _trade_ts_ms(_order_field(t, "timestamp"))
            if ts is not None and ts < start_ms:
                reached_old = True
                break
            usd_amount = _safe_decimal(_order_field(t, "usd_amount") or 0)
            if usd_amount == 0:
                price = _safe_decimal(_order_field(t, "price") or 0)
                size = _safe_decimal(_order_field(t, "size") or 0)
                usd_amount = price * size
            total += abs(usd_amount)
            count += 1
        cursor = getattr(resp, "next_cursor", None) if not isinstance(resp, dict) else resp.get("next_cursor")
        if not cursor:
            break
        pages += 1
    return total, count


def _paradex_fills_since(
    trader: ParadexTrader,
    market: str,
    start_ms: int,
    end_ms: int,
    max_pages: int = 5,
) -> tuple[Decimal, int]:
    total = Decimal(0)
    count = 0
    cursor = None
    pages = 0
    while pages < max_pages:
        params = {"market": market, "start_at": int(start_ms), "end_at": int(end_ms), "page_size": 200}
        if cursor:
            params["cursor"] = cursor
        data = trader._api.fetch_fills(params)
        results = list(data.get("results") or [])
        for item in results:
            if not isinstance(item, dict):
                continue
            price = _safe_decimal(item.get("price") or 0)
            size = _safe_decimal(item.get("size") or 0)
            total += abs(price * size)
            count += 1
        cursor = data.get("next") or data.get("next_cursor")
        if not cursor:
            break
        pages += 1
    return total, count


def _mask_config(config: Dict[str, Any]) -> Dict[str, Any]:
    exchange = dict(config.get("exchange", {}))
    runtime = dict(config.get("runtime", {}))
    runtime.pop("loop_interval_ms", None)
    exchange.pop("api_private_key_enc", None)
    exchange.pop("eth_private_key_enc", None)
    exchange.pop("grvt_api_key_enc", None)
    exchange.pop("grvt_private_key_enc", None)
    exchange.pop("paradex_l1_private_key_enc", None)
    exchange.pop("paradex_l2_private_key_enc", None)
    exchange["api_private_key_set"] = bool(config.get("exchange", {}).get("api_private_key_enc"))
    exchange["eth_private_key_set"] = bool(config.get("exchange", {}).get("eth_private_key_enc"))
    exchange["grvt_api_key_set"] = bool(config.get("exchange", {}).get("grvt_api_key_enc"))
    exchange["grvt_private_key_set"] = bool(config.get("exchange", {}).get("grvt_private_key_enc"))
    exchange["paradex_l1_private_key_set"] = bool(config.get("exchange", {}).get("paradex_l1_private_key_enc"))
    exchange["paradex_l2_private_key_set"] = bool(config.get("exchange", {}).get("paradex_l2_private_key_enc"))
    result = dict(config)
    result["runtime"] = runtime
    result["exchange"] = exchange
    return result


app = FastAPI(title="Grid", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.on_event("startup")
async def _startup() -> None:
    data_dir = default_data_dir()
    config_path = data_dir / "config.json"
    app.state.config = ConfigStore(path=config_path)
    app.state.logbus = LogBus()
    app.state.bot_manager = BotManager(app.state.logbus, app.state.config)
    app.state.history_store = HistoryStore(path=data_dir / "runtime_history.jsonl")
    app.state.sessions = {}
    app.state.fernet = None
    app.state.runtime_secrets = {}
    app.state.lighter_trader = None
    app.state.lighter_trader_sig = None
    app.state.paradex_trader = None
    app.state.paradex_trader_sig = None
    app.state.grvt_trader = None
    app.state.grvt_trader_sig = None
    app.state.runtime_stats = {}
    app.state.logbus.publish("server.start")


@app.on_event("shutdown")
async def _shutdown() -> None:
    trader: Optional[LighterTrader] = getattr(app.state, "lighter_trader", None)
    if trader:
        await trader.close()
    p_trader: Optional[ParadexTrader] = getattr(app.state, "paradex_trader", None)
    if p_trader:
        await p_trader.close()
    g_trader: Optional[GrvtTrader] = getattr(app.state, "grvt_trader", None)
    if g_trader:
        await g_trader.close()


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(str(WEB_DIR / "index.html"))


@app.get("/login")
async def login_page() -> FileResponse:
    return FileResponse(str(WEB_DIR / "login.html"))


@app.get("/api/health")
async def health() -> Dict[str, Any]:
    return {"ok": True}


@app.get("/api/auth/status")
async def auth_status(request: Request) -> Dict[str, Any]:
    config: Dict[str, Any] = request.app.state.config.read()
    setup_required = not bool(config.get("auth", {}).get("password_hash_b64"))
    authenticated = False
    token = _session_token(request)
    if token and token in request.app.state.sessions:
        authenticated = True
    unlocked = bool(request.app.state.fernet)
    return {
        "setup_required": setup_required,
        "authenticated": authenticated,
        "unlocked": unlocked,
    }


@app.post("/api/auth/setup")
async def auth_setup(body: PasswordBody, request: Request, response: Response) -> Dict[str, Any]:
    config: Dict[str, Any] = request.app.state.config.read()
    if config.get("auth", {}).get("password_hash_b64"):
        raise HTTPException(status_code=400, detail="已初始化")

    password_salt = new_salt_b64()
    kdf_salt = new_salt_b64()
    password_hash = password_hash_b64(body.password, password_salt)

    config["auth"] = {
        "password_salt_b64": password_salt,
        "password_hash_b64": password_hash,
        "kdf_salt_b64": kdf_salt,
    }
    request.app.state.config.write(config)

    token = secrets.token_urlsafe(32)
    request.app.state.sessions[token] = {"created": True}
    request.app.state.fernet = derive_fernet(body.password, kdf_salt)
    response.set_cookie("grid_session", token, httponly=True, samesite="lax")
    request.app.state.logbus.publish("auth.setup")
    return {"ok": True}


@app.post("/api/auth/login")
async def auth_login(body: PasswordBody, request: Request, response: Response) -> Dict[str, Any]:
    config: Dict[str, Any] = request.app.state.config.read()
    auth = config.get("auth", {})
    if not auth.get("password_hash_b64"):
        raise HTTPException(status_code=400, detail="未初始化")

    if not verify_password(body.password, auth["password_salt_b64"], auth["password_hash_b64"]):
        raise HTTPException(status_code=401, detail="密码错误")

    token = secrets.token_urlsafe(32)
    request.app.state.sessions[token] = {"created": True}
    request.app.state.fernet = derive_fernet(body.password, auth["kdf_salt_b64"])
    response.set_cookie("grid_session", token, httponly=True, samesite="lax")
    request.app.state.logbus.publish("auth.login")
    return {"ok": True}


@app.post("/api/auth/logout")
async def auth_logout(request: Request, response: Response, _: str = Depends(require_auth)) -> Dict[str, Any]:
    token = _session_token(request)
    if token:
        request.app.state.sessions.pop(token, None)
    request.app.state.fernet = None
    response.delete_cookie("grid_session")
    request.app.state.logbus.publish("auth.logout")
    return {"ok": True}


@app.post("/api/auth/lock")
async def auth_lock(request: Request, _: str = Depends(require_auth)) -> Dict[str, Any]:
    request.app.state.fernet = None
    request.app.state.logbus.publish("auth.lock")
    return {"ok": True}


@app.get("/api/config")
async def get_config(request: Request, _: str = Depends(require_auth)) -> Dict[str, Any]:
    config: Dict[str, Any] = request.app.state.config.read()
    return {"config": _mask_config(config)}


@app.post("/api/config")
async def update_config(
    request: Request,
    patch: Dict[str, Any] = Body(default_factory=dict),
    fernet: Fernet = Depends(require_unlocked),
) -> Dict[str, Any]:
    config: Dict[str, Any] = request.app.state.config.read()
    runtime_patch = patch.get("runtime")
    if isinstance(runtime_patch, dict):
        runtime_clean = dict(runtime_patch)
        runtime_clean.pop("loop_interval_ms", None)
        patch = dict(patch)
        patch["runtime"] = runtime_clean
    exchange_patch = dict(patch.get("exchange") or {})
    plaintext_api_key = exchange_patch.pop("api_private_key", None)
    plaintext_eth_key = exchange_patch.pop("eth_private_key", None)
    plaintext_grvt_api_key = exchange_patch.pop("grvt_api_key", None)
    plaintext_grvt_private_key = exchange_patch.pop("grvt_private_key", None)
    plaintext_paradex_l1_key = exchange_patch.pop("paradex_l1_private_key", None)
    plaintext_paradex_l2_key = exchange_patch.pop("paradex_l2_private_key", None)

    if "exchange" in patch:
        patch = dict(patch)
        patch["exchange"] = exchange_patch

    merged = config
    removed_symbols: set[str] = set()
    if "strategies" in patch:
        strategies_patch = patch.get("strategies") or {}
        if not isinstance(strategies_patch, dict):
            raise HTTPException(status_code=400, detail="策略配置格式错误")
        normalized: Dict[str, Any] = {}
        for key, value in strategies_patch.items():
            symbol = str(key or "").strip().upper()
            if not symbol:
                continue
            item = value if isinstance(value, dict) else {}
            normalized[symbol] = dict(item)
        prev_symbols = set((config.get("strategies", {}) or {}).keys())
        removed_symbols = prev_symbols - set(normalized.keys())
        merged = dict(merged)
        merged["strategies"] = normalized
        patch = dict(patch)
        patch.pop("strategies", None)

    if patch:
        merged = _deep_merge(merged, patch)
    runtime_cfg = merged.get("runtime")
    if isinstance(runtime_cfg, dict):
        runtime_cfg = dict(runtime_cfg)
        runtime_cfg.pop("loop_interval_ms", None)
        merged["runtime"] = runtime_cfg

    await _fill_strategy_market_ids(request, merged)

    remember = bool(merged.get("exchange", {}).get("remember_secrets", True))
    runtime_secrets: Dict[str, str] = request.app.state.runtime_secrets

    if plaintext_api_key is not None:
        if remember:
            merged["exchange"]["api_private_key_enc"] = encrypt_str(fernet, str(plaintext_api_key))
            runtime_secrets.pop("api_private_key", None)
        else:
            merged["exchange"]["api_private_key_enc"] = ""
            runtime_secrets["api_private_key"] = str(plaintext_api_key)

    if plaintext_eth_key is not None:
        if remember:
            merged["exchange"]["eth_private_key_enc"] = encrypt_str(fernet, str(plaintext_eth_key))
            runtime_secrets.pop("eth_private_key", None)
        else:
            merged["exchange"]["eth_private_key_enc"] = ""
            runtime_secrets["eth_private_key"] = str(plaintext_eth_key)

    if plaintext_grvt_api_key is not None:
        if remember:
            merged["exchange"]["grvt_api_key_enc"] = encrypt_str(fernet, str(plaintext_grvt_api_key))
            runtime_secrets.pop("grvt_api_key", None)
        else:
            merged["exchange"]["grvt_api_key_enc"] = ""
            runtime_secrets["grvt_api_key"] = str(plaintext_grvt_api_key)

    if plaintext_grvt_private_key is not None:
        if remember:
            merged["exchange"]["grvt_private_key_enc"] = encrypt_str(fernet, str(plaintext_grvt_private_key))
            runtime_secrets.pop("grvt_private_key", None)
        else:
            merged["exchange"]["grvt_private_key_enc"] = ""
            runtime_secrets["grvt_private_key"] = str(plaintext_grvt_private_key)

    if plaintext_paradex_l1_key is not None:
        if remember:
            merged["exchange"]["paradex_l1_private_key_enc"] = encrypt_str(fernet, str(plaintext_paradex_l1_key))
            runtime_secrets.pop("paradex_l1_private_key", None)
        else:
            merged["exchange"]["paradex_l1_private_key_enc"] = ""
            runtime_secrets["paradex_l1_private_key"] = str(plaintext_paradex_l1_key)

    if plaintext_paradex_l2_key is not None:
        if remember:
            merged["exchange"]["paradex_l2_private_key_enc"] = encrypt_str(fernet, str(plaintext_paradex_l2_key))
            runtime_secrets.pop("paradex_l2_private_key", None)
        else:
            merged["exchange"]["paradex_l2_private_key_enc"] = ""
            runtime_secrets["paradex_l2_private_key"] = str(plaintext_paradex_l2_key)

    request.app.state.config.write(merged)
    if removed_symbols:
        runtime_stats: Dict[str, Any] = request.app.state.runtime_stats
        for symbol in removed_symbols:
            try:
                await request.app.state.bot_manager.stop(symbol)
            except Exception:
                pass
            runtime_stats.pop(symbol, None)
    request.app.state.logbus.publish("config.update")
    return {"ok": True, "config": _mask_config(merged)}


@app.get("/api/bots/status")
async def bots_status(request: Request, _: str = Depends(require_auth)) -> Dict[str, Any]:
    return {"bots": request.app.state.bot_manager.snapshot()}


@app.post("/api/bots/start")
async def bots_start(body: BotSymbolsBody, request: Request, _: str = Depends(require_unlocked)) -> Dict[str, Any]:
    config: Dict[str, Any] = request.app.state.config.read()
    exchange_name = _exchange_name(config)
    symbols = [s for s in (_normalize_symbol(x) for x in body.symbols) if s]
    if await _fill_strategy_market_ids(request, config, symbols=set(symbols)):
        request.app.state.config.write(config)
    trader = await _ensure_trader(request, exchange_name)
    runtime_stats: Dict[str, Any] = request.app.state.runtime_stats
    now_ms = _now_ms()
    for sym in symbols:
        strat = (config.get("strategies", {}) or {}).get(sym, {}) or {}
        strat_exchange = str(strat.get("exchange") or "").strip().lower()
        if strat_exchange and strat_exchange != exchange_name:
            request.app.state.logbus.publish(
                f"bot.start.skip symbol={sym} exchange={exchange_name} reason=exchange_mismatch strat_exchange={strat_exchange}"
            )
            continue
        runtime_stats[sym] = {"exchange": exchange_name, "start_ms": now_ms, "base_pnl": None}
        await request.app.state.bot_manager.start(sym, trader)
    return {"ok": True, "bots": request.app.state.bot_manager.snapshot()}


@app.post("/api/bots/stop")
async def bots_stop(body: BotSymbolsBody, request: Request, _: str = Depends(require_auth)) -> Dict[str, Any]:
    config: Dict[str, Any] = request.app.state.config.read()
    exchange_name = _exchange_name(config)
    try:
        trader = await _ensure_trader(request, exchange_name)
        await request.app.state.bot_manager.capture_history(trader, body.symbols, "manual_stop")
    except Exception as exc:
        request.app.state.logbus.publish(f"history.capture.error err={type(exc).__name__}:{exc}")
    runtime_stats: Dict[str, Any] = request.app.state.runtime_stats
    for symbol in body.symbols:
        sym = symbol.upper()
        await request.app.state.bot_manager.stop(sym)
        runtime_stats.pop(sym, None)
    return {"ok": True, "bots": request.app.state.bot_manager.snapshot()}


@app.post("/api/bots/emergency_stop")
async def bots_emergency_stop(request: Request, _: str = Depends(require_auth)) -> Dict[str, Any]:
    config: Dict[str, Any] = request.app.state.config.read()
    exchange_name = _exchange_name(config)
    bots = request.app.state.bot_manager.snapshot()
    running_symbols = [s for s, data in bots.items() if isinstance(data, dict) and data.get("running")]
    trader: Optional[Trader]
    if exchange_name == "paradex":
        trader = request.app.state.paradex_trader
    elif exchange_name == "grvt":
        trader = request.app.state.grvt_trader
    else:
        trader = request.app.state.lighter_trader

    if trader is None:
        try:
            trader = await _ensure_trader(request, exchange_name)
        except Exception as exc:
            request.app.state.logbus.publish(f"emergency.init.error exchange={exchange_name} err={type(exc).__name__}:{exc}")
            trader = None

    if trader:
        try:
            await request.app.state.bot_manager.capture_history(trader, running_symbols, "emergency_stop")
        except Exception as exc:
            request.app.state.logbus.publish(f"history.capture.error err={type(exc).__name__}:{exc}")

    await request.app.state.bot_manager.stop_all()
    request.app.state.runtime_stats = {}
    canceled: Dict[str, int] = {}

    if trader is None:
        request.app.state.logbus.publish("bots.emergency_stop")
        return {"ok": True, "canceled": canceled, "bots": request.app.state.bot_manager.snapshot()}

    strategies = config.get("strategies", {}) or {}
    for symbol, strat in strategies.items():
        if not isinstance(strat, dict):
            continue
        market_id = strat.get("market_id")
        if market_id is None or (isinstance(market_id, str) and not market_id.strip()):
            continue
        try:
            orders = await trader.active_orders(market_id)
        except Exception as exc:
            request.app.state.logbus.publish(f"emergency.list.error symbol={symbol} err={type(exc).__name__}:{exc}")
            continue

        prefix = grid_prefix(trader.account_key, market_id, symbol)
        targets: list[tuple[Any, int]] = []
        for o in orders:
            cid = _order_client_id(o)
            if cid is None or cid <= 0:
                continue
            if not is_grid_client_order(prefix, cid):
                continue
            oid = _order_id(o)
            if oid is None:
                continue
            if isinstance(oid, int) and oid <= 0:
                continue
            targets.append((oid, cid))

        count = 0
        for oid, cid in targets[:200]:
            try:
                await trader.cancel_order(market_id, oid)
                count += 1
            except Exception as exc:
                request.app.state.logbus.publish(f"emergency.cancel.error symbol={symbol} id={cid} err={type(exc).__name__}:{exc}")
        if count:
            canceled[symbol] = count
    request.app.state.logbus.publish("bots.emergency_stop")
    return {"ok": True, "canceled": canceled, "bots": request.app.state.bot_manager.snapshot()}


@app.get("/api/logs/recent")
async def logs_recent(request: Request, _: str = Depends(require_auth)) -> Dict[str, Any]:
    return {"items": request.app.state.logbus.recent()}


@app.get("/api/logs/stream")
async def logs_stream(request: Request, _: str = Depends(require_auth)) -> StreamingResponse:
    return StreamingResponse(request.app.state.logbus.stream(), media_type="text/event-stream")


@app.get("/api/runtime/history")
async def runtime_history(
    request: Request,
    limit: int = 200,
    _: str = Depends(require_auth),
) -> Dict[str, Any]:
    store: HistoryStore = request.app.state.history_store
    return {"items": store.read(limit=limit)}


@app.get("/api/runtime/status")
async def runtime_status(
    request: Request,
    exchange: Optional[str] = None,
    _: str = Depends(require_auth),
) -> Dict[str, Any]:
    config: Dict[str, Any] = request.app.state.config.read()
    runtime = config.get("runtime", {}) or {}
    simulate = bool(runtime.get("dry_run", True)) and bool(runtime.get("simulate_fill", False))
    name = _exchange_name(config, exchange)
    bots = request.app.state.bot_manager.snapshot()
    runtime_stats: Dict[str, Any] = request.app.state.runtime_stats
    now_ms = _now_ms()
    updated_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    running_symbols: list[str] = []
    for symbol, data in bots.items():
        if isinstance(data, dict) and data.get("running"):
            running_symbols.append(symbol)

    if not running_symbols:
        return {
            "exchange": name,
            "updated_at": updated_at,
            "totals": {
                "profit": "0",
                "volume": "0",
                "trade_count": 0,
                "position_notional": "0",
                "open_orders": 0,
                "reduce_symbols": [],
                "running": 0,
            },
            "symbols": {},
        }

    if simulate:
        totals_profit = Decimal(0)
        totals_volume = Decimal(0)
        totals_trades = 0
        totals_position = Decimal(0)
        totals_orders = 0
        reduce_symbols: list[str] = []
        symbols_data: Dict[str, Any] = {}
        bot_manager = request.app.state.bot_manager

        for symbol in sorted(running_symbols):
            status = bots.get(symbol) or {}
            if not isinstance(status, dict):
                continue
            started_at = status.get("started_at")
            start_ms = _parse_iso_ms(started_at) or now_ms
            entry = runtime_stats.get(symbol)
            if not isinstance(entry, dict) or entry.get("exchange") != name:
                entry = {"exchange": name, "start_ms": start_ms, "base_pnl": None}
                runtime_stats[symbol] = entry
            if entry.get("start_ms") is None:
                entry["start_ms"] = start_ms
            start_ms = int(entry.get("start_ms") or start_ms)

            mid_value = _safe_decimal(status.get("mid") or 0)
            if mid_value <= 0:
                mid_value = bot_manager.sim_last_mid(symbol)

            sim_pnl = bot_manager.sim_pnl(symbol, mid_value)
            if entry.get("base_pnl") is None:
                entry["base_pnl"] = sim_pnl
            profit = sim_pnl - _safe_decimal(entry.get("base_pnl") or 0)

            volume, trade_count = bot_manager.sim_trade_stats(symbol, start_ms, now_ms)
            pos_base = bot_manager.sim_position_base(symbol)
            position_notional = abs(pos_base * mid_value) if mid_value > 0 else Decimal(0)
            open_orders = bot_manager.sim_open_orders(symbol)
            reduce_mode = bool(status.get("reduce_mode"))
            if reduce_mode:
                reduce_symbols.append(symbol)

            symbols_data[symbol] = {
                "symbol": symbol,
                "market_id": status.get("market_id"),
                "started_at": started_at,
                "profit": _fmt_decimal(profit),
                "volume": _fmt_decimal(volume),
                "trade_count": trade_count,
                "position_notional": _fmt_decimal(position_notional),
                "open_orders": open_orders,
                "delay_count": int(status.get("delay_count") or 0),
                "reduce_mode": reduce_mode,
            }

            totals_profit += profit
            totals_volume += volume
            totals_trades += trade_count
            totals_position += position_notional
            totals_orders += open_orders

        return {
            "exchange": name,
            "updated_at": updated_at,
            "totals": {
                "profit": _fmt_decimal(totals_profit),
                "volume": _fmt_decimal(totals_volume),
                "trade_count": totals_trades,
                "position_notional": _fmt_decimal(totals_position),
                "open_orders": totals_orders,
                "reduce_symbols": reduce_symbols,
                "running": len(symbols_data),
            },
            "symbols": symbols_data,
        }

    try:
        trader = await _ensure_trader(request, name)
    except Exception as exc:
        request.app.state.logbus.publish(f"runtime.status.error err={type(exc).__name__}:{exc}")
        return {"exchange": name, "updated_at": updated_at, "error": "无法建立交易所连接"}

    positions_map: Dict[Any, Dict[str, Decimal]]
    if name == "paradex" and isinstance(trader, ParadexTrader):
        positions_map = _paradex_positions_map(trader)
    elif name == "grvt" and isinstance(trader, GrvtTrader):
        positions_map = await _grvt_positions_map(trader)
    elif isinstance(trader, LighterTrader):
        positions_map = await _lighter_positions_map(trader)
    else:
        positions_map = {}

    totals_profit = Decimal(0)
    totals_volume = Decimal(0)
    totals_trades = 0
    totals_position = Decimal(0)
    totals_orders = 0
    reduce_symbols: list[str] = []
    symbols_data: Dict[str, Any] = {}

    for symbol in sorted(running_symbols):
        status = bots.get(symbol) or {}
        if not isinstance(status, dict):
            continue
        started_at = status.get("started_at")
        start_ms = _parse_iso_ms(started_at) or now_ms
        entry = runtime_stats.get(symbol)
        if not isinstance(entry, dict) or entry.get("exchange") != name:
            entry = {"exchange": name, "start_ms": start_ms, "base_pnl": None}
            runtime_stats[symbol] = entry
        if entry.get("start_ms") is None:
            entry["start_ms"] = start_ms
        start_ms = int(entry.get("start_ms") or start_ms)

        strat = (config.get("strategies", {}) or {}).get(symbol, {}) or {}
        market_id = strat.get("market_id")
        if market_id is None or (isinstance(market_id, str) and not market_id.strip()):
            market_id = status.get("market_id")
        if name in {"paradex", "grvt"} and market_id is not None:
            market_id = str(market_id)
        if name == "lighter" and isinstance(market_id, str):
            try:
                market_id = int(market_id)
            except Exception:
                pass

        mid_value = _safe_decimal(status.get("mid") or 0)
        if mid_value <= 0 and market_id is not None:
            try:
                bid, ask = await trader.best_bid_ask(market_id)
                if bid is not None and ask is not None:
                    mid_value = (bid + ask) / 2
            except Exception:
                mid_value = Decimal(0)

        pnl_now = Decimal(0)
        pos_base = Decimal(0)
        use_base = True
        if market_id is not None:
            pnl_item = positions_map.get(market_id)
            if pnl_item:
                pnl_now = _safe_decimal(pnl_item.get("pnl"))
                pos_base = _safe_decimal(pnl_item.get("base"))

        if name == "lighter" and isinstance(trader, LighterTrader) and isinstance(market_id, int):
            use_base = False
            try:
                pnl_now = await request.app.state.bot_manager.lighter_trade_pnl(
                    trader,
                    symbol,
                    int(market_id),
                    start_ms,
                    now_ms,
                    mid_value,
                )
            except Exception as exc:
                request.app.state.logbus.publish(
                    f"runtime.pnl.error symbol={symbol} market_id={market_id} err={type(exc).__name__}:{exc}"
                )

        if use_base:
            if entry.get("base_pnl") is None:
                entry["base_pnl"] = pnl_now
            profit = pnl_now - _safe_decimal(entry.get("base_pnl") or 0)
        else:
            profit = pnl_now

        volume = Decimal(0)
        trade_count = 0
        try:
            if name == "paradex" and isinstance(trader, ParadexTrader) and market_id is not None:
                volume, trade_count = _paradex_fills_since(trader, str(market_id), start_ms, now_ms)
            elif name == "grvt" and isinstance(trader, GrvtTrader) and market_id is not None:
                volume, trade_count = await _grvt_trades_since(trader, str(market_id), start_ms, now_ms)
            elif isinstance(trader, LighterTrader) and isinstance(market_id, int):
                volume, trade_count = await _lighter_trades_since(trader, int(market_id), start_ms)
        except Exception as exc:
            request.app.state.logbus.publish(
                f"runtime.trades.error symbol={symbol} market_id={market_id} err={type(exc).__name__}:{exc}"
            )

        position_notional = abs(pos_base * mid_value) if mid_value > 0 else Decimal(0)
        open_orders = int(status.get("existing") or 0)
        reduce_mode = bool(status.get("reduce_mode"))
        if reduce_mode:
            reduce_symbols.append(symbol)

        symbols_data[symbol] = {
            "symbol": symbol,
            "market_id": market_id,
            "started_at": started_at,
            "profit": _fmt_decimal(profit),
            "volume": _fmt_decimal(volume),
            "trade_count": trade_count,
            "position_notional": _fmt_decimal(position_notional),
            "open_orders": open_orders,
            "delay_count": int(status.get("delay_count") or 0),
            "reduce_mode": reduce_mode,
        }

        totals_profit += profit
        totals_volume += volume
        totals_trades += trade_count
        totals_position += position_notional
        totals_orders += open_orders

    return {
        "exchange": name,
        "updated_at": updated_at,
        "totals": {
            "profit": _fmt_decimal(totals_profit),
            "volume": _fmt_decimal(totals_volume),
            "trade_count": totals_trades,
            "position_notional": _fmt_decimal(totals_position),
            "open_orders": totals_orders,
            "reduce_symbols": reduce_symbols,
            "running": len(symbols_data),
        },
        "symbols": symbols_data,
    }


@app.get("/api/exchange/markets")
async def exchange_markets(
    request: Request,
    env: str = "mainnet",
    exchange: Optional[str] = None,
    _: str = Depends(require_auth),
) -> Dict[str, Any]:
    config: Dict[str, Any] = request.app.state.config.read()
    name = _exchange_name(config, exchange)
    try:
        if name == "paradex":
            items = await paradex_fetch_perp_markets(env)
        elif name == "grvt":
            items = await grvt_fetch_perp_markets(env)
        else:
            items = await lighter_fetch_perp_markets(env)
    except Exception as exc:
        request.app.state.logbus.publish(f"exchange.markets error={type(exc).__name__}:{exc}")
        raise HTTPException(status_code=502, detail="查询市场失败")
    return {"exchange": name, "items": items}


@app.post("/api/exchange/test_connection")
async def exchange_test_connection(
    request: Request,
    exchange: Optional[str] = None,
    _: str = Depends(require_unlocked),
) -> Dict[str, Any]:
    config: Dict[str, Any] = request.app.state.config.read()
    ex = config.get("exchange", {}) or {}
    env = str(ex.get("env") or "mainnet")
    name = _exchange_name(config, exchange)
    if name == "paradex":
        l1_address = _safe_str(ex.get("paradex_l1_address"))
        l2_address = _safe_str(ex.get("paradex_l2_address"))
        l1_key = _get_secret(request, "paradex_l1_private_key")
        l2_key = _get_secret(request, "paradex_l2_private_key")
        if not ((l2_address and l2_key) or (l1_address and l1_key)):
            raise HTTPException(status_code=400, detail="请先配置 Paradex L2 或 L1 私钥")
        try:
            result = await paradex_test_connection(env, l1_address, l1_key, l2_address, l2_key)
        except Exception as exc:
            request.app.state.logbus.publish(f"paradex.test_connection error={type(exc).__name__}:{exc}")
            raise HTTPException(status_code=502, detail="测试失败")
        return {"exchange": name, "result": result}

    if name == "grvt":
        account_id = _safe_str(ex.get("grvt_account_id"))
        api_key = _get_secret(request, "grvt_api_key")
        private_key = _get_secret(request, "grvt_private_key")
        if not account_id or not api_key or not private_key:
            raise HTTPException(status_code=400, detail="请填写 GRVT account_id、API Key 与私钥")
        try:
            result = await grvt_test_connection(env, account_id, api_key, private_key)
        except Exception as exc:
            request.app.state.logbus.publish(f"grvt.test_connection error={type(exc).__name__}:{exc}")
            raise HTTPException(status_code=502, detail="测试失败")
        return {"exchange": name, "result": result}

    account_index = _to_int(ex.get("account_index"))
    api_key_index = _to_int(ex.get("api_key_index"))
    api_private_key = _get_secret(request, "api_private_key")
    if account_index is None or api_key_index is None or not api_private_key:
        raise HTTPException(status_code=400, detail="请先完整配置 account_index、api_key_index、API 私钥")
    try:
        result = await lighter_test_connection(env, int(account_index), int(api_key_index), api_private_key)
    except Exception as exc:
        request.app.state.logbus.publish(f"lighter.test_connection error={type(exc).__name__}:{exc}")
        raise HTTPException(status_code=502, detail="测试失败")
    return {"exchange": name, "result": result}


@app.get("/api/exchange/active_orders")
async def exchange_active_orders(
    request: Request,
    symbol: str = "BTC",
    mine: bool = True,
    exchange: Optional[str] = None,
    _: str = Depends(require_unlocked),
) -> Dict[str, Any]:
    symbol = symbol.upper()
    config: Dict[str, Any] = request.app.state.config.read()
    runtime = config.get("runtime", {}) or {}
    simulate = bool(runtime.get("dry_run", True)) and bool(runtime.get("simulate_fill", False))
    name = _exchange_name(config, exchange)
    strat = (config.get("strategies", {}) or {}).get(symbol, {}) or {}
    market_id = _normalize_market_id(name, strat.get("market_id"))
    if market_id is None:
        if await _fill_strategy_market_ids(request, config, symbols={symbol}):
            request.app.state.config.write(config)
            strat = (config.get("strategies", {}) or {}).get(symbol, {}) or {}
            market_id = _normalize_market_id(name, strat.get("market_id"))
    if market_id is None:
        raise HTTPException(status_code=400, detail="未配置 market_id")

    if simulate:
        orders = request.app.state.bot_manager.sim_orders(symbol)
        items = [_order_to_dict(o) for o in orders]
        return {"exchange": name, "symbol": symbol, "market_id": market_id, "orders": items}

    trader = await _ensure_trader(request, name)
    orders = await trader.active_orders(market_id)
    prefix = grid_prefix(trader.account_key, market_id, symbol)

    items: list[Dict[str, Any]] = []
    for o in orders:
        cid = _order_client_id(o)
        if mine and (cid is None or not is_grid_client_order(prefix, cid)):
            continue
        items.append(_order_to_dict(o))
    return {"exchange": name, "symbol": symbol, "market_id": market_id, "orders": items}


@app.get("/api/exchange/account_snapshot")
async def exchange_account_snapshot(
    request: Request,
    exchange: Optional[str] = None,
    _: str = Depends(require_unlocked),
) -> Dict[str, Any]:
    config: Dict[str, Any] = request.app.state.config.read()
    name = _exchange_name(config, exchange)
    ex = config.get("exchange", {}) or {}
    if name == "paradex":
        trader = await _ensure_paradex_trader(request)
        summary = trader._api.fetch_account_summary()
        if hasattr(summary, "model_dump"):
            data = summary.model_dump()
        elif hasattr(summary, "to_dict"):
            data = summary.to_dict()
        else:
            data = getattr(summary, "__dict__", {"raw": str(summary)})
        return {"exchange": name, "account": data}

    if name == "grvt":
        trader = await _ensure_grvt_trader(request)
        summary = await trader._api.get_account_summary()
        if hasattr(summary, "model_dump"):
            data = summary.model_dump()
        elif hasattr(summary, "to_dict"):
            data = summary.to_dict()
        else:
            data = getattr(summary, "__dict__", {"raw": str(summary)})
        return {"exchange": name, "account": data}

    account_index = _to_int(ex.get("account_index"))
    if account_index is None:
        raise HTTPException(status_code=400, detail="未配置 account_index")

    import lighter

    url = lighter_base_url(str(ex.get("env") or "mainnet"))
    api_client = lighter.ApiClient(configuration=lighter.Configuration(host=url))
    try:
        account_api = lighter.AccountApi(api_client)
        resp = await account_api.account(by="index", value=str(int(account_index)))
        if hasattr(resp, "model_dump"):
            data = resp.model_dump()
        elif hasattr(resp, "to_dict"):
            data = resp.to_dict()
        else:
            data = {"raw": str(resp)}
        return {"exchange": name, "account": data}
    finally:
        await api_client.close()


@app.post("/api/lighter/resolve_account_index")
async def lighter_resolve_account_index(
    body: ResolveAccountIndexBody,
    request: Request,
    _: str = Depends(require_auth),
) -> Dict[str, Any]:
    try:
        client = LighterPublicClient(env=body.env)
        idx = client.resolve_account_index(body.l1_address)
    except Exception as exc:
        request.app.state.logbus.publish(f"lighter.resolve_account_index error={type(exc).__name__}:{exc}")
        raise HTTPException(status_code=502, detail="查询失败")
    if idx is None:
        raise HTTPException(status_code=404, detail="未找到 account_index")
    return {"account_index": idx}


@app.get("/api/lighter/markets")
async def lighter_markets(request: Request, env: str = "mainnet", _: str = Depends(require_auth)) -> Dict[str, Any]:
    try:
        items = await lighter_fetch_perp_markets(env)
    except Exception as exc:
        request.app.state.logbus.publish(f"lighter.markets error={type(exc).__name__}:{exc}")
        raise HTTPException(status_code=502, detail="查询市场失败")
    return {"items": items}


@app.post("/api/lighter/test_connection")
async def lighter_test(request: Request, _: str = Depends(require_unlocked)) -> Dict[str, Any]:
    config: Dict[str, Any] = request.app.state.config.read()
    ex = config.get("exchange", {})
    env = str(ex.get("env") or "mainnet")
    account_index = _to_int(ex.get("account_index"))
    api_key_index = _to_int(ex.get("api_key_index"))
    api_private_key = _get_secret(request, "api_private_key")
    if account_index is None or api_key_index is None or not api_private_key:
        raise HTTPException(status_code=400, detail="请先完整配置 account_index、api_key_index、API 私钥")
    try:
        result = await lighter_test_connection(env, int(account_index), int(api_key_index), api_private_key)
    except Exception as exc:
        request.app.state.logbus.publish(f"lighter.test_connection error={type(exc).__name__}:{exc}")
        raise HTTPException(status_code=502, detail="测试失败")
    return {"result": result}


@app.get("/api/lighter/active_orders")
async def lighter_active_orders(
    request: Request,
    symbol: str = "BTC",
    mine: bool = True,
    _: str = Depends(require_unlocked),
) -> Dict[str, Any]:
    symbol = symbol.upper()
    config: Dict[str, Any] = request.app.state.config.read()
    strat = (config.get("strategies", {}) or {}).get(symbol, {}) or {}
    market_id = strat.get("market_id")
    if market_id is None or (isinstance(market_id, str) and not market_id.strip()):
        raise HTTPException(status_code=400, detail="未配置 market_id")

    trader = await _ensure_lighter_trader(request)
    orders = await trader.active_orders(market_id)
    prefix = grid_prefix(trader.account_key, market_id, symbol)

    items = []
    for o in orders:
        cid = int(getattr(o, "client_order_index", 0) or 0)
        if mine and not is_grid_client_order(prefix, cid):
            continue
        items.append(
            {
                "client_order_index": cid,
                "order_index": int(getattr(o, "order_index", 0) or 0),
                "is_ask": bool(getattr(o, "is_ask", False)),
                "price": getattr(o, "price", None),
                "base_price": int(getattr(o, "base_price", 0) or 0),
                "base_size": int(getattr(o, "base_size", 0) or 0),
                "remaining_base_amount": getattr(o, "remaining_base_amount", None),
                "status": getattr(o, "status", None),
                "created_at": getattr(o, "created_at", None),
                "updated_at": getattr(o, "updated_at", None),
            }
        )
    return {"symbol": symbol, "market_id": market_id, "orders": items}


@app.get("/api/lighter/account_snapshot")
async def lighter_account_snapshot(request: Request, _: str = Depends(require_auth)) -> Dict[str, Any]:
    config: Dict[str, Any] = request.app.state.config.read()
    ex = config.get("exchange", {})
    env = str(ex.get("env") or "mainnet")
    account_index = _to_int(ex.get("account_index"))
    if account_index is None:
        raise HTTPException(status_code=400, detail="未配置 account_index")

    import lighter

    url = lighter_base_url(env)
    api_client = lighter.ApiClient(configuration=lighter.Configuration(host=url))
    try:
        account_api = lighter.AccountApi(api_client)
        resp = await account_api.account(by="index", value=str(int(account_index)))
        if hasattr(resp, "model_dump"):
            data = resp.model_dump()
        elif hasattr(resp, "to_dict"):
            data = resp.to_dict()
        else:
            data = {"raw": str(resp)}
        return {"account": data}
    finally:
        await api_client.close()


def _get_secret(request: Request, name: str) -> Optional[str]:
    config: Dict[str, Any] = request.app.state.config.read()
    runtime: Dict[str, str] = request.app.state.runtime_secrets
    if name in runtime:
        return runtime.get(name)

    fernet: Optional[Fernet] = request.app.state.fernet
    if not fernet:
        return None

    enc_field = {
        "api_private_key": "api_private_key_enc",
        "eth_private_key": "eth_private_key_enc",
        "grvt_api_key": "grvt_api_key_enc",
        "grvt_private_key": "grvt_private_key_enc",
        "paradex_l1_private_key": "paradex_l1_private_key_enc",
        "paradex_l2_private_key": "paradex_l2_private_key_enc",
    }.get(name)
    if not enc_field:
        return None
    token = config.get("exchange", {}).get(enc_field) or ""
    if not token:
        return None
    try:
        return decrypt_str(fernet, token)
    except Exception:
        return None


async def _ensure_paradex_trader(request: Request) -> ParadexTrader:
    config: Dict[str, Any] = request.app.state.config.read()
    ex = config.get("exchange", {})
    env = str(ex.get("env") or "mainnet")
    l1_address = _safe_str(ex.get("paradex_l1_address"))
    l2_address = _safe_str(ex.get("paradex_l2_address"))
    l1_private_key = _get_secret(request, "paradex_l1_private_key")
    l2_private_key = _get_secret(request, "paradex_l2_private_key")
    if not ((l2_address and l2_private_key) or (l1_address and l1_private_key)):
        raise HTTPException(status_code=400, detail="请先配置 Paradex L2 或 L1 私钥")

    sig = (env, l1_address, l2_address, _secret_fingerprint(l1_private_key), _secret_fingerprint(l2_private_key))
    existing: Optional[ParadexTrader] = request.app.state.paradex_trader
    existing_sig = request.app.state.paradex_trader_sig
    if existing and existing_sig == sig:
        return existing

    if existing:
        await existing.close()

    trader = ParadexTrader(
        env=env,
        l1_address=l1_address,
        l1_private_key=l1_private_key,
        l2_address=l2_address,
        l2_private_key=l2_private_key,
    )
    err = trader.check_client()
    if err is not None:
        await trader.close()
        raise HTTPException(status_code=400, detail=f"API Key 校验失败：{err}")

    request.app.state.paradex_trader = trader
    request.app.state.paradex_trader_sig = sig
    return trader


async def _ensure_grvt_trader(request: Request) -> GrvtTrader:
    config: Dict[str, Any] = request.app.state.config.read()
    ex = config.get("exchange", {})
    env = str(ex.get("env") or "mainnet")
    account_id = _safe_str(ex.get("grvt_account_id"))
    api_key = _get_secret(request, "grvt_api_key")
    private_key = _get_secret(request, "grvt_private_key")
    if not account_id or not api_key or not private_key:
        raise HTTPException(status_code=400, detail="请填写 GRVT account_id、API Key 与私钥")

    sig = (env, account_id, _secret_fingerprint(api_key), _secret_fingerprint(private_key))
    existing: Optional[GrvtTrader] = request.app.state.grvt_trader
    existing_sig = request.app.state.grvt_trader_sig
    if existing and existing_sig == sig:
        return existing

    if existing:
        await existing.close()

    try:
        trader = GrvtTrader(
            env=env,
            trading_account_id=account_id,
            api_key=api_key,
            private_key=private_key,
        )
    except ModuleNotFoundError as exc:
        name = getattr(exc, "name", "") or ""
        if name.startswith("pysdk"):
            raise HTTPException(status_code=400, detail="GRVT 依赖 pysdk 未安装，请先安装或切换交易所") from exc
        raise
    err = await trader.verify()
    if err is not None:
        await trader.close()
        raise HTTPException(status_code=400, detail=f"API Key 验证失败：{err}")

    request.app.state.grvt_trader = trader
    request.app.state.grvt_trader_sig = sig
    return trader


async def _ensure_trader(request: Request, exchange: Optional[str] = None) -> Trader:
    config: Dict[str, Any] = request.app.state.config.read()
    name = _exchange_name(config, exchange)
    if name == "paradex":
        return await _ensure_paradex_trader(request)
    if name == "grvt":
        return await _ensure_grvt_trader(request)
    return await _ensure_lighter_trader(request)


async def _ensure_lighter_trader(request: Request) -> LighterTrader:
    config: Dict[str, Any] = request.app.state.config.read()
    ex = config.get("exchange", {})
    env = str(ex.get("env") or "mainnet")
    account_index = _to_int(ex.get("account_index"))
    api_key_index = _to_int(ex.get("api_key_index"))
    api_private_key = _get_secret(request, "api_private_key")
    if account_index is None or api_key_index is None or not api_private_key:
        raise HTTPException(status_code=400, detail="请先完整配置 account_index、api_key_index、API 私钥")

    sig = (env, int(account_index), int(api_key_index), _secret_fingerprint(api_private_key))
    existing: Optional[LighterTrader] = request.app.state.lighter_trader
    existing_sig = request.app.state.lighter_trader_sig
    if existing and existing_sig == sig:
        return existing

    if existing:
        await existing.close()

    trader = LighterTrader(
        env=env,
        account_index=int(account_index),
        api_key_index=int(api_key_index),
        api_private_key=api_private_key,
        logbus=request.app.state.logbus,
    )
    err = trader.check_client()
    if err is not None:
        await trader.close()
        raise HTTPException(status_code=400, detail=f"API Key 校验失败：{err}")

    request.app.state.lighter_trader = trader
    request.app.state.lighter_trader_sig = sig
    return trader
