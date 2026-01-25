from __future__ import annotations

import secrets
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
from app.exchanges.lighter.public_api import LighterPublicClient, base_url as lighter_base_url
from app.exchanges.lighter.sdk_ops import fetch_perp_markets, test_connection as lighter_test_connection
from app.exchanges.lighter.trader import LighterTrader
from app.services.bot_manager import BotManager
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


def _mask_config(config: Dict[str, Any]) -> Dict[str, Any]:
    exchange = dict(config.get("exchange", {}))
    exchange.pop("api_private_key_enc", None)
    exchange.pop("eth_private_key_enc", None)
    exchange["api_private_key_set"] = bool(config.get("exchange", {}).get("api_private_key_enc"))
    exchange["eth_private_key_set"] = bool(config.get("exchange", {}).get("eth_private_key_enc"))
    result = dict(config)
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
    app.state.sessions = {}
    app.state.fernet = None
    app.state.runtime_secrets = {}
    app.state.lighter_trader = None
    app.state.lighter_trader_sig = None
    app.state.logbus.publish("server.start")


@app.on_event("shutdown")
async def _shutdown() -> None:
    trader: Optional[LighterTrader] = getattr(app.state, "lighter_trader", None)
    if trader:
        await trader.close()


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(str(WEB_DIR / "index.html"))


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
    exchange_patch = dict(patch.get("exchange") or {})
    plaintext_api_key = exchange_patch.pop("api_private_key", None)
    plaintext_eth_key = exchange_patch.pop("eth_private_key", None)

    if "exchange" in patch:
        patch = dict(patch)
        patch["exchange"] = exchange_patch

    merged = request.app.state.config.update(patch)

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

    request.app.state.config.write(merged)
    request.app.state.logbus.publish("config.update")
    return {"ok": True, "config": _mask_config(merged)}


@app.get("/api/bots/status")
async def bots_status(request: Request, _: str = Depends(require_auth)) -> Dict[str, Any]:
    return {"bots": request.app.state.bot_manager.snapshot()}


@app.post("/api/bots/start")
async def bots_start(body: BotSymbolsBody, request: Request, _: str = Depends(require_unlocked)) -> Dict[str, Any]:
    trader = await _ensure_lighter_trader(request)
    for symbol in body.symbols:
        await request.app.state.bot_manager.start(symbol.upper(), trader)
    return {"ok": True, "bots": request.app.state.bot_manager.snapshot()}


@app.post("/api/bots/stop")
async def bots_stop(body: BotSymbolsBody, request: Request, _: str = Depends(require_auth)) -> Dict[str, Any]:
    for symbol in body.symbols:
        await request.app.state.bot_manager.stop(symbol.upper())
    return {"ok": True, "bots": request.app.state.bot_manager.snapshot()}


@app.post("/api/bots/emergency_stop")
async def bots_emergency_stop(request: Request, _: str = Depends(require_auth)) -> Dict[str, Any]:
    await request.app.state.bot_manager.stop_all()
    canceled: Dict[str, int] = {}
    trader: Optional[LighterTrader] = request.app.state.lighter_trader
    if trader:
        config: Dict[str, Any] = request.app.state.config.read()
        strategies = config.get("strategies", {}) or {}
        for symbol, strat in strategies.items():
            if not isinstance(strat, dict):
                continue
            market_id = strat.get("market_id")
            if not isinstance(market_id, int):
                continue
            try:
                orders = await trader.active_orders(market_id)
            except Exception as exc:
                request.app.state.logbus.publish(f"emergency.list.error symbol={symbol} err={type(exc).__name__}:{exc}")
                continue

            prefix = grid_prefix(trader.account_index, market_id, symbol)
            ids = []
            for o in orders:
                cid = int(getattr(o, "client_order_index", 0) or 0)
                if cid > 0 and is_grid_client_order(prefix, cid):
                    ids.append(cid)

            count = 0
            for cid in ids[:200]:
                try:
                    await trader.cancel_order(market_id, cid)
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
        items = await fetch_perp_markets(env)
    except Exception as exc:
        request.app.state.logbus.publish(f"lighter.markets error={type(exc).__name__}:{exc}")
        raise HTTPException(status_code=502, detail="查询市场失败")
    return {"items": items}


@app.post("/api/lighter/test_connection")
async def lighter_test(request: Request, _: str = Depends(require_unlocked)) -> Dict[str, Any]:
    config: Dict[str, Any] = request.app.state.config.read()
    ex = config.get("exchange", {})
    env = str(ex.get("env") or "mainnet")
    account_index = ex.get("account_index")
    api_key_index = ex.get("api_key_index")
    api_private_key = _get_secret(request, "api_private_key")
    if not isinstance(account_index, int) or not isinstance(api_key_index, int) or not api_private_key:
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
    if not isinstance(market_id, int):
        raise HTTPException(status_code=400, detail="未配置 market_id")

    trader = await _ensure_lighter_trader(request)
    orders = await trader.active_orders(market_id)
    prefix = grid_prefix(trader.account_index, market_id, symbol)

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
    account_index = ex.get("account_index")
    if not isinstance(account_index, int):
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


async def _ensure_lighter_trader(request: Request) -> LighterTrader:
    config: Dict[str, Any] = request.app.state.config.read()
    ex = config.get("exchange", {})
    env = str(ex.get("env") or "mainnet")
    account_index = ex.get("account_index")
    api_key_index = ex.get("api_key_index")
    api_private_key = _get_secret(request, "api_private_key")
    if not isinstance(account_index, int) or not isinstance(api_key_index, int) or not api_private_key:
        raise HTTPException(status_code=400, detail="请先完整配置 account_index、api_key_index、API 私钥")

    sig = (env, int(account_index), int(api_key_index))
    existing: Optional[LighterTrader] = request.app.state.lighter_trader
    existing_sig = request.app.state.lighter_trader_sig
    if existing and existing_sig == sig:
        return existing

    if existing:
        await existing.close()

    trader = LighterTrader(env=env, account_index=int(account_index), api_key_index=int(api_key_index), api_private_key=api_private_key)
    err = trader.check_client()
    if err is not None:
        await trader.close()
        raise HTTPException(status_code=400, detail=f"API Key 校验失败：{err}")

    request.app.state.lighter_trader = trader
    request.app.state.lighter_trader_sig = sig
    return trader
