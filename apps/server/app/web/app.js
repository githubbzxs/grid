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

  btnStartAll: document.getElementById("btn-start-all"),
  btnStopAll: document.getElementById("btn-stop-all"),
  btnEmergency: document.getElementById("btn-emergency"),
  botsTbody: document.getElementById("bots-tbody"),

  logs: document.getElementById("logs"),
};

let authState = { setup_required: true, authenticated: false, unlocked: false };
let logSource = null;

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
}

async function loadConfig() {
  const resp = await apiFetch("/api/config");
  fillConfig(resp.config || {});
}

async function saveConfig() {
  const exchange = {
    env: els.exEnv.value,
    l1_address: els.exL1.value.trim(),
    account_index: els.exAccount.value.trim() ? Number(els.exAccount.value.trim()) : null,
    api_key_index: els.exKeyIndex.value.trim() ? Number(els.exKeyIndex.value.trim()) : null,
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
  const lines = items.map(
    (x) =>
      `${x.symbol} id=${x.market_id} sizeDec=${x.supported_size_decimals} priceDec=${x.supported_price_decimals} makerFee=${x.maker_fee} takerFee=${x.taker_fee}`
  );
  els.marketsOutput.value = lines.join("\n");
}

async function testConnection() {
  const resp = await apiFetch("/api/lighter/test_connection", { method: "POST" });
  els.testOutput.value = JSON.stringify(resp.result || {}, null, 2);
}

function renderBots(bots) {
  const symbols = ["BTC", "ETH", "SOL"];
  const rows = symbols.map((s) => bots[s] || { symbol: s, running: false, started_at: null, last_tick_at: null, message: "" });
  els.botsTbody.innerHTML = rows
    .map((r) => {
      const st = r.running ? "运行中" : "停止";
      return `<tr>
        <td class="mono">${escapeHtml(r.symbol)}</td>
        <td>${escapeHtml(st)}</td>
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
