# 🧠 Project Memory (项目记忆库)

> 注意：此文件由 Agent 自动维护。每次会话结束或重要变更后必须更新。
> 目的：作为项目的长期记忆，确保上下文在不同会话和 Sub-Agents 之间无损传递。

## 1. 📍 Current Status (当前状态)

**当前阶段**: [ 🐛 调试中 ]
**当前任务**:
- [ ] 验证 Lighter 运行统计（成交量/笔数）是否正常（已加入 auth token + retry）
- [ ] 验证 GRVT 真实连接与下单（已安装 grvt-pysdk，使用 --no-deps）

**下一步计划**:
- [ ] 在 WebUI 启动 Lighter 策略后检查 /api/runtime/status
- [ ] 在 GRVT 环境执行 test_connection / 启动策略验证

## 2. 🛠 Tech Stack & Config (技术栈与配置)

| 类别 | 选型/版本 | 备注 |
| --- | --- | --- |
| **Language** | Python 3.11+ | FastAPI 服务端 |
| **Framework** | FastAPI + Uvicorn | API + WebUI |
| **Crypto** | cryptography | 密钥加解密 |
| **SDK** | lighter-python / paradex-py / grvt-pysdk | 交易所 SDK |
| **Storage** | JSON 文件 | data/config.json, data/runtime_history.jsonl |

**关键环境配置**:
- Python Version: >= 3.11
- 默认端口: 9999（监听 0.0.0.0）
- 环境变量: GRID_HOST, GRID_PORT, GRID_DATA_DIR
- 运行参数: runtime.simulate_fill（模拟成交开关）
- 依赖拆分: apps/server/requirements.txt（Lighter/Paradex）+ apps/server/requirements-grvt.txt（GRVT，--no-deps 安装）

## 3. 🏗 Architecture & Patterns (架构与模式)

**目录结构规范**:
- apps/server/app: FastAPI 主服务与业务逻辑
- apps/server/app/web: 静态 WebUI
- apps/server/app/exchanges: 交易所适配（Lighter / Paradex / GRVT）
- scripts: 部署与运维脚本

**部署结构**:
- 远程部署服务器: 154.201.95.70:22（root）
- 服务端仓库路径: /root/grid
- Python 虚拟环境: /root/grid/.venv
- systemd 服务: /etc/systemd/system/grid.service
- 启动命令: /root/grid/.venv/bin/python -m uvicorn app.main:app --app-dir apps/server --host 0.0.0.0 --port 9999

**核心设计模式**:
- 使用 app/core/config_store 统一读写配置
- 交易所适配器分层组织
- 动态网格与 AS 网格在 UI 分表配置，后端通过 grid_mode 区分
- AS 价差按 Avellaneda-Stoikov 公式计算，步长最小为价格刻度
- AS 网格仅挂两单（1 bid + 1 ask）
- AS 风控仅最大回撤保护（as_max_drawdown），不使用减仓模式

## 4. 📝 Key Decisions Log (关键决策记录)

- **[2026-02-05]**: 为 Lighter 增加逐请求延迟诊断日志，并在补单阶段输出汇总日志（定位限速/重试/串行造成的慢）。
- **[2026-02-05]**: 取消密钥输入的状态胶囊提示，保存后保留密码输入的圆点显示（不再清空密钥输入框）。
- **[2026-02-05]**: 本机通过 scripts/start.bat 启动服务，WebUI 可在 http://127.0.0.1:9999/login 访问（未登录状态）。
- **[2026-02-05]**: 同步远程仓库到最新 `origin/main`（拉取包含 GRVT 适配新增与 WebUI 更新的提交）。
- **[2026-02-04]**: Lighter 成交统计新增 auth token 与重试机制，修复统计为 0 的问题。
- **[2026-02-04]**: 拆分 GRVT 依赖到 requirements-grvt.txt，并以 --no-deps 安装，规避 websockets 版本冲突。
- **[2026-02-03]**: 默认远程部署服务器切换为 154.201.95.70。

## 5. ⚠️ Known Issues & Constraints (已知问题与约束)

- 旧服务器 45.207.211.121 Web/SSH 不可用（HTTP 无响应、SSH 握手超时）。
- GRVT SDK 依赖通过 --no-deps 安装，若运行时出现 websockets 兼容性问题需进一步验证。

## 6. 🎨 User Preferences (用户偏好)

- 所有自然语言回复使用中文。
- 注释和文档必须使用中文，统一 UTF-8。
- 遵循 KISS / SOLID。
- 发现缺陷优先修复再扩展。
- 禁止 MVP 或占位实现。
- 有改动需提交并推送远端。

---


## 7. ????

- ???????????????????? /api/logs/recent ? /api/logs/stream ?? lighter.latency ? grid.reconcile ???
- ???????????????

**Last Updated**: 2026-02-05 21:30
