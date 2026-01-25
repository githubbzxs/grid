const els = {
  dotAuth: document.getElementById("dot-auth"),
  pillText: document.getElementById("pill-text"),
  authCard: document.getElementById("auth-card"),
  authStatus: document.getElementById("auth-status"),
  password: document.getElementById("password"),
  btnSetup: document.getElementById("btn-setup"),
  btnLogin: document.getElementById("btn-login"),
  btnLogout: document.getElementById("btn-logout"),
  btnLock: document.getElementById("btn-lock"),
  appArea: document.getElementById("app-area"),

  exName: document.getElementById("ex-name"),
  exEnv: document.getElementById("ex-env"),
  lighterFields: document.getElementById("lighter-fields"),
  paradexFields: document.getElementById("paradex-fields"),
  exL1: document.getElementById("ex-l1"),
  exAccount: document.getElementById("ex-account"),
  btnResolveAccount: document.getElementById("btn-resolve-account"),
  exKeyIndex: document.getElementById("ex-key-index"),
  exApiKey: document.getElementById("ex-api-key"),
  exEthKey: document.getElementById("ex-eth-key"),
  pxL1: document.getElementById("px-l1"),
  pxL1Key: document.getElementById("px-l1-key"),
  pxL1KeyHint: document.getElementById("px-l1-key-hint"),
  pxL2: document.getElementById("px-l2"),
  pxL2Key: document.getElementById("px-l2-key"),
  pxL2KeyHint: document.getElementById("px-l2-key-hint"),
  exRemember: document.getElementById("ex-remember"),
  exApiKeyHint: document.getElementById("ex-api-key-hint"),
  exEthKeyHint: document.getElementById("ex-eth-key-hint"),
  btnSaveConfig: document.getElementById("btn-save-config"),
  btnFetchMarkets: document.getElementById("btn-fetch-markets"),
  btnTestConn: document.getElementById("btn-test-conn"),
  marketsOutput: document.getElementById("markets-output"),
  testOutput: document.getElementById("test-output"),

  stBtcEnabled: document.getElementById("st-btc-enabled"),
  stBtcMarket: document.getElementById("st-btc-market"),
  stBtcStep: document.getElementById("st-btc-step"),
  stBtcUp: document.getElementById("st-btc-up"),
  stBtcDown: document.getElementById("st-btc-down"),
  stBtcMode: document.getElementById("st-btc-mode"),
  stBtcSize: document.getElementById("st-btc-size"),
  stBtcMaxPos: document.getElementById("st-btc-maxpos"),
  stBtcExitPos: document.getElementById("st-btc-exitpos"),
  stBtcReduce: document.getElementById("st-btc-reduce"),

  stEthEnabled: document.getElementById("st-eth-enabled"),
  stEthMarket: document.getElementById("st-eth-market"),
  stEthStep: document.getElementById("st-eth-step"),
  stEthUp: document.getElementById("st-eth-up"),
  stEthDown: document.getElementById("st-eth-down"),
  stEthMode: document.getElementById("st-eth-mode"),
  stEthSize: document.getElementById("st-eth-size"),
  stEthMaxPos: document.getElementById("st-eth-maxpos"),
  stEthExitPos: document.getElementById("st-eth-exitpos"),
  stEthReduce: document.getElementById("st-eth-reduce"),

  stSolEnabled: document.getElementById("st-sol-enabled"),
  stSolMarket: document.getElementById("st-sol-market"),
  stSolStep: document.getElementById("st-sol-step"),
  stSolUp: document.getElementById("st-sol-up"),
  stSolDown: document.getElementById("st-sol-down"),
  stSolMode: document.getElementById("st-sol-mode"),
  stSolSize: document.getElementById("st-sol-size"),
  stSolMaxPos: document.getElementById("st-sol-maxpos"),
  stSolExitPos: document.getElementById("st-sol-exitpos"),
  stSolReduce: document.getElementById("st-sol-reduce"),

  runtimeDryRun: document.getElementById("runtime-dry-run"),
  runtimeInterval: document.getElementById("runtime-interval"),
  runtimeStatusInterval: document.getElementById("runtime-status-interval"),
  btnSaveStrategies: document.getElementById("btn-save-strategies"),
  btnAutoMarket: document.getElementById("btn-auto-market"),

  btnStartAll: document.getElementById("btn-start-all"),
  btnStopAll: document.getElementById("btn-stop-all"),
  btnEmergency: document.getElementById("btn-emergency"),
  botsTbody: document.getElementById("bots-tbody"),

  btnRefreshAccount: document.getElementById("btn-refresh-account"),
  accountOutput: document.getElementById("account-output"),
  ordersSymbol: document.getElementById("orders-symbol"),
  ordersMine: document.getElementById("orders-mine"),
  btnRefreshOrders: document.getElementById("btn-refresh-orders"),
  ordersOutput: document.getElementById("orders-output"),

  rtProfit: document.getElementById("rt-profit"),
  rtVolume: document.getElementById("rt-volume"),
  rtPosition: document.getElementById("rt-position"),
  rtTrades: document.getElementById("rt-trades"),
  rtOrders: document.getElementById("rt-orders"),
  rtReduce: document.getElementById("rt-reduce"),
  rtUpdated: document.getElementById("rt-updated"),
  runtimeTbody: document.getElementById("runtime-tbody"),

  logs: document.getElementById("logs"),
};

let authState = { setup_required: true, authenticated: false, unlocked: false };
let logSource = null;
let lastMarkets = [];
let runtimeTimer = null;

function currentExchange() {
  const name = (els.exName && els.exName.value) || "lighter";
  return String(name).toLowerCase() === "paradex" ? "paradex" : "lighter";
}

function applyExchangeUI() {
  const isParadex = currentExchange() === "paradex";
  if (els.lighterFields) els.lighterFields.hidden = isParadex;
  if (els.paradexFields) els.paradexFields.hidden = !isParadex;
}

async function apiFetch(path, { method = "GET", body = null } = {}) {
  const resp = await fetch(path, {
    method,
    credentials: "include",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await resp.text();
  let json = null;
  try {
    json = text ? JSON.parse(text) : null;
  } catch {
    json = null;
  }
  if (!resp.ok) {
    const msg = (json && (json.detail || json.message)) || text || `HTTP ${resp.status}`;
    throw new Error(msg);
  }
  return json;
}

function setPill(ok, text) {
  els.dotAuth.classList.remove("ok", "bad");
  els.dotAuth.classList.add(ok ? "ok" : "bad");
  els.pillText.textContent = text;
}

function setAuthCardInfo(text) {
  els.authStatus.textContent = text;
}

function showApp(show) {
  els.appArea.hidden = !show;
}

function appendLog(line) {
  const maxLines = 400;
  const current = els.logs.textContent.split("\n").filter((x) => x.length);
  current.push(line);
  const sliced = current.slice(-maxLines);
  els.logs.textContent = sliced.join("\n") + "\n";
  els.logs.scrollTop = els.logs.scrollHeight;
}

function startLogStream() {
  if (logSource) return;
  logSource = new EventSource("/api/logs/stream");
  logSource.onmessage = (ev) => appendLog(ev.data);
  logSource.onerror = () => {
    logSource.close();
    logSource = null;
  };
}

async function refreshAuth() {
  try {
    authState = await apiFetch("/api/auth/status");
    const s = `setup_required=${authState.setup_required} authenticated=${authState.authenticated} unlocked=${authState.unlocked}`;
    setAuthCardInfo(s);
    if (authState.setup_required) {
      setPill(false, "需要初始化");
      showApp(false);
      if (runtimeTimer) {
        clearInterval(runtimeTimer);
        runtimeTimer = null;
      }
      return;
    }
    if (!authState.authenticated) {
      setPill(false, "未登录");
      showApp(false);
      if (runtimeTimer) {
        clearInterval(runtimeTimer);
        runtimeTimer = null;
      }
      return;
    }
    if (!authState.unlocked) {
      setPill(false, "已登录但未解锁");
      showApp(false);
      if (runtimeTimer) {
        clearInterval(runtimeTimer);
        runtimeTimer = null;
      }
      return;
    }
    setPill(true, "已解锁");
    showApp(true);
    startLogStream();
    await loadConfig();
    await refreshBots();
    await refreshRuntimeStatus();
    startRuntimeLoop();
  } catch (e) {
    setPill(false, `错误：${e.message}`);
    showApp(false);
  }
}

async function setup() {
  const password = els.password.value || "";
  await apiFetch("/api/auth/setup", { method: "POST", body: { password } });
  els.password.value = "";
  await refreshAuth();
}

async function login() {
  const password = els.password.value || "";
  await apiFetch("/api/auth/login", { method: "POST", body: { password } });
  els.password.value = "";
  await refreshAuth();
}

async function logout() {
  await apiFetch("/api/auth/logout", { method: "POST" });
  if (logSource) {
    logSource.close();
    logSource = null;
  }
  if (runtimeTimer) {
    clearInterval(runtimeTimer);
    runtimeTimer = null;
  }
  await refreshAuth();
}

async function lock() {
  await apiFetch("/api/auth/lock", { method: "POST" });
  if (logSource) {
    logSource.close();
    logSource = null;
  }
  if (runtimeTimer) {
    clearInterval(runtimeTimer);
    runtimeTimer = null;
  }
  await refreshAuth();
}

function fillConfig(cfg) {
  const ex = cfg.exchange || {};
  els.exName.value = ex.name || "lighter";
  els.exEnv.value = ex.env || "mainnet";
  els.exL1.value = ex.l1_address || "";
  els.exAccount.value = ex.account_index == null ? "" : String(ex.account_index);
  els.exKeyIndex.value = ex.api_key_index == null ? "" : String(ex.api_key_index);
  els.exRemember.value = String(Boolean(ex.remember_secrets));
  els.exApiKeyHint.textContent = ex.api_private_key_set ? "已保存（加密）" : "未保存";
  els.exEthKeyHint.textContent = ex.eth_private_key_set ? "已保存（加密）" : "未保存";
  els.pxL1.value = ex.paradex_l1_address || "";
  els.pxL2.value = ex.paradex_l2_address || "";
  els.pxL1KeyHint.textContent = ex.paradex_l1_private_key_set ? "已保存（加密）" : "未保存";
  els.pxL2KeyHint.textContent = ex.paradex_l2_private_key_set ? "已保存（加密）" : "未保存";

  const rt = cfg.runtime || {};
  els.runtimeDryRun.value = String(Boolean(rt.dry_run));
  els.runtimeInterval.value = rt.loop_interval_ms == null ? "100" : String(rt.loop_interval_ms);
  if (els.runtimeStatusInterval) {
    els.runtimeStatusInterval.value = rt.status_refresh_ms == null ? "1000" : String(rt.status_refresh_ms);
  }

  const st = cfg.strategies || {};
  fillStrategyRow("BTC", st.BTC || {}, "btc");
  fillStrategyRow("ETH", st.ETH || {}, "eth");
  fillStrategyRow("SOL", st.SOL || {}, "sol");

  applyExchangeUI();
}

function fillStrategyRow(symbol, s, key) {
  const enabled = Boolean(s.enabled);
  const market = s.market_id == null ? "" : String(s.market_id);
  const step = s.grid_step == null ? "" : String(s.grid_step);
  const up = s.levels_up == null ? "" : String(s.levels_up);
  const down = s.levels_down == null ? "" : String(s.levels_down);
  const mode = s.order_size_mode || "notional";
  const size = s.order_size_value == null ? "" : String(s.order_size_value);
  const maxpos = s.max_position_notional == null ? "" : String(s.max_position_notional);
  const exitpos = s.reduce_position_notional == null ? "" : String(s.reduce_position_notional);
  const reduce = s.reduce_order_size_multiplier == null ? "" : String(s.reduce_order_size_multiplier);

  if (key === "btc") {
    els.stBtcEnabled.checked = enabled;
    els.stBtcMarket.value = market;
    els.stBtcStep.value = step;
    els.stBtcUp.value = up;
    els.stBtcDown.value = down;
    els.stBtcMode.value = mode;
    els.stBtcSize.value = size;
    els.stBtcMaxPos.value = maxpos;
    els.stBtcExitPos.value = exitpos;
    els.stBtcReduce.value = reduce;
  } else if (key === "eth") {
    els.stEthEnabled.checked = enabled;
    els.stEthMarket.value = market;
    els.stEthStep.value = step;
    els.stEthUp.value = up;
    els.stEthDown.value = down;
    els.stEthMode.value = mode;
    els.stEthSize.value = size;
    els.stEthMaxPos.value = maxpos;
    els.stEthExitPos.value = exitpos;
    els.stEthReduce.value = reduce;
  } else if (key === "sol") {
    els.stSolEnabled.checked = enabled;
    els.stSolMarket.value = market;
    els.stSolStep.value = step;
    els.stSolUp.value = up;
    els.stSolDown.value = down;
    els.stSolMode.value = mode;
    els.stSolSize.value = size;
    els.stSolMaxPos.value = maxpos;
    els.stSolExitPos.value = exitpos;
    els.stSolReduce.value = reduce;
  }
}

async function loadConfig() {
  const resp = await apiFetch("/api/config");
  fillConfig(resp.config || {});
}

async function saveConfig() {
  const exchange = {
    name: currentExchange(),
    env: els.exEnv.value,
    remember_secrets: els.exRemember.value === "true",
  };
  if (exchange.name === "paradex") {
    exchange.paradex_l1_address = els.pxL1.value.trim();
    exchange.paradex_l2_address = els.pxL2.value.trim();
    const l1_key = els.pxL1Key.value.trim();
    const l2_key = els.pxL2Key.value.trim();
    if (l1_key) exchange.paradex_l1_private_key = l1_key;
    if (l2_key) exchange.paradex_l2_private_key = l2_key;
  } else {
    exchange.l1_address = els.exL1.value.trim();
    exchange.account_index = els.exAccount.value.trim() ? Math.floor(Number(els.exAccount.value.trim())) : null;
    exchange.api_key_index = els.exKeyIndex.value.trim() ? Math.floor(Number(els.exKeyIndex.value.trim())) : null;
    const api_private_key = els.exApiKey.value.trim();
    const eth_private_key = els.exEthKey.value.trim();
    if (api_private_key) exchange.api_private_key = api_private_key;
    if (eth_private_key) exchange.eth_private_key = eth_private_key;
  }

  const resp = await apiFetch("/api/config", { method: "POST", body: { exchange } });
  fillConfig(resp.config || {});
  els.exApiKey.value = "";
  els.exEthKey.value = "";
  els.pxL1Key.value = "";
  els.pxL2Key.value = "";
}

function numOrNull(v) {
  const s = String(v || "").trim();
  if (!s) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

function numOrZero(v) {
  const n = numOrNull(v);
  return n == null ? 0 : n;
}

function marketIdValue(input) {
  const raw = String(input.value || "").trim();
  if (!raw) return null;
  if (currentExchange() === "paradex") return raw;
  const n = Number(raw);
  return Number.isFinite(n) ? Math.floor(n) : null;
}

async function saveStrategies() {
  const runtime = {
    dry_run: els.runtimeDryRun.value === "true",
    loop_interval_ms: Math.floor(numOrZero(els.runtimeInterval.value)),
    status_refresh_ms: Math.floor(numOrZero(els.runtimeStatusInterval ? els.runtimeStatusInterval.value : 0)) || 1000,
  };
  const btcMarket = marketIdValue(els.stBtcMarket);
  const ethMarket = marketIdValue(els.stEthMarket);
  const solMarket = marketIdValue(els.stSolMarket);
  const strategies = {
    BTC: {
      enabled: Boolean(els.stBtcEnabled.checked),
      market_id: btcMarket,
      grid_step: numOrZero(els.stBtcStep.value),
      levels_up: Math.floor(numOrZero(els.stBtcUp.value)),
      levels_down: Math.floor(numOrZero(els.stBtcDown.value)),
      order_size_mode: els.stBtcMode.value,
      order_size_value: numOrZero(els.stBtcSize.value),
      max_position_notional: numOrZero(els.stBtcMaxPos.value),
      reduce_position_notional: numOrZero(els.stBtcExitPos.value),
      reduce_order_size_multiplier: numOrZero(els.stBtcReduce.value),
      post_only: true,
    },
    ETH: {
      enabled: Boolean(els.stEthEnabled.checked),
      market_id: ethMarket,
      grid_step: numOrZero(els.stEthStep.value),
      levels_up: Math.floor(numOrZero(els.stEthUp.value)),
      levels_down: Math.floor(numOrZero(els.stEthDown.value)),
      order_size_mode: els.stEthMode.value,
      order_size_value: numOrZero(els.stEthSize.value),
      max_position_notional: numOrZero(els.stEthMaxPos.value),
      reduce_position_notional: numOrZero(els.stEthExitPos.value),
      reduce_order_size_multiplier: numOrZero(els.stEthReduce.value),
      post_only: true,
    },
    SOL: {
      enabled: Boolean(els.stSolEnabled.checked),
      market_id: solMarket,
      grid_step: numOrZero(els.stSolStep.value),
      levels_up: Math.floor(numOrZero(els.stSolUp.value)),
      levels_down: Math.floor(numOrZero(els.stSolDown.value)),
      order_size_mode: els.stSolMode.value,
      order_size_value: numOrZero(els.stSolSize.value),
      max_position_notional: numOrZero(els.stSolMaxPos.value),
      reduce_position_notional: numOrZero(els.stSolExitPos.value),
      reduce_order_size_multiplier: numOrZero(els.stSolReduce.value),
      post_only: true,
    },
  };

  const resp = await apiFetch("/api/config", { method: "POST", body: { runtime, strategies } });
  fillConfig(resp.config || {});
  startRuntimeLoop();
}

async function resolveAccountIndex() {
  if (currentExchange() !== "lighter") {
    throw new Error("仅 Lighter 支持自动查询 account_index");
  }
  const env = els.exEnv.value;
  const l1 = els.exL1.value.trim();
  if (!l1) throw new Error("请先填写 L1 地址");
  const resp = await apiFetch("/api/lighter/resolve_account_index", { method: "POST", body: { env, l1_address: l1 } });
  els.exAccount.value = String(resp.account_index);
}

async function fetchMarkets() {
  const env = els.exEnv.value;
  const exchange = currentExchange();
  const resp = await apiFetch(`/api/exchange/markets?env=${encodeURIComponent(env)}&exchange=${encodeURIComponent(exchange)}`);
  const items = resp.items || [];
  lastMarkets = items;
  const lines = items.map(
    (x) =>
      `${x.symbol} id=${x.market_id} sizeDec=${x.supported_size_decimals} priceDec=${x.supported_price_decimals} makerFee=${x.maker_fee} takerFee=${x.taker_fee}`
  );
  els.marketsOutput.value = lines.join("\n");
  return items;
}

async function testConnection() {
  const exchange = currentExchange();
  const resp = await apiFetch(`/api/exchange/test_connection?exchange=${encodeURIComponent(exchange)}`, { method: "POST" });
  els.testOutput.value = JSON.stringify(resp.result || {}, null, 2);
}

function pickMarketId(symbol, items) {
  const upper = symbol.toUpperCase();
  const candidates = items.filter((x) => String(x.symbol || "").toUpperCase().includes(upper));
  if (!candidates.length) return null;
  const prefer = candidates.find((x) => /USDC|USD/.test(String(x.symbol || "").toUpperCase()));
  return (prefer || candidates[0]).market_id;
}

async function autoFillMarketIds() {
  const items = lastMarkets.length ? lastMarkets : await fetchMarkets();
  const btc = pickMarketId("BTC", items);
  const eth = pickMarketId("ETH", items);
  const sol = pickMarketId("SOL", items);
  if (btc != null) els.stBtcMarket.value = String(btc);
  if (eth != null) els.stEthMarket.value = String(eth);
  if (sol != null) els.stSolMarket.value = String(sol);
}

async function refreshAccount() {
  const exchange = currentExchange();
  const resp = await apiFetch(`/api/exchange/account_snapshot?exchange=${encodeURIComponent(exchange)}`);
  els.accountOutput.value = JSON.stringify(resp.account || {}, null, 2);
}

async function refreshOrders() {
  const symbol = els.ordersSymbol.value;
  const mine = els.ordersMine.value;
  const exchange = currentExchange();
  const resp = await apiFetch(
    `/api/exchange/active_orders?symbol=${encodeURIComponent(symbol)}&mine=${encodeURIComponent(mine)}&exchange=${encodeURIComponent(exchange)}`
  );
  els.ordersOutput.value = JSON.stringify(resp || {}, null, 2);
}

function fmtNumber(value, digits = 4) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "-";
  return n.toFixed(digits);
}

function setProfitStyle(el, value) {
  if (!el) return;
  el.classList.remove("ok", "bad");
  const n = Number(value);
  if (!Number.isFinite(n)) return;
  if (n > 0) el.classList.add("ok");
  if (n < 0) el.classList.add("bad");
}

function renderRuntimeStatus(data) {
  const totals = data.totals || {};
  els.rtProfit.textContent = fmtNumber(totals.profit, 4);
  setProfitStyle(els.rtProfit, totals.profit);
  els.rtVolume.textContent = fmtNumber(totals.volume, 4);
  els.rtPosition.textContent = fmtNumber(totals.position_notional, 4);
  els.rtTrades.textContent = String(totals.trade_count || 0);
  els.rtOrders.textContent = String(totals.open_orders || 0);
  const reduceSymbols = totals.reduce_symbols || [];
  els.rtReduce.textContent = reduceSymbols.length ? reduceSymbols.join(", ") : "无";
  els.rtUpdated.textContent = data.updated_at || "-";

  const symbols = data.symbols || {};
  const rows = ["BTC", "ETH", "SOL"].map((s) => symbols[s] || { symbol: s });
  els.runtimeTbody.innerHTML = rows
    .map((r) => {
      const reduce = r.reduce_mode ? "是" : "否";
      return `<tr>
        <td class="mono">${escapeHtml(r.symbol || "")}</td>
        <td class="mono muted">${escapeHtml(r.market_id || "")}</td>
        <td class="mono">${escapeHtml(fmtNumber(r.profit, 4))}</td>
        <td class="mono">${escapeHtml(fmtNumber(r.volume, 4))}</td>
        <td class="mono">${escapeHtml(String(r.trade_count || 0))}</td>
        <td class="mono">${escapeHtml(fmtNumber(r.position_notional, 4))}</td>
        <td class="mono">${escapeHtml(String(r.open_orders || 0))}</td>
        <td class="mono">${escapeHtml(reduce)}</td>
      </tr>`;
    })
    .join("");
}

async function refreshRuntimeStatus() {
  const exchange = currentExchange();
  const resp = await apiFetch(`/api/runtime/status?exchange=${encodeURIComponent(exchange)}`);
  renderRuntimeStatus(resp || {});
}

function startRuntimeLoop() {
  if (runtimeTimer) {
    clearInterval(runtimeTimer);
    runtimeTimer = null;
  }
  const interval = Math.max(200, Math.floor(numOrZero(els.runtimeStatusInterval ? els.runtimeStatusInterval.value : 1000)));
  runtimeTimer = setInterval(async () => {
    if (authState.authenticated && authState.unlocked) {
      try {
        await refreshRuntimeStatus();
      } catch {}
    }
  }, interval);
}

function renderBots(bots) {
  const symbols = ["BTC", "ETH", "SOL"];
  const rows = symbols.map((s) => bots[s] || { symbol: s, running: false, started_at: null, last_tick_at: null, message: "" });
  els.botsTbody.innerHTML = rows
    .map((r) => {
      const st = r.running ? "运行中" : "停止";
      return `<tr>
        <td class="mono">${escapeHtml(r.symbol)}</td>
        <td class="mono muted">${escapeHtml(r.market_id || "")}</td>
        <td>${escapeHtml(st)}</td>
        <td class="mono muted">${escapeHtml(r.mid || "")}</td>
        <td class="mono muted">${escapeHtml(r.center || "")}</td>
        <td class="mono muted">${escapeHtml(`${r.desired || 0}/${r.existing || 0}`)}</td>
        <td class="mono muted">${escapeHtml(r.started_at || "")}</td>
        <td class="mono muted">${escapeHtml(r.last_tick_at || "")}</td>
        <td class="muted">${escapeHtml(r.message || "")}</td>
      </tr>`;
    })
    .join("");
}

async function refreshBots() {
  const resp = await apiFetch("/api/bots/status");
  renderBots(resp.bots || {});
}

async function startAll() {
  const dryRun = els.runtimeDryRun.value === "true";
  if (!dryRun) {
    if (!confirm("当前为实盘模式，会真实下单。确认启动吗？")) return;
  }
  await apiFetch("/api/bots/start", { method: "POST", body: { symbols: ["BTC", "ETH", "SOL"] } });
  await refreshBots();
}

async function stopAll() {
  await apiFetch("/api/bots/stop", { method: "POST", body: { symbols: ["BTC", "ETH", "SOL"] } });
  await refreshBots();
}

async function emergencyStop() {
  await apiFetch("/api/bots/emergency_stop", { method: "POST" });
  await refreshBots();
}

function escapeHtml(s) {
  return String(s).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
}

function wire() {
  if (els.exName) {
    els.exName.addEventListener("change", () => {
      lastMarkets = [];
      applyExchangeUI();
    });
  }
  els.btnSetup.addEventListener("click", async () => {
    try {
      await setup();
    } catch (e) {
      alert(e.message);
    }
  });
  els.btnLogin.addEventListener("click", async () => {
    try {
      await login();
    } catch (e) {
      alert(e.message);
    }
  });
  els.btnLogout.addEventListener("click", async () => {
    try {
      await logout();
    } catch (e) {
      alert(e.message);
    }
  });
  els.btnLock.addEventListener("click", async () => {
    try {
      await lock();
    } catch (e) {
      alert(e.message);
    }
  });
  els.btnSaveConfig.addEventListener("click", async () => {
    try {
      await saveConfig();
    } catch (e) {
      alert(e.message);
    }
  });
  els.btnSaveStrategies.addEventListener("click", async () => {
    try {
      await saveStrategies();
    } catch (e) {
      alert(e.message);
    }
  });
  els.btnAutoMarket.addEventListener("click", async () => {
    try {
      await autoFillMarketIds();
    } catch (e) {
      alert(e.message);
    }
  });
  els.btnResolveAccount.addEventListener("click", async () => {
    try {
      await resolveAccountIndex();
    } catch (e) {
      alert(e.message);
    }
  });
  els.btnFetchMarkets.addEventListener("click", async () => {
    try {
      await fetchMarkets();
    } catch (e) {
      alert(e.message);
    }
  });
  els.btnTestConn.addEventListener("click", async () => {
    try {
      await testConnection();
    } catch (e) {
      alert(e.message);
    }
  });
  els.btnStartAll.addEventListener("click", async () => {
    try {
      await startAll();
    } catch (e) {
      alert(e.message);
    }
  });
  els.btnStopAll.addEventListener("click", async () => {
    try {
      await stopAll();
    } catch (e) {
      alert(e.message);
    }
  });
  els.btnEmergency.addEventListener("click", async () => {
    if (!confirm("确定执行紧急停止吗？")) return;
    try {
      await emergencyStop();
    } catch (e) {
      alert(e.message);
    }
  });
  els.btnRefreshAccount.addEventListener("click", async () => {
    try {
      await refreshAccount();
    } catch (e) {
      alert(e.message);
    }
  });
  els.btnRefreshOrders.addEventListener("click", async () => {
    try {
      await refreshOrders();
    } catch (e) {
      alert(e.message);
    }
  });
}

async function loop() {
  await refreshAuth();
  setInterval(async () => {
    if (authState.authenticated && authState.unlocked) {
      try {
        await refreshBots();
      } catch {}
    }
  }, 2000);
}

wire();
loop();
