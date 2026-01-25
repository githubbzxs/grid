无限网格交易程序（Lighter）- 方案草案
================================

已确认需求摘要
------------

- 交易所：Lighter
- 市场：永续合约
- 策略：双向无限网格（中心跟随最新价）
- 标的：BTC、ETH、SOL 同时运行
- 网格参数：固定价差、上下层数、每单数量等都在 WebUI 中配置
- 下单偏好：严格 Post-Only（Maker）
- 运行环境：Windows 与 Linux
- 启动方式：一键脚本
- 部署诉求：希望可公网访问，但不做账号系统；采用单管理员密码保护

官方资料调研结论
--------------

Lighter 提供 API 与 SDK，交易请求需要签名与 nonce 管理，官方也提供 Python/Go SDK。

- 文档入口（检索时间：2026-01-25）
  - https://docs.lighter.xyz/perpetual-futures/api
  - https://apidocs.lighter.xyz/docs/get-started-for-programmers-1
  - https://apidocs.lighter.xyz/docs/api-keys
  - https://apidocs.lighter.xyz/docs/websocket-reference
  - https://apidocs.lighter.xyz/docs/rate-limits
  - https://github.com/elliottech/lighter-python
  - https://github.com/elliottech/lighter-go

首版范围（MVP）
--------------

必须做到（全部在 WebUI）

- 管理员密码：初始化、登录、修改
- Lighter 配置
  - mainnet/testnet 切换
  - L1 地址
  - account_index 自动查询与手填
  - api_key_index、API 私钥录入
  - 可选 ETH 私钥（仅在需要执行特定提现/转账类型时才用）
  - 连接测试与基础信息拉取（余额、仓位、订单）
- 策略配置（按标的独立保存）
  - 固定价差
  - 上下层数
  - 每单数量：固定名义金额 或 固定币数量
  - Post-Only 开关（首版默认且建议固定开启）
  - 最大未成交订单数、最大持仓名义等最小风控项
- 运行控制
  - BTC/ETH/SOL 各自启动/停止
  - 紧急停止（停止策略并撤单）
  - 一键撤单（按标的/全局）
- 监控展示
  - 运行状态、余额、仓位、未成交订单、最近成交、错误提示
  - 实时日志（SSE 或轮询）

暂不做（二期）

- 回测/模拟盘
- 多用户权限系统
- 高级风控与参数自适应
- 自动多 API key 分流提速

技术方案（KISS）
--------------

- 语言：Python 3.11+
- 后端：FastAPI
  - 提供 REST API
  - 托管静态 WebUI
  - asyncio 后台任务管理多个标的 bot
- 存储：SQLite
  - 配置、运行状态快照、事件与日志索引
- Lighter 适配：优先使用官方 Python SDK 负责签名、nonce 管理与交易提交

安全设计（单人公网可用）
--------------------

- 必须有管理员密码
- 敏感字段（API 私钥、ETH 私钥）支持两种模式
  - 记住：使用管理员密码派生密钥加密后落盘
  - 不记住：不落盘，重启后需重新输入
- 默认仅监听 127.0.0.1；若选择 0.0.0.0 则在 UI 强提示风险

无限网格策略定义（实现口径）
------------------------

“无限”指价格可以持续单边移动，但系统始终只维持有限数量的挂单。

- 对每个标的，维持上方 N 层卖单与下方 N 层买单
- 以最新中间价为中心，每次价格跨过一格才触发滚动更新（避免每个 tick 都撤挂）
- 任一订单成交后，按固定价差补充相邻一格的反向订单，保持层数恒定
- 所有订单使用 client_order_index 做可追踪与幂等控制
- 增加节流与重试，遵守 rate limit，网络断开可自动恢复

项目结构（拟定）
--------------

- apps/server
  - app/main.py：FastAPI 入口
  - app/api：配置、运行控制、状态、日志
  - app/exchanges/lighter：Lighter 适配层
  - app/strategies/grid：网格引擎
  - app/storage：SQLite 与加密
  - app/services：bot 管理器与后台任务
  - app/web：静态 WebUI
- scripts
  - start.bat：Windows 一键启动
  - start.sh：Linux 一键启动（用 bash 执行）

里程碑与交付
----------

1) 工程骨架 + WebUI 可打开、可保存配置、可看日志
2) Lighter 打通：账户信息查询、下单/撤单链路跑通
3) 网格引擎上线：BTC/ETH/SOL 同时运行可用
4) 稳定性与风控：限流、断线重连、异常恢复、紧急停止
5) 一键启动脚本完善 + 验收示例配置

验收标准（首版）
--------------

- Windows：双击 scripts/start.bat 后可访问 WebUI，完成配置并启动网格
- Linux：执行 bash scripts/start.sh 后同样可用
- 全程无需命令行配置：API 私钥、参数、启动停止都在 WebUI 完成

风险提示
------

网格策略不保证盈利；永续合约存在爆仓与极端行情风险。首版会提供最小风控与紧急停止能力，但仍需你自行承担交易风险。
