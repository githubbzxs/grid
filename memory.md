# 🧠 Project Memory (项目记忆库)

> 注意：此文件由 Agent 自动维护。每次会话结束或重要变更后必须更新。
> 目的：作为项目的长期记忆，确保上下文在不同会话和 Sub-Agents 之间无损传递。

## 1. 📍 Current Status (当前状态)

**当前阶段**: [ 📝 规划中 ]
**当前任务**:
- [ ] 等待远程服务器连接信息，用于启动服务。

**下一步计划**:
- [ ] 获取 SSH 连接信息与项目路径后执行远程启动。

## 2. 🛠 Tech Stack & Config (技术栈与配置)

| 类别 | 选型/版本 | 备注 |
| --- | --- | --- |
| **Language** | Python 3.11+ | FastAPI 运行环境 |
| **Framework** | FastAPI + Uvicorn | API 与 WebUI 服务 |
| **Crypto** | cryptography | 密钥加解密 |
| **SDK** | lighter-python / paradex-py / grvt-pysdk | 交易所 SDK |
| **Storage** | JSON 文件 | `data/config.json`、`data/runtime_history.jsonl` |

**关键环境配置**:
- Python Version: >= 3.11
- 默认端口: 9999（本地 127.0.0.1）
- 环境变量: `GRID_HOST`、`GRID_PORT`、`GRID_DATA_DIR`
- 运行参数: `runtime.simulate_fill`（仅模拟模式生效）

## 3. 🏗 Architecture & Patterns (架构与模式)

**目录结构规范**:
- `apps/server/app`: FastAPI 后端与业务逻辑
- `apps/server/app/web`: 静态 WebUI
- `apps/server/app/exchanges`: 交易所适配（Lighter / Paradex / GRVT）
- `apps/server/app/strategies`: 网格策略实现
- `scripts`: 启动与更新脚本

**核心设计模式**:
- 配置由 `app/core/config_store` 统一读写。
- 交易所适配与策略实现分层组织。
- AS 网格通过运行时计算中心价与价差，兼容现有网格下单逻辑。

## 4. 📝 Key Decisions Log (关键决策记录)

- **[2026-02-01]**: GRVT 行情使用 WS、下单使用 SDK，策略区增加交易所限制提示。
- **[2026-02-01]**: 网格补单策略改为优先补中心附近档位。
- **[2026-02-01]**: 新增 AS 网格模式，基于 Avellaneda-Stoikov 计算中心价与价差。
- **[2026-02-01]**: Lighter 的 OrderApi.trades limit 固定为 100。
- **[2026-02-01]**: WebUI 增加 AS 参数输入与说明。

## 5. ⚠️ Known Issues & Constraints (已知问题与约束)

- 暂无新增已知问题。

## 6. 🎨 User Preferences (用户偏好)

- 所有自然语言回复使用中文。
- 注释与文档必须使用中文，统一 UTF-8 编码。
- 遵循 KISS 与 SOLID。
- 发现缺陷优先修复，再扩展新功能。
- 禁止 MVP 或占位实现，要求完整具体实现。
- 改动后自动提交并推送远端仓库。

---

**Last Updated**: 2026-02-01 20:10
