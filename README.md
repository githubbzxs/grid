# Grid（无限网格交易程序）

面向 Lighter / Paradex 的网格交易程序，提供 WebUI 配置与运行控制。

## 1. 功能概览

- **WebUI**：管理员登录、交易所配置、策略配置、启动/停止、紧急停止（撤网格单）、日志
- **Lighter**：自动查询 account_index、拉取 perp 市场列表、测试连接、账户快照/挂单
- **Paradex**：拉取 perp 市场列表、测试连接、账户快照/挂单
- **网格策略**：滚动网格（维持上下固定层数）、模拟/实盘切换、模拟成交统计

## 2. 环境要求

- Python 3.11+
- 可访问 GitHub 与 PyPI
- `apps/server/requirements.txt` 通过 `git+https://...` 拉取官方 `lighter-python` 与 `paradex-py`

## 3. 快速开始

### Windows

1. 双击 `scripts/start.bat`
2. 打开浏览器访问 `http://127.0.0.1:9999/`

### Linux

1. 执行 `bash scripts/start.sh`
2. 打开浏览器访问 `http://127.0.0.1:9999/`

## 4. 更新（Linux）

- 更新并重启（默认目录 `grid`）：
  - `bash -c "$(curl -fsSL https://raw.githubusercontent.com/githubbzxs/grid/main/scripts/update.sh)"`
- 指定仓库目录：
  - `GRID_DIR=/opt/grid bash -c "$(curl -fsSL https://raw.githubusercontent.com/githubbzxs/grid/main/scripts/update.sh)"`

## 5. 部署（可选）

### 公网部署

- Windows：先设置 `GRID_HOST=0.0.0.0`、`GRID_PORT=9999` 再运行脚本
- Linux：`GRID_HOST=0.0.0.0 GRID_PORT=9999 bash scripts/start.sh`

提示：脚本默认监听 `0.0.0.0:9999`，公网需放通防火墙并使用服务器公网 IP 访问；必须设置强管理员密码，建议配合反向代理与 HTTPS。

### Linux 一键部署

- 从零部署并启动（拉取仓库 + 启动）：
  - `bash -c "$(curl -fsSL https://raw.githubusercontent.com/githubbzxs/grid/main/scripts/bootstrap.sh)"`
- 说明：在 Debian/Ubuntu 上会自动安装 pythonX-venv、python3-pip、rustc、cargo（需要 root 或 sudo）

## 6. WebUI 使用流程（建议先模拟）

1. 首次打开，设置管理员密码并登录解锁
2. 交易所配置  
   - 选择交易所与 mainnet/testnet  
   - Lighter：填写 L1 地址、account_index、api_key_index、API 私钥（可选 ETH 私钥），可点“自动查询 account_index”
   - Paradex：填写 L2 地址与 L2 私钥（推荐），或填写 L1 地址与 L1 私钥
3. 拉取市场列表，选择目标 perp，`market_id` 会自动填充
4. 策略配置（可新增/删除币对）  
   - 填写固定价差、上下层数、每单模式与数值  
   - 运行模式先选“模拟（不下单）”，如需模拟成交可开启“模拟成交”
5. 启动全部  
   - 模拟成交会在价格触达挂单线时视为成交，并统计仓位/成交
6. 确认无误后切到“实盘（会真实下单）”，保存策略，然后停止再启动

## 7. 计划

详见 `PLAN.md`

## 8. 自动提交（可选）

- 自动提交脚本：
  - `powershell -ExecutionPolicy Bypass -File scripts/auto-commit.ps1 -m "chore: auto commit"`
