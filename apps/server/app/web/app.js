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

  exEnv: document.getElementById("ex-env"),
  exL1: document.getElementById("ex-l1"),
  exAccount: document.getElementById("ex-account"),
  btnResolveAccount: document.getElementById("btn-resolve-account"),
  exKeyIndex: document.getElementById("ex-key-index"),
  exApiKey: document.getElementById("ex-api-key"),
  exEthKey: document.getElementById("ex-eth-key"),
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

  stEthEnabled: document.getElementById("st-eth-enabled"),
  stEthMarket: document.getElementById("st-eth-market"),
  stEthStep: document.getElementById("st-eth-step"),
  stEthUp: document.getElementById("st-eth-up"),
  stEthDown: document.getElementById("st-eth-down"),
  stEthMode: document.getElementById("st-eth-mode"),
  stEthSize: document.getElementById("st-eth-size"),

  stSolEnabled: document.getElementById("st-sol-enabled"),
  stSolMarket: document.getElementById("st-sol-market"),
  stSolStep: document.getElementById("st-sol-step"),
  stSolUp: document.getElementById("st-sol-up"),
  stSolDown: document.getElementById("st-sol-down"),
  stSolMode: document.getElementById("st-sol-mode"),
  stSolSize: document.getElementById("st-sol-size"),

  runtimeDryRun: document.getElementById("runtime-dry-run"),
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

  logs: document.getElementById("logs"),
};

let authState = { setup_required: true, authenticated: false, unlocked: false };
let logSource = null;
let lastMarkets = [];

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
      return;
    }
    if (!authState.authenticated) {
      setPill(false, "未登录");
      showApp(false);
      return;
    }
    if (!authState.unlocked) {
      setPill(false, "已登录但未解锁");
      showApp(false);
      return;
    }
    setPill(true, "已解锁");
    showApp(true);
    startLogStream();
    await loadConfig();
    await refreshBots();
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
  await refreshAuth();
}

async function lock() {
  await apiFetch("/api/auth/lock", { method: "POST" });
  if (logSource) {
    logSource.close();
    logSource = null;
  }
  await refreshAuth();
}

function fillConfig(cfg) {
  const ex = cfg.exchange || {};
  els.exEnv.value = ex.env || "mainnet";
  els.exL1.value = ex.l1_address || "";
  els.exAccount.value = ex.account_index == null ? "" : String(ex.account_index);
  els.exKeyIndex.value = ex.api_key_index == null ? "" : String(ex.api_key_index);
  els.exRemember.value = String(Boolean(ex.remember_secrets));
  els.exApiKeyHint.textContent = ex.api_private_key_set ? "已保存（加密）" : "未保存";
  els.exEthKeyHint.textContent = ex.eth_private_key_set ? "已保存（加密）" : "未保存";

  const rt = cfg.runtime || {};
  els.runtimeDryRun.value = String(Boolean(rt.dry_run));

  const st = cfg.strategies || {};
  fillStrategyRow("BTC", st.BTC || {}, "btc");
  fillStrategyRow("ETH", st.ETH || {}, "eth");
  fillStrategyRow("SOL", st.SOL || {}, "sol");
}

function fillStrategyRow(symbol, s, key) {
  const enabled = Boolean(s.enabled);
  const market = s.market_id == null ? "" : String(s.market_id);
  const step = s.grid_step == null ? "" : String(s.grid_step);
  const up = s.levels_up == null ? "" : String(s.levels_up);
  const down = s.levels_down == null ? "" : String(s.levels_down);
  const mode = s.order_size_mode || "notional";
  const size = s.order_size_value == null ? "" : String(s.order_size_value);

  if (key === "btc") {
    els.stBtcEnabled.checked = enabled;
    els.stBtcMarket.value = market;
    els.stBtcStep.value = step;
    els.stBtcUp.value = up;
    els.stBtcDown.value = down;
    els.stBtcMode.value = mode;
    els.stBtcSize.value = size;
  } else if (key === "eth") {
    els.stEthEnabled.checked = enabled;
    els.stEthMarket.value = market;
    els.stEthStep.value = step;
    els.stEthUp.value = up;
    els.stEthDown.value = down;
    els.stEthMode.value = mode;
    els.stEthSize.value = size;
  } else if (key === "sol") {
    els.stSolEnabled.checked = enabled;
    els.stSolMarket.value = market;
    els.stSolStep.value = step;
    els.stSolUp.value = up;
    els.stSolDown.value = down;
    els.stSolMode.value = mode;
    els.stSolSize.value = size;
  }
}

async function loadConfig() {
  const resp = await apiFetch("/api/config");
  fillConfig(resp.config || {});
}

async function saveConfig() {
  const exchange = {
    env: els.exEnv.value,
    l1_address: els.exL1.value.trim(),
    account_index: els.exAccount.value.trim() ? Math.floor(Number(els.exAccount.value.trim())) : null,
    api_key_index: els.exKeyIndex.value.trim() ? Math.floor(Number(els.exKeyIndex.value.trim())) : null,
    remember_secrets: els.exRemember.value === "true",
  };
  const api_private_key = els.exApiKey.value.trim();
  const eth_private_key = els.exEthKey.value.trim();
  if (api_private_key) exchange.api_private_key = api_private_key;
  if (eth_private_key) exchange.eth_private_key = eth_private_key;

  const resp = await apiFetch("/api/config", { method: "POST", body: { exchange } });
  fillConfig(resp.config || {});
  els.exApiKey.value = "";
  els.exEthKey.value = "";
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

async function saveStrategies() {
  const runtime = { dry_run: els.runtimeDryRun.value === "true" };
  const btcMarket = numOrNull(els.stBtcMarket.value);
  const ethMarket = numOrNull(els.stEthMarket.value);
  const solMarket = numOrNull(els.stSolMarket.value);
  const strategies = {
    BTC: {
      enabled: Boolean(els.stBtcEnabled.checked),
      market_id: btcMarket == null ? null : Math.floor(btcMarket),
      grid_step: numOrZero(els.stBtcStep.value),
      levels_up: Math.floor(numOrZero(els.stBtcUp.value)),
      levels_down: Math.floor(numOrZero(els.stBtcDown.value)),
      order_size_mode: els.stBtcMode.value,
      order_size_value: numOrZero(els.stBtcSize.value),
      post_only: true,
    },
    ETH: {
      enabled: Boolean(els.stEthEnabled.checked),
      market_id: ethMarket == null ? null : Math.floor(ethMarket),
      grid_step: numOrZero(els.stEthStep.value),
      levels_up: Math.floor(numOrZero(els.stEthUp.value)),
      levels_down: Math.floor(numOrZero(els.stEthDown.value)),
      order_size_mode: els.stEthMode.value,
      order_size_value: numOrZero(els.stEthSize.value),
      post_only: true,
    },
    SOL: {
      enabled: Boolean(els.stSolEnabled.checked),
      market_id: solMarket == null ? null : Math.floor(solMarket),
      grid_step: numOrZero(els.stSolStep.value),
      levels_up: Math.floor(numOrZero(els.stSolUp.value)),
      levels_down: Math.floor(numOrZero(els.stSolDown.value)),
      order_size_mode: els.stSolMode.value,
      order_size_value: numOrZero(els.stSolSize.value),
      post_only: true,
    },
  };

  const resp = await apiFetch("/api/config", { method: "POST", body: { runtime, strategies } });
  fillConfig(resp.config || {});
}

async function resolveAccountIndex() {
  const env = els.exEnv.value;
  const l1 = els.exL1.value.trim();
  if (!l1) throw new Error("请先填写 L1 地址");
  const resp = await apiFetch("/api/lighter/resolve_account_index", { method: "POST", body: { env, l1_address: l1 } });
  els.exAccount.value = String(resp.account_index);
}

async function fetchMarkets() {
  const env = els.exEnv.value;
  const resp = await apiFetch(`/api/lighter/markets?env=${encodeURIComponent(env)}`);
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
  const resp = await apiFetch("/api/lighter/test_connection", { method: "POST" });
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
  const resp = await apiFetch("/api/lighter/account_snapshot");
  els.accountOutput.value = JSON.stringify(resp.account || {}, null, 2);
}

async function refreshOrders() {
  const symbol = els.ordersSymbol.value;
  const mine = els.ordersMine.value;
  const resp = await apiFetch(`/api/lighter/active_orders?symbol=${encodeURIComponent(symbol)}&mine=${encodeURIComponent(mine)}`);
  els.ordersOutput.value = JSON.stringify(resp || {}, null, 2);
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
