Grid（无限网格交易程序）
====================

当前状态
-------

已具备可跑通的 MVP：

- WebUI：管理员密码、交易所配置（Lighter/Paradex）、策略配置、启动/停止、紧急停止（撤网格单）、日志
- Lighter：自动查询 account_index、拉取 perp 市场列表、测试连接、查看账户快照与当前挂单
- Paradex：拉取 perp 市场列表、测试连接、查看账户快照与当前挂单
- 网格：滚动网格（维持上/下固定层数），支持“模拟/实盘”切换

依赖说明
-------

- 需要 Python 3.11+、可访问 GitHub 与 PyPI
- `apps/server/requirements.txt` 会通过 `git+https://...` 拉取官方 `lighter-python` 与 `paradex-py`

快速开始
-------

Windows

- 双击 `scripts/start.bat`
- 浏览器打开 `http://127.0.0.1:9999/`

Linux

- 执行 `bash scripts/start.sh`
- 浏览器打开 `http://127.0.0.1:9999/`

Linux 一键启动命令
--------------

- `bash scripts/start.sh`

公网部署（可选）
------------

脚本支持环境变量：

- Windows：先设置 `GRID_HOST=0.0.0.0`、`GRID_PORT=9999` 再运行脚本
- Linux：`GRID_HOST=0.0.0.0 GRID_PORT=9999 bash scripts/start.sh`

提示：脚本默认监听 `0.0.0.0:9999`，公网需放通防火墙并使用服务器公网 IP 访问；必须设置强管理员密码，建议配合反向代理与 HTTPS。

WebUI 使用步骤（建议先模拟）
------------------------

1) 首次打开，设置管理员密码并登录解锁
2) 交易所配置
   - 选择交易所与 mainnet/testnet
   - Lighter：填写 L1 地址、account_index、api_key_index、API 私钥（可选 ETH 私钥），可点“自动查询 account_index”
   - Paradex：填写 L2 地址与 L2 私钥（推荐），或填写 L1 地址与 L1 私钥
3) 拉取市场列表，找到你要跑的 BTC/ETH/SOL perp 的 `market_id`（Lighter 为数字，Paradex 为市场符号）
4) 策略配置
   - 填写每个标的的 `market_id`、固定价差、上下层数、每单模式与数值
   - 运行模式先选“模拟（不下单）”，保存策略
5) 启动 BTC/ETH/SOL
   - 模拟模式会输出 create/cancel 日志但不会真实下单
6) 确认无误后切到“实盘（会真实下单）”，保存策略，然后停止再启动

计划
---

详见 `PLAN.md`

一键部署（Linux）
------------

- 从零部署并启动（拉取仓库 + 启动）：
  - `bash -c "$(curl -fsSL https://raw.githubusercontent.com/githubbzxs/grid/main/scripts/bootstrap.sh)"`
