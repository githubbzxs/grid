const els = {
  btnLogout: document.getElementById("btn-logout"),
  btnLock: document.getElementById("btn-lock"),
  appArea: document.getElementById("app-area"),
  navSelect: document.getElementById("nav-select"),

  exName: document.getElementById("ex-name"),
  exEnv: document.getElementById("ex-env"),
  lighterFields: document.getElementById("lighter-fields"),
  grvtFields: document.getElementById("grvt-fields"),
  paradexFields: document.getElementById("paradex-fields"),
  exL1: document.getElementById("ex-l1"),
  exAccount: document.getElementById("ex-account"),
  exKeyIndex: document.getElementById("ex-key-index"),
  exApiKey: document.getElementById("ex-api-key"),
  exEthKey: document.getElementById("ex-eth-key"),
  grvtAccountId: document.getElementById("grvt-account-id"),
  grvtApiKey: document.getElementById("grvt-api-key"),
  grvtPrivateKey: document.getElementById("grvt-private-key"),
  pxL1: document.getElementById("px-l1"),
  pxL1Key: document.getElementById("px-l1-key"),
  pxL1KeyHint: document.getElementById("px-l1-key-hint"),
  pxL2: document.getElementById("px-l2"),
  pxL2Key: document.getElementById("px-l2-key"),
  pxL2KeyHint: document.getElementById("px-l2-key-hint"),
  exRemember: document.getElementById("ex-remember"),
  exApiKeyHint: document.getElementById("ex-api-key-hint"),
  exEthKeyHint: document.getElementById("ex-eth-key-hint"),
  grvtApiKeyHint: document.getElementById("grvt-api-key-hint"),
  grvtPrivateKeyHint: document.getElementById("grvt-private-key-hint"),
  btnSaveConfig: document.getElementById("btn-save-config"),
  btnTestConn: document.getElementById("btn-test-conn"),
  testOutput: document.getElementById("test-output"),

  strategyDynamicTable: document.getElementById("strategy-dynamic-table"),
  strategyDynamicTbody: document.getElementById("strategy-dynamic-tbody"),
  strategyAsTable: document.getElementById("strategy-as-table"),
  strategyAsTbody: document.getElementById("strategy-as-tbody"),
  btnAddDynamic: document.getElementById("btn-add-dynamic"),
  btnAddAs: document.getElementById("btn-add-as"),
  btnSaveStrategies: document.getElementById("btn-save-strategies"),

  runtimeDryRun: document.getElementById("runtime-dry-run"),
  runtimeSimulateFill: document.getElementById("runtime-simulate-fill"),
  runtimeInterval: document.getElementById("runtime-interval"),
  runtimeStatusInterval: document.getElementById("runtime-status-interval"),
  runtimeAutoRestart: document.getElementById("runtime-auto-restart"),
  runtimeRestartDelay: document.getElementById("runtime-restart-delay"),
  runtimeRestartMax: document.getElementById("runtime-restart-max"),
  runtimeRestartWindow: document.getElementById("runtime-restart-window"),
  runtimeStopMinutes: document.getElementById("runtime-stop-minutes"),
  runtimeStopVolume: document.getElementById("runtime-stop-volume"),

  btnStartAll: document.getElementById("btn-start-all"),
  btnStopAll: document.getElementById("btn-stop-all"),
  btnEmergency: document.getElementById("btn-emergency"),
  botsTbody: document.getElementById("bots-tbody"),

  btnRefreshAccount: document.getElementById("btn-refresh-account"),
  btnCopyAccount: document.getElementById("btn-copy-account"),
  btnClearAccount: document.getElementById("btn-clear-account"),
  accountOutput: document.getElementById("account-output"),
  ordersSymbol: document.getElementById("orders-symbol"),
  ordersMine: document.getElementById("orders-mine"),
  btnRefreshOrders: document.getElementById("btn-refresh-orders"),
  btnCopyOrders: document.getElementById("btn-copy-orders"),
  btnClearOrders: document.getElementById("btn-clear-orders"),
  ordersOutput: document.getElementById("orders-output"),

  exchangeLimitHint: document.getElementById("exchange-limit-hint"),

  rtProfit: document.getElementById("rt-profit"),
  rtVolume: document.getElementById("rt-volume"),
  rtPosition: document.getElementById("rt-position"),
  rtTrades: document.getElementById("rt-trades"),
  rtOrders: document.getElementById("rt-orders"),
  rtReduce: document.getElementById("rt-reduce"),
  rtUpdated: document.getElementById("rt-updated"),
  runtimeTbody: document.getElementById("runtime-tbody"),

  historyLimit: document.getElementById("history-limit"),
  btnRefreshHistory: document.getElementById("btn-refresh-history"),
  historyTbody: document.getElementById("history-tbody"),

  logs: document.getElementById("logs"),
  btnCopyLogs: document.getElementById("btn-copy-logs"),
  btnClearLogs: document.getElementById("btn-clear-logs"),
  btnToggleLogScroll: document.getElementById("btn-toggle-log-scroll"),
};

let authState = { setup_required: true, authenticated: false, unlocked: false };
let logSource = null;
let currentStrategies = [];
let lastBots = {};
let runtimeTimer = null;
let accountResolveTimer = null;
let accountResolving = false;
let logAutoScroll = true;
const navLinks = Array.from(document.querySelectorAll(".nav-links a"));
const pageSections = Array.from(document.querySelectorAll(".page-section"));

function currentExchange() {
  const name = (els.exName && els.exName.value) || "lighter";
  const lowered = String(name).toLowerCase();
  if (lowered === "paradex") return "paradex";
  if (lowered === "grvt") return "grvt";
  return "lighter";
}

function applyExchangeUI() {
  const exchange = currentExchange();
  const isLighter = exchange === "lighter";
  const isParadex = exchange === "paradex";
  const isGrvt = exchange === "grvt";
  if (els.lighterFields) els.lighterFields.hidden = !isLighter;
  if (els.paradexFields) els.paradexFields.hidden = !isParadex;
  if (els.grvtFields) els.grvtFields.hidden = !isGrvt;
  updateExchangeLimitHint();
}

function scheduleResolveAccountIndex() {
  if (currentExchange() !== "lighter") return;
  if (!els.exL1 || !els.exAccount) return;
  const l1 = els.exL1.value.trim();
  if (!l1) return;
  if (String(els.exAccount.value || "").trim()) return;
  if (accountResolving) return;
  if (accountResolveTimer) clearTimeout(accountResolveTimer);
  accountResolveTimer = setTimeout(async () => {
    accountResolving = true;
    try {
      await resolveAccountIndex();
    } catch (e) {
      console.warn(e);
    } finally {
      accountResolving = false;
    }
  }, 500);
}

function updateExchangeLimitHint() {
  if (!els.exchangeLimitHint) return;
  const exchange = currentExchange();
  if (exchange === "grvt") {
    els.exchangeLimitHint.textContent =
      "GRVT 限制：价格/数量精度与最小下单量以市场规则为准，默认 GTT（GOOD_TILL_TIME），post_only 生效，client_order_id 需唯一。";
    return;
  }
  if (exchange === "paradex") {
    els.exchangeLimitHint.textContent =
      "Paradex 限制：价格/数量精度与最小下单量以市场规则为准，建议使用 L2 subkey。";
    return;
  }
  els.exchangeLimitHint.textContent =
    "Lighter 限制：价格/数量精度与最小下单量以市场规则为准，需匹配 account_index 与 api_key_index。";
}

function syncSimulateFillState() {
  if (!els.runtimeSimulateFill || !els.runtimeDryRun) return;
  const dryRun = els.runtimeDryRun.value === "true";
  els.runtimeSimulateFill.disabled = !dryRun;
  if (!dryRun) {
    els.runtimeSimulateFill.value = "false";
  }
}

function normalizeSymbol(value) {
  return String(value || "").trim().toUpperCase();
}

function strategyDefaults(mode = "dynamic") {
  const base = {
    symbol: "",
    exchange: currentExchange(),
    enabled: true,
    market_id: null,
    order_size_mode: "notional",
    order_size_value: 5,
    post_only: true,
    max_open_orders: 50,
  };
  if (mode === "as") {
    return {
      ...base,
      grid_mode: "as",
      as_gamma: 0.1,
      as_k: 1.5,
      as_tau_seconds: 30,
      as_vol_points: 60,
      as_step_multiplier: 1,
      as_max_drawdown: 0,
    };
  }
  return {
    ...base,
    grid_mode: "dynamic",
    grid_step: 0,
    levels_up: 10,
    levels_down: 10,
    max_position_notional: 20,
    reduce_position_notional: 0,
    reduce_order_size_multiplier: 1,
  };
}

function normalizeStrategies(raw) {
  const list = [];
  const seen = new Set();
  if (Array.isArray(raw)) {
    raw.forEach((item) => {
      if (!item || typeof item !== "object") return;
      const symbol = normalizeSymbol(item.symbol || item.name || item.ticker);
      if (!symbol || seen.has(symbol)) return;
      const mode = String(item.grid_mode || "").toLowerCase() === "as" ? "as" : "dynamic";
      const merged = { ...strategyDefaults(mode), ...item, symbol, grid_mode: mode };
      if (mode === "as") {
        delete merged.as_min_step;
        delete merged.as_max_step_multiplier;
        delete merged.grid_step;
        delete merged.levels_up;
        delete merged.levels_down;
        delete merged.max_position_notional;
        delete merged.reduce_position_notional;
        delete merged.reduce_order_size_multiplier;
      }
      list.push(merged);
      seen.add(symbol);
    });
  } else if (raw && typeof raw === "object") {
    Object.entries(raw).forEach(([key, value]) => {
      const symbol = normalizeSymbol(key);
      if (!symbol || seen.has(symbol)) return;
      const base = value && typeof value === "object" ? value : {};
      const mode = String(base.grid_mode || "").toLowerCase() === "as" ? "as" : "dynamic";
      const merged = { ...strategyDefaults(mode), ...base, symbol, grid_mode: mode };
      if (mode === "as") {
        delete merged.as_min_step;
        delete merged.as_max_step_multiplier;
        delete merged.grid_step;
        delete merged.levels_up;
        delete merged.levels_down;
        delete merged.max_position_notional;
        delete merged.reduce_position_notional;
        delete merged.reduce_order_size_multiplier;
      }
      list.push(merged);
      seen.add(symbol);
    });
  }
  return list;
}

function valueText(value) {
  if (value === null || value === undefined) return "";
  return String(value);
}

function dynamicStrategyRowTemplate(strategy) {
  const symbol = escapeHtml(strategy.symbol || "");
  const exchange = String(strategy.exchange || currentExchange()).toLowerCase();
  const enabled = strategy.enabled ? "checked" : "";
  const step = escapeHtml(valueText(strategy.grid_step));
  const up = escapeHtml(valueText(strategy.levels_up));
  const down = escapeHtml(valueText(strategy.levels_down));
  const size = escapeHtml(valueText(strategy.order_size_value));
  const maxpos = escapeHtml(valueText(strategy.max_position_notional));
  const exitpos = escapeHtml(valueText(strategy.reduce_position_notional));
  const reduce = escapeHtml(valueText(strategy.reduce_order_size_multiplier));
  const mode = strategy.order_size_mode === "base" ? "base" : "notional";
  return `<tr>
    <td data-label="标的"><input class="st-symbol mono" placeholder="例如 BTC" value="${symbol}" /></td>
    <td data-label="交易所">
      <select class="st-exchange">
        <option value="lighter" ${exchange === "lighter" ? "selected" : ""}>Lighter</option>
        <option value="grvt" ${exchange === "grvt" ? "selected" : ""}>GRVT</option>
        <option value="paradex" ${exchange === "paradex" ? "selected" : ""}>Paradex</option>
      </select>
    </td>
    <td data-label="启用"><input class="st-enabled" type="checkbox" ${enabled} /></td>
    <td data-label="交易所限制"><div class="st-limit hint">后台自动匹配市场</div></td>
    <td data-label="价差"><input class="st-step" placeholder="例如 5" value="${step}" /></td>
    <td data-label="上层"><input class="st-up" placeholder="10" value="${up}" /></td>
    <td data-label="下层"><input class="st-down" placeholder="10" value="${down}" /></td>
    <td data-label="每单模式">
      <select class="st-mode">
        <option value="notional" ${mode === "notional" ? "selected" : ""}>固定名义金额</option>
        <option value="base" ${mode === "base" ? "selected" : ""}>固定币数量</option>
      </select>
    </td>
    <td data-label="每单数量"><input class="st-size" placeholder="例如 5" value="${size}" /></td>
    <td data-label="触发仓位"><input class="st-maxpos" placeholder="例如 100" value="${maxpos}" /></td>
    <td data-label="退出仓位"><input class="st-exitpos" placeholder="例如 80" value="${exitpos}" /></td>
    <td data-label="减仓倍数"><input class="st-reduce" placeholder="例如 2" value="${reduce}" /></td>
    <td data-label="操作"><button class="danger btn-remove-row" type="button">删除</button></td>
  </tr>`;
}

function asStrategyRowTemplate(strategy) {
  const symbol = escapeHtml(strategy.symbol || "");
  const exchange = String(strategy.exchange || currentExchange()).toLowerCase();
  const enabled = strategy.enabled ? "checked" : "";
  const asGamma = escapeHtml(valueText(strategy.as_gamma));
  const asK = escapeHtml(valueText(strategy.as_k));
  const asTau = escapeHtml(valueText(strategy.as_tau_seconds));
  const asVol = escapeHtml(valueText(strategy.as_vol_points));
  const asStepMult = escapeHtml(valueText(strategy.as_step_multiplier));
  const asMaxDrawdown = escapeHtml(valueText(strategy.as_max_drawdown));
  const size = escapeHtml(valueText(strategy.order_size_value));
  const mode = strategy.order_size_mode === "base" ? "base" : "notional";
  return `<tr>
    <td data-label="标的"><input class="st-symbol mono" placeholder="例如 BTC" value="${symbol}" /></td>
    <td data-label="交易所">
      <select class="st-exchange">
        <option value="lighter" ${exchange === "lighter" ? "selected" : ""}>Lighter</option>
        <option value="grvt" ${exchange === "grvt" ? "selected" : ""}>GRVT</option>
        <option value="paradex" ${exchange === "paradex" ? "selected" : ""}>Paradex</option>
      </select>
    </td>
    <td data-label="启用"><input class="st-enabled" type="checkbox" ${enabled} /></td>
    <td data-label="交易所限制"><div class="st-limit hint">后台自动匹配市场</div></td>
    <td data-label="ASγ"><input class="st-as-gamma" placeholder="默认 0.1" value="${asGamma}" /></td>
    <td data-label="AS-k"><input class="st-as-k" placeholder="默认 1.5" value="${asK}" /></td>
    <td data-label="AS-τ(s)"><input class="st-as-tau" placeholder="默认 30" value="${asTau}" /></td>
    <td data-label="AS-σ采样"><input class="st-as-vol" placeholder="默认 60" value="${asVol}" /></td>
    <td data-label="AS 价差乘数"><input class="st-as-step-mult" placeholder="默认 1" value="${asStepMult}" /></td>
    <td data-label="AS 最大回撤"><input class="st-as-max-dd" placeholder="例如 50" value="${asMaxDrawdown}" /></td>
    <td data-label="每单模式">
      <select class="st-mode">
        <option value="notional" ${mode === "notional" ? "selected" : ""}>固定名义金额</option>
        <option value="base" ${mode === "base" ? "selected" : ""}>固定币数量</option>
      </select>
    </td>
    <td data-label="每单数量"><input class="st-size" placeholder="例如 5" value="${size}" /></td>
    <td data-label="操作"><button class="danger btn-remove-row" type="button">删除</button></td>
  </tr>`;
}

function addStrategyRow(strategy, mode = "dynamic") {
  const tbody = mode === "as" ? els.strategyAsTbody : els.strategyDynamicTbody;
  if (!tbody) return;
  const data = strategy ? { ...strategyDefaults(mode), ...strategy } : strategyDefaults(mode);
  const template = mode === "as" ? asStrategyRowTemplate(data) : dynamicStrategyRowTemplate(data);
  tbody.insertAdjacentHTML("beforeend", template);
}

function renderStrategyTable(tbody, list, mode) {
  if (!tbody) return;
  const rows = list && list.length ? list.map((item) => (mode === "as" ? asStrategyRowTemplate(item) : dynamicStrategyRowTemplate(item))).join("") : "";
  tbody.innerHTML = rows;
}

function renderStrategies(list) {
  const dynamicList = [];
  const asList = [];
  (list || []).forEach((item) => {
    if (String(item.grid_mode || "").toLowerCase() === "as") {
      asList.push(item);
    } else {
      dynamicList.push(item);
    }
  });
  renderStrategyTable(els.strategyDynamicTbody, dynamicList, "dynamic");
  renderStrategyTable(els.strategyAsTbody, asList, "as");
}

function getStrategyRowsByMode(mode) {
  const tbody = mode === "as" ? els.strategyAsTbody : els.strategyDynamicTbody;
  if (!tbody) return [];
  return Array.from(tbody.querySelectorAll("tr"));
}

function getAllStrategyRows() {
  return [...getStrategyRowsByMode("dynamic"), ...getStrategyRowsByMode("as")];
}

function rowHasValues(row) {
  const inputs = Array.from(row.querySelectorAll("input, select"));
  return inputs.some((input) => {
    if (input.classList.contains("st-symbol") || input.classList.contains("st-exchange")) return false;
    if (input.type === "checkbox") return input.checked;
    return String(input.value || "").trim() !== "";
  });
}

function collectStrategiesFromTable() {
  const strategies = {};
  const seen = new Set();
  let hasEmptySymbol = false;

  function applyRow(row, mode) {
    const symbolInput = row.querySelector(".st-symbol");
    const symbol = normalizeSymbol(symbolInput ? symbolInput.value : "");
    const exchangeInput = row.querySelector(".st-exchange");
    const exchange = exchangeInput ? exchangeInput.value : currentExchange();
    if (!symbol) {
      if (rowHasValues(row)) {
        hasEmptySymbol = true;
      }
      return;
    }
    if (seen.has(symbol)) {
      throw new Error(`币对重复：${symbol}`);
    }
    seen.add(symbol);
    const existing = currentStrategies.find((item) => item.symbol === symbol) || {};
    const prevExchange = String(existing.exchange || currentExchange()).toLowerCase();
    const nextExchange = String(exchange || currentExchange()).toLowerCase();
    let marketId = existing.market_id;
    if (typeof marketId === "string" && !marketId.trim()) {
      marketId = null;
    }
    if (prevExchange !== nextExchange) {
      marketId = null;
    }
    const base = {
      ...strategyDefaults(mode),
      ...existing,
      symbol,
      exchange: exchange || currentExchange(),
      enabled: Boolean(row.querySelector(".st-enabled")?.checked),
      market_id: marketId,
      order_size_mode: row.querySelector(".st-mode")?.value || "notional",
      order_size_value: numOrZero(row.querySelector(".st-size")?.value),
    };

    if (mode === "as") {
      strategies[symbol] = {
        symbol,
        exchange: base.exchange,
        enabled: base.enabled,
        market_id: base.market_id,
        grid_mode: "as",
        order_size_mode: base.order_size_mode,
        order_size_value: base.order_size_value,
        post_only: Boolean(base.post_only),
        max_open_orders: Math.floor(numOrZero(base.max_open_orders)),
        as_gamma: numOrZero(row.querySelector(".st-as-gamma")?.value),
        as_k: numOrZero(row.querySelector(".st-as-k")?.value),
        as_tau_seconds: numOrZero(row.querySelector(".st-as-tau")?.value),
        as_vol_points: Math.floor(numOrZero(row.querySelector(".st-as-vol")?.value)),
        as_step_multiplier: numOrZero(row.querySelector(".st-as-step-mult")?.value),
        as_max_drawdown: numOrZero(row.querySelector(".st-as-max-dd")?.value),
      };
      return;
    }

    strategies[symbol] = {
      ...base,
      grid_mode: "dynamic",
      levels_up: Math.floor(numOrZero(row.querySelector(".st-up")?.value)),
      levels_down: Math.floor(numOrZero(row.querySelector(".st-down")?.value)),
      max_position_notional: numOrZero(row.querySelector(".st-maxpos")?.value),
      reduce_position_notional: numOrZero(row.querySelector(".st-exitpos")?.value),
      reduce_order_size_multiplier: numOrZero(row.querySelector(".st-reduce")?.value),
      grid_step: numOrZero(row.querySelector(".st-step")?.value),
    };
  }

  getStrategyRowsByMode("dynamic").forEach((row) => applyRow(row, "dynamic"));
  getStrategyRowsByMode("as").forEach((row) => applyRow(row, "as"));

  if (hasEmptySymbol) {
    throw new Error("存在未填写的币对，请补充或删除。");
  }
  return strategies;
}

function getCurrentStrategySymbols() {
  const exchange = currentExchange();
  return currentStrategies
    .filter((item) => String(item.exchange || exchange).toLowerCase() === exchange)
    .map((item) => item.symbol)
    .filter(Boolean);
}

function mergeSymbols(...lists) {
  const result = [];
  const seen = new Set();
  lists.flat().forEach((item) => {
    const symbol = normalizeSymbol(item);
    if (!symbol || seen.has(symbol)) return;
    seen.add(symbol);
    result.push(symbol);
  });
  return result;
}

function updateOrdersSymbolOptions() {
  if (!els.ordersSymbol) return;
  const symbols = mergeSymbols(getCurrentStrategySymbols(), Object.keys(lastBots || {}));
  const current = els.ordersSymbol.value;
  if (!symbols.length) {
    els.ordersSymbol.innerHTML = '<option value="">暂无币对</option>';
    return;
  }
  els.ordersSymbol.innerHTML = symbols.map((s) => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join("");
  if (symbols.includes(current)) {
    els.ordersSymbol.value = current;
  } else {
    els.ordersSymbol.value = symbols[0];
  }
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

function setAuthCardInfo(text) {
  if (els.authStatus) {
    els.authStatus.textContent = text;
  }
}

function setSecretStatus(el, saved) {
  if (!el) return;
  el.textContent = saved ? "已保存（加密）" : "未保存";
  el.classList.toggle("saved", saved);
  el.classList.toggle("empty", !saved);
}

function showApp(show) {
  els.appArea.hidden = !show;
}

function redirectToLogin() {
  if (window.location.pathname !== "/login") {
    window.location.href = "/login";
  }
}

function appendLog(line) {
  const maxLines = 400;
  const current = els.logs.textContent.split("\n").filter((x) => x.length);
  current.push(line);
  const sliced = current.slice(-maxLines);
  els.logs.textContent = sliced.join("\n") + "\n";
  if (logAutoScroll) {
    els.logs.scrollTop = els.logs.scrollHeight;
  }
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

function getSectionIdFromHash() {
  const raw = String(window.location.hash || "").trim();
  if (!raw || raw === "#") return "";
  return raw.startsWith("#") ? raw.slice(1) : raw;
}

function activateSection(id) {
  if (!pageSections.length) return;
  const target = pageSections.find((section) => section.id === id) || pageSections[0];
  pageSections.forEach((section) => {
    section.classList.toggle("active", section === target);
  });
  navLinks.forEach((link) => {
    const linkTarget = link.dataset.target || "";
    link.classList.toggle("active", linkTarget === target.id);
  });
  if (els.navSelect && target) {
    els.navSelect.value = target.id;
  }
  if (target && window.location.hash !== `#${target.id}`) {
    history.replaceState(null, "", `#${target.id}`);
  }
  window.scrollTo(0, 0);
}

function initNavigation() {
  if (!pageSections.length || !navLinks.length) return;
  navLinks.forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      const target = link.dataset.target || "";
      activateSection(target);
    });
  });
  if (els.navSelect) {
    els.navSelect.addEventListener("change", () => {
      activateSection(els.navSelect.value);
    });
  }
  activateSection(getSectionIdFromHash());
  window.addEventListener("hashchange", () => {
    activateSection(getSectionIdFromHash());
  });
}

async function refreshAuth() {
  try {
    authState = await apiFetch("/api/auth/status");
    const s = `setup_required=${authState.setup_required} authenticated=${authState.authenticated} unlocked=${authState.unlocked}`;
    setAuthCardInfo(s);
    if (authState.setup_required) {
      showApp(false);
      if (runtimeTimer) {
        clearInterval(runtimeTimer);
        runtimeTimer = null;
      }
      redirectToLogin();
      return;
    }
    if (!authState.authenticated) {
      showApp(false);
      if (runtimeTimer) {
        clearInterval(runtimeTimer);
        runtimeTimer = null;
      }
      redirectToLogin();
      return;
    }
    if (!authState.unlocked) {
      showApp(false);
      if (runtimeTimer) {
        clearInterval(runtimeTimer);
        runtimeTimer = null;
      }
      redirectToLogin();
      return;
    }
    showApp(true);
    startLogStream();
    await loadConfig();
    await refreshBots();
    await refreshRuntimeStatus();
    await refreshHistory();
    startRuntimeLoop();
  } catch (e) {
    showApp(false);
  }
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
  if (els.exRemember) {
    els.exRemember.value = String(Boolean(ex.remember_secrets));
  }
  setSecretStatus(els.exApiKeyHint, Boolean(ex.api_private_key_set));
  setSecretStatus(els.exEthKeyHint, Boolean(ex.eth_private_key_set));
  if (els.grvtAccountId) {
    els.grvtAccountId.value = ex.grvt_account_id || "";
  }
  setSecretStatus(els.grvtApiKeyHint, Boolean(ex.grvt_api_key_set));
  setSecretStatus(els.grvtPrivateKeyHint, Boolean(ex.grvt_private_key_set));
  if (els.pxL1) {
    els.pxL1.value = ex.paradex_l1_address || "";
  }
  if (els.pxL2) {
    els.pxL2.value = ex.paradex_l2_address || "";
  }
  setSecretStatus(els.pxL1KeyHint, Boolean(ex.paradex_l1_private_key_set));
  setSecretStatus(els.pxL2KeyHint, Boolean(ex.paradex_l2_private_key_set));

  const rt = cfg.runtime || {};
  els.runtimeDryRun.value = String(Boolean(rt.dry_run));
  if (els.runtimeSimulateFill) {
    const simFill = rt.simulate_fill == null ? false : Boolean(rt.simulate_fill);
    els.runtimeSimulateFill.value = String(simFill);
  }
  syncSimulateFillState();
  els.runtimeInterval.value = rt.loop_interval_ms == null ? "100" : String(rt.loop_interval_ms);
  if (els.runtimeStatusInterval) {
    els.runtimeStatusInterval.value = rt.status_refresh_ms == null ? "1000" : String(rt.status_refresh_ms);
  }
  if (els.runtimeAutoRestart) {
    const autoRestart = rt.auto_restart == null ? true : Boolean(rt.auto_restart);
    els.runtimeAutoRestart.value = String(autoRestart);
  }
  if (els.runtimeRestartDelay) {
    els.runtimeRestartDelay.value = rt.restart_delay_ms == null ? "1000" : String(rt.restart_delay_ms);
  }
  if (els.runtimeRestartMax) {
    els.runtimeRestartMax.value = rt.restart_max == null ? "5" : String(rt.restart_max);
  }
  if (els.runtimeRestartWindow) {
    els.runtimeRestartWindow.value = rt.restart_window_ms == null ? "60000" : String(rt.restart_window_ms);
  }
  if (els.runtimeStopMinutes) {
    els.runtimeStopMinutes.value = rt.stop_after_minutes == null ? "0" : String(rt.stop_after_minutes);
  }
  if (els.runtimeStopVolume) {
    els.runtimeStopVolume.value = rt.stop_after_volume == null ? "0" : String(rt.stop_after_volume);
  }
  if (els.historyLimit && !els.historyLimit.value) {
    els.historyLimit.value = "200";
  }

  const st = normalizeStrategies(cfg.strategies || {});
  currentStrategies = st;
  renderStrategies(st);
  updateOrdersSymbolOptions();

  applyExchangeUI();
  scheduleResolveAccountIndex();
}

async function loadConfig() {
  const resp = await apiFetch("/api/config");
  fillConfig(resp.config || {});
}

async function saveConfig() {
  const exchange = {
    name: currentExchange(),
    env: els.exEnv.value,
    remember_secrets: els.exRemember ? els.exRemember.value === "true" : true,
  };
  if (exchange.name === "paradex") {
    exchange.paradex_l1_address = "";
    exchange.paradex_l2_address = els.pxL2 ? els.pxL2.value.trim() : "";
    const l2_key = els.pxL2Key ? els.pxL2Key.value.trim() : "";
    if (l2_key) exchange.paradex_l2_private_key = l2_key;
  } else if (exchange.name === "grvt") {
    exchange.grvt_account_id = els.grvtAccountId ? els.grvtAccountId.value.trim() : "";
    const api_key = els.grvtApiKey ? els.grvtApiKey.value.trim() : "";
    const private_key = els.grvtPrivateKey ? els.grvtPrivateKey.value.trim() : "";
    if (api_key) exchange.grvt_api_key = api_key;
    if (private_key) exchange.grvt_private_key = private_key;
  } else {
    exchange.l1_address = els.exL1.value.trim();
    exchange.account_index = els.exAccount.value.trim() ? Math.floor(Number(els.exAccount.value.trim())) : null;
    exchange.api_key_index = els.exKeyIndex.value.trim() ? Math.floor(Number(els.exKeyIndex.value.trim())) : null;
    const api_private_key = els.exApiKey.value.trim();
    const eth_private_key = els.exEthKey ? els.exEthKey.value.trim() : "";
    if (api_private_key) exchange.api_private_key = api_private_key;
    if (eth_private_key) exchange.eth_private_key = eth_private_key;
    if (!exchange.account_index && exchange.l1_address) {
      try {
        await resolveAccountIndex();
      } catch (e) {
        console.warn(e);
      }
      exchange.account_index = els.exAccount.value.trim() ? Math.floor(Number(els.exAccount.value.trim())) : null;
    }
  }

  const resp = await apiFetch("/api/config", { method: "POST", body: { exchange } });
  fillConfig(resp.config || {});
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
  const dryRun = els.runtimeDryRun.value === "true";
  const simulateFill = els.runtimeSimulateFill ? els.runtimeSimulateFill.value === "true" : false;
  const runtime = {
    dry_run: dryRun,
    simulate_fill: dryRun && simulateFill,
    loop_interval_ms: Math.floor(numOrZero(els.runtimeInterval.value)),
    status_refresh_ms: Math.floor(numOrZero(els.runtimeStatusInterval ? els.runtimeStatusInterval.value : 0)) || 1000,
    auto_restart: els.runtimeAutoRestart ? els.runtimeAutoRestart.value === "true" : true,
    restart_delay_ms: Math.floor(numOrZero(els.runtimeRestartDelay ? els.runtimeRestartDelay.value : 0)),
    restart_max: Math.floor(numOrZero(els.runtimeRestartMax ? els.runtimeRestartMax.value : 0)),
    restart_window_ms: Math.floor(numOrZero(els.runtimeRestartWindow ? els.runtimeRestartWindow.value : 0)),
    stop_after_minutes: numOrZero(els.runtimeStopMinutes ? els.runtimeStopMinutes.value : 0),
    stop_after_volume: numOrZero(els.runtimeStopVolume ? els.runtimeStopVolume.value : 0),
  };
  const strategies = collectStrategiesFromTable();

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

async function testConnection() {
  const exchange = currentExchange();
  const resp = await apiFetch(`/api/exchange/test_connection?exchange=${encodeURIComponent(exchange)}`, { method: "POST" });
  els.testOutput.value = JSON.stringify(resp.result || {}, null, 2);
}

async function refreshAccount() {
  const exchange = currentExchange();
  const resp = await apiFetch(`/api/exchange/account_snapshot?exchange=${encodeURIComponent(exchange)}`);
  els.accountOutput.textContent = JSON.stringify(resp.account || {}, null, 2);
}

async function refreshOrders() {
  const symbol = els.ordersSymbol.value;
  if (!symbol) {
    const placeholder = els.ordersOutput.dataset.placeholder || "请先配置币对。";
    els.ordersOutput.textContent = placeholder;
    return;
  }
  const mine = els.ordersMine.value;
  const exchange = currentExchange();
  const resp = await apiFetch(
    `/api/exchange/active_orders?symbol=${encodeURIComponent(symbol)}&mine=${encodeURIComponent(mine)}&exchange=${encodeURIComponent(exchange)}`
  );
  els.ordersOutput.textContent = JSON.stringify(resp || {}, null, 2);
}

function copyText(text) {
  if (!text) return;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).catch(() => {});
    return;
  }
  const temp = document.createElement("textarea");
  temp.value = text;
  temp.style.position = "fixed";
  temp.style.left = "-9999px";
  document.body.appendChild(temp);
  temp.select();
  try {
    document.execCommand("copy");
  } catch {}
  temp.remove();
}

function clearOutput(el) {
  if (!el) return;
  const placeholder = el.dataset && el.dataset.placeholder ? el.dataset.placeholder : "";
  el.textContent = placeholder;
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
  const rowSymbols = mergeSymbols(getCurrentStrategySymbols(), Object.keys(symbols));
  const rows = rowSymbols.map((s) => symbols[s] || { symbol: s });
  els.runtimeTbody.innerHTML = rows
    .map((r) => {
      const reduce = r.reduce_mode ? "是" : "否";
      return `<tr>
        <td class="mono">${escapeHtml(r.symbol || "")}</td>
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

function renderHistory(items) {
  const rows = (items || []).map((r) => {
    const totals = r.totals || {};
    const symbols = Object.keys(r.symbols || {}).join(", ");
    const reason = r.stop_reason ? `${r.reason || ""}(${r.stop_reason})` : r.reason || "";
    return `<tr>
      <td class="mono muted">${escapeHtml(r.created_at || "")}</td>
      <td class="mono">${escapeHtml(r.exchange || "")}</td>
      <td>${escapeHtml(reason)}</td>
      <td class="mono">${escapeHtml(symbols)}</td>
      <td class="mono">${escapeHtml(fmtNumber(totals.profit, 4))}</td>
      <td class="mono">${escapeHtml(fmtNumber(totals.volume, 4))}</td>
      <td class="mono">${escapeHtml(String(totals.trade_count || 0))}</td>
      <td class="mono">${escapeHtml(fmtNumber(totals.position_notional, 4))}</td>
      <td class="mono">${escapeHtml(String(totals.open_orders || 0))}</td>
      <td class="mono">${escapeHtml((totals.reduce_symbols || []).join(", ") || "无")}</td>
    </tr>`;
  });
  els.historyTbody.innerHTML = rows.join("");
}

async function refreshHistory() {
  const limit = els.historyLimit ? Math.floor(numOrZero(els.historyLimit.value)) : 200;
  const resp = await apiFetch(`/api/runtime/history?limit=${encodeURIComponent(limit)}`);
  renderHistory(resp.items || []);
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
  const symbols = mergeSymbols(getCurrentStrategySymbols(), Object.keys(bots || {}));
  const rows = symbols.map((s) => bots[s] || { symbol: s, running: false, started_at: null, last_tick_at: null, message: "" });
  els.botsTbody.innerHTML = rows
    .map((r) => {
      const st = r.running ? "运行中" : "停止";
      return `<tr>
        <td class="mono">${escapeHtml(r.symbol)}</td>
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
  lastBots = resp.bots || {};
  renderBots(lastBots);
  updateOrdersSymbolOptions();
}

async function startAll() {
  const dryRun = els.runtimeDryRun.value === "true";
  if (!dryRun) {
    if (!confirm("当前为实盘模式，会真实下单。确认启动吗？")) return;
  }
  const symbols = getCurrentStrategySymbols();
  if (!symbols.length) {
    alert("请先配置策略币对。");
    return;
  }
  await apiFetch("/api/bots/start", { method: "POST", body: { symbols } });
  await refreshBots();
}

async function stopAll() {
  const symbols = getCurrentStrategySymbols();
  if (!symbols.length) {
    alert("请先配置策略币对。");
    return;
  }
  await apiFetch("/api/bots/stop", { method: "POST", body: { symbols } });
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
  initNavigation();
  if (els.exName) {
    els.exName.addEventListener("change", async () => {
      applyExchangeUI();
      scheduleResolveAccountIndex();
    });
  }
  if (els.exL1) {
    els.exL1.addEventListener("blur", () => {
      scheduleResolveAccountIndex();
    });
    els.exL1.addEventListener("change", () => {
      scheduleResolveAccountIndex();
    });
  }
  if (els.runtimeDryRun) {
    els.runtimeDryRun.addEventListener("change", () => {
      syncSimulateFillState();
    });
  }
  if (els.btnAddDynamic) {
    els.btnAddDynamic.addEventListener("click", () => {
      addStrategyRow({ symbol: "" }, "dynamic");
    });
  }
  if (els.btnAddAs) {
    els.btnAddAs.addEventListener("click", () => {
      addStrategyRow({ symbol: "" }, "as");
    });
  }

  function bindStrategyTable(tbody, mode) {
    if (!tbody) return;
    tbody.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      if (target.classList.contains("btn-remove-row")) {
        const row = target.closest("tr");
        if (row) {
          row.remove();
        }
      }
    });
    tbody.addEventListener("change", async (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      if (target.classList.contains("st-symbol")) {
        const row = target.closest("tr");
        if (!row) return;
        const symbol = normalizeSymbol(target.value);
        target.value = symbol;
        if (!symbol) return;
        return;
      }
    });
  }

  bindStrategyTable(els.strategyDynamicTbody, "dynamic");
  bindStrategyTable(els.strategyAsTbody, "as");

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
  if (els.btnCopyAccount) {
    els.btnCopyAccount.addEventListener("click", () => {
      copyText(els.accountOutput.textContent || "");
    });
  }
  if (els.btnClearAccount) {
    els.btnClearAccount.addEventListener("click", () => {
      clearOutput(els.accountOutput);
    });
  }
  if (els.btnCopyOrders) {
    els.btnCopyOrders.addEventListener("click", () => {
      copyText(els.ordersOutput.textContent || "");
    });
  }
  if (els.btnClearOrders) {
    els.btnClearOrders.addEventListener("click", () => {
      clearOutput(els.ordersOutput);
    });
  }
  if (els.btnCopyLogs) {
    els.btnCopyLogs.addEventListener("click", () => {
      copyText(els.logs.textContent || "");
    });
  }
  if (els.btnClearLogs) {
    els.btnClearLogs.addEventListener("click", () => {
      clearOutput(els.logs);
    });
  }
  if (els.btnToggleLogScroll) {
    els.btnToggleLogScroll.addEventListener("click", () => {
      logAutoScroll = !logAutoScroll;
      els.btnToggleLogScroll.textContent = `自动滚动：${logAutoScroll ? "开" : "关"}`;
    });
  }
  if (els.btnRefreshHistory) {
    els.btnRefreshHistory.addEventListener("click", async () => {
      try {
        await refreshHistory();
      } catch (e) {
        alert(e.message);
      }
    });
  }
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





