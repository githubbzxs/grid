const els = {
  dotAuth: document.getElementById('dot-auth'),
  pillText: document.getElementById('pill-text'),
  authStatus: document.getElementById('auth-status'),
  password: document.getElementById('password'),
  btnLogin: document.getElementById('btn-login')
}

let authState = { setup_required: true, authenticated: false, unlocked: false }

async function apiFetch(path, { method = 'GET', body = null } = {}) {
  const resp = await fetch(path, {
    method,
    credentials: 'include',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined
  })
  const text = await resp.text()
  let json = null
  try {
    json = text ? JSON.parse(text) : null
  } catch {
    json = null
  }
  if (!resp.ok) {
    const msg = (json && (json.detail || json.message)) || text || `HTTP ${resp.status}`
    throw new Error(msg)
  }
  return json
}

function setPill(ok, text) {
  els.dotAuth.classList.remove('ok', 'bad')
  els.dotAuth.classList.add(ok ? 'ok' : 'bad')
  els.pillText.textContent = text
}

function setAuthInfo(text) {
  if (els.authStatus) {
    els.authStatus.textContent = text
  }
}

function updateButtonLabel() {
  if (!els.btnLogin) return
  if (authState.setup_required) {
    els.btnLogin.textContent = '初始化并登录'
  } else {
    els.btnLogin.textContent = '登录'
  }
}

async function refreshAuth() {
  try {
    authState = await apiFetch('/api/auth/status')
    setAuthInfo(`setup_required=${authState.setup_required} authenticated=${authState.authenticated} unlocked=${authState.unlocked}`)
    if (authState.authenticated && authState.unlocked) {
      setPill(true, '已解锁')
      window.location.href = '/'
      return
    }
    if (authState.setup_required) {
      setPill(false, '需要初始化')
    } else if (!authState.authenticated) {
      setPill(false, '未登录')
    } else {
      setPill(false, '已登录但未解锁')
    }
    updateButtonLabel()
  } catch (e) {
    setPill(false, `错误：${e.message}`)
  }
}

async function setup(password) {
  await apiFetch('/api/auth/setup', { method: 'POST', body: { password } })
}

async function login(password) {
  await apiFetch('/api/auth/login', { method: 'POST', body: { password } })
}

async function handleLogin() {
  const password = (els.password && els.password.value) || ''
  if (!password || password.length < 8) {
    alert('请输入至少 8 位的密码')
    return
  }
  if (authState.setup_required) {
    await setup(password)
  } else {
    await login(password)
  }
  if (els.password) {
    els.password.value = ''
  }
  await refreshAuth()
}

function wire() {
  if (els.btnLogin) {
    els.btnLogin.addEventListener('click', async () => {
      try {
        await handleLogin()
      } catch (e) {
        alert(e.message)
      }
    })
  }
  if (els.password) {
    els.password.addEventListener('keydown', async (event) => {
      if (event.key !== 'Enter') return
      event.preventDefault()
      try {
        await handleLogin()
      } catch (e) {
        alert(e.message)
      }
    })
  }
}

wire()
refreshAuth()
