# Grid（无限网格交易程序）

面向 **Lighter / Paradex / GRVT** 的网格交易服务，提供 WebUI 配置、运行控制与统计展示。

## 1. 功能概览

- **WebUI**：管理员登录、交易所配置、策略配置、启动/停止、紧急撤单、运行统计、日志与历史。
- **行情与下单**：
  - Lighter / Paradex：使用各自官方 SDK。
  - GRVT：**行情走 WS，订单走 SDK**（符合官方推荐方式）。
- **网格策略**：支持多币对、动态增删、模拟/实盘切换、模拟成交统计。

## 2. 交易所支持

- **Lighter**：
  - account_index 自动查询（依赖 L1 地址）。
  - market_id 为数字。
- **Paradex**：
  - 仅保留 L2 地址与 L2 私钥（推荐）。
  - market_id 为市场字符串。
- **GRVT**：
  - 需要 Trading Account ID + API Key + 私钥。
  - market_id 为 instrument 字符串。
  - 价格/数量精度、最小下单量以市场列表为准；默认 GTT（GOOD_TILL_TIME），post_only 生效。

## 3. 环境要求

- Python 3.11+
- 可访问 GitHub 与 PyPI
- `apps/server/requirements.txt` 中包含官方 SDK（Lighter / Paradex / GRVT）

## 4. 启动方式

### Windows

1. 双击 `scripts/start.bat`
2. 访问：`http://127.0.0.1:9999/`

### Linux

1. 执行 `bash scripts/start.sh`
2. 访问：`http://127.0.0.1:9999/`

## 5. WebUI 使用流程（建议先模拟）

1. 首次打开设置管理员密码并登录解锁。
2. 交易所配置：
   - **Lighter**：填写 L1 地址、api_key_index、API 私钥，account_index 可自动查询。
   - **Paradex**：填写 L2 地址 + L2 私钥。
   - **GRVT**：填写 Trading Account ID + API Key + 私钥。
3. 获取市场列表，`market_id` 会自动填充并随交易所切换自动更新。
4. 策略配置：填写间隔、上下层、每单模式与数量、最大仓位/退出仓位等。
5. 运行模式建议先选择「模拟（不下单）」，需要模拟成交可开启「模拟成交」。
6. 确认无误后切换到实盘并保存策略，再启动。

## 6. 策略参数与交易所限制说明

- **market_id 类型**：Lighter 为数字；Paradex / GRVT 为 instrument 字符串。
- **精度与最小下单量**：以“市场列表”中返回的 `sizeDec / priceDec / minBase / tick` 为准。
- **GRVT 订单限制**：默认 GTT（GOOD_TILL_TIME），post_only 有效，client_order_id 必须唯一。
- **网格类型**：动态网格与 AS 网格在 WebUI 中分表配置，后端以 `grid_mode` 区分（`dynamic` / `as`）。
- **动态参数**：`grid_step` 固定价差。
- **AS 参数（可选）**：`as_min_step` AS 最小价差（<=0 时自动使用最小价格刻度）。
- **AS 参数（可选）**：`as_gamma` 风险厌恶系数，默认 0.1。
- **AS 参数（可选）**：`as_k` 深度系数，默认 1.5。
- **AS 参数（可选）**：`as_tau_seconds` 时间尺度（秒），默认 30。
- **AS 参数（可选）**：`as_vol_points` 波动率采样点数，默认 60（最少 5）。
- **AS 参数（可选）**：`as_max_step_multiplier` 最大价差倍数，默认 10。
- **AS 参数（可选）**：`as_max_drawdown` 最大回撤阈值（>0 启用，触发后紧急停止）。
- **AS 价差规则**：AS 网格实际步长取 `max(as_min_step, AS 半价差)`，并受 `as_max_step_multiplier` 上限约束（旧配置中的 `grid_step` 仅作为回退）。
- **AS 挂单规则**：AS 网格仅挂两单（1 个 bid + 1 个 ask）。
- **AS 风控**：AS 网格不使用减仓模式，使用最大回撤保护。

## 7. 更新与部署（Linux）

- 更新并重启（默认目录 `grid`）：
  - `bash -c "$(curl -fsSL https://raw.githubusercontent.com/githubbzxs/grid/main/scripts/update.sh)"`
- 指定仓库目录：
  - `GRID_DIR=/opt/grid bash -c "$(curl -fsSL https://raw.githubusercontent.com/githubbzxs/grid/main/scripts/update.sh)"`

## 8. 一键部署（可选）

- 从零部署并启动：
  - `bash -c "$(curl -fsSL https://raw.githubusercontent.com/githubbzxs/grid/main/scripts/bootstrap.sh)"`
- 说明：Debian/Ubuntu 会自动安装 python-venv、pip、rustc、cargo（需要 root 或 sudo）。

## 9. 计划

详见 `PLAN.md`。
