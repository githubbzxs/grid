# 🧠 Project Memory (项目记忆库)

> 注意：此文件由 Agent 自动维护。每次会话结束或重要变更后必须更新。
> 目的：作为项目的长期记忆，确保上下文在不同会话和 Sub-Agents 之间无损传递。

## 1. 📍 Current Status (当前状态)

**当前阶段**: [ ✅ 已交付 ]
**当前任务**:
- [x] AS 网格参数精简（移除 as_min_step / as_max_step_multiplier / 上下层设置）
- [x] AS 价差计算按论文公式，步长 = max(半价差 * as_step_multiplier, 最小价格刻度)
- [x] AS 网格仅挂两单（1 bid + 1 ask），风控为最大回撤保护（as_max_drawdown）
- [x] 私钥保存状态可视化（显著状态标记）
- [x] 允许删除动态网格/AS 网格最后一行
- [x] GRVT 缺失 pysdk 时返回友好错误，避免 Internal Server Error
- [x] Lighter 统计按 account_index 匹配修复（上一轮完成）

**下一步计划**:
- [ ] 如需现场确认：检查 WebUI 操作反馈与策略启动/统计刷新

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
- 运行参数: runtime.simulate_fill（模拟模式开关）

## 3. 🏗 Architecture & Patterns (架构与模式)

**目录结构规范**:
- apps/server/app: FastAPI 主服务与业务逻辑
- apps/server/app/web: 静态 WebUI
- apps/server/app/exchanges: 交易所适配（Lighter / Paradex / GRVT）
- scripts: 部署与运维脚本

**部署结构**:
- 远程部署服务器: 45.207.211.121:22（root）
- 服务器仓库路径: /root/grid
- Python 虚拟环境: /root/grid/.venv
- systemd 服务: /etc/systemd/system/grid.service
- 启动命令: /root/grid/.venv/bin/python -m uvicorn app.main:app --app-dir apps/server --host 0.0.0.0 --port 9999

**核心设计模式**:
- 使用 app/core/config_store 统一读写配置
- 交易所适配器分层组织
- 动态网格与 AS 网格在 UI 分表配置，后端通过 grid_mode 区分
- AS 价差按 Avellaneda-Stoikov 公式计算，步长最小为价格刻度
- AS 网格仅挂两单（1 bid + 1 ask）
- AS 风控仅最大回撤（as_max_drawdown），不使用减仓模式

## 4. 📝 Key Decisions Log (关键决策记录)

- **[2026-02-02]**: 移除 AS 的 as_min_step / as_max_step_multiplier / 上下层参数，采用论文公式 + 价格刻度约束。
- **[2026-02-02]**: 增加私钥保存状态可视化提示，允许删除最后一行策略。
- **[2026-02-02]**: GRVT 缺失 pysdk 时返回友好错误，避免启动策略 500。
- **[2026-02-02]**: 修复 Lighter 统计按 account_index 匹配（上一轮完成）。
- **[2026-02-01]**: 动态网格与 AS 网格彻底分开（WebUI 独立表格）。
- **[2026-02-01]**: AS 网格仅挂两单并启用最大回撤保护。

## 5. ⚠️ Known Issues & Constraints (已知问题与约束)

- 暂无已知问题。

## 6. 🎨 User Preferences (用户偏好)

- 所有自然语言回复使用中文。
- 注释和文档必须使用中文，统一 UTF-8。
- 遵循 KISS / SOLID。
- 发现缺陷优先修复再扩展。
- 禁止 MVP 或占位实现。
- 有改动需自动提交并推送远端。

---

**Last Updated**: 2026-02-02 22:44
