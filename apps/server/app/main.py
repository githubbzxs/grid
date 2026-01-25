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
from app.exchanges.lighter.public_api import LighterPublicClient
from app.services.bot_manager import BotManager


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
    app.state.bot_manager = BotManager(app.state.logbus)
    app.state.sessions = {}
    app.state.fernet = None
    app.state.runtime_secrets = {}
    app.state.logbus.publish("server.start")


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
async def bots_start(body: BotSymbolsBody, request: Request, _: str = Depends(require_auth)) -> Dict[str, Any]:
    for symbol in body.symbols:
        await request.app.state.bot_manager.start(symbol.upper())
    return {"ok": True, "bots": request.app.state.bot_manager.snapshot()}


@app.post("/api/bots/stop")
async def bots_stop(body: BotSymbolsBody, request: Request, _: str = Depends(require_auth)) -> Dict[str, Any]:
    for symbol in body.symbols:
        await request.app.state.bot_manager.stop(symbol.upper())
    return {"ok": True, "bots": request.app.state.bot_manager.snapshot()}


@app.post("/api/bots/emergency_stop")
async def bots_emergency_stop(request: Request, _: str = Depends(require_auth)) -> Dict[str, Any]:
    await request.app.state.bot_manager.stop_all()
    request.app.state.logbus.publish("bots.emergency_stop")
    return {"ok": True, "bots": request.app.state.bot_manager.snapshot()}


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
