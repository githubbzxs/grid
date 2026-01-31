# 🧠 Project Memory (项目记忆库)

> 注意：此文件由 Agent 自动维护。每次会话结束或重要变更后必须更新。
> 目的：作为项目的长期记忆，确保上下文在不同会话和 Sub-Agents 之间无损传递。

## 1. 📍 Current Status (当前状态)

**当前阶段**: [ 🚧 开发中 ]
**当前任务**:
- [x] 确认远程仓库地址为 https://github.com/githubbzxs/grid
- [ ] 与用户确认是否需要推送当前本地提交（main 已领先 origin）

**下一步计划**:
- [ ] 如需同步远程，执行 `git push`
- [ ] 处理 README/PLAN 中文乱码的编码问题

## 2. 🛠 Tech Stack & Config (技术栈与配置)

| 类别 | 选型/版本 | 备注 |
| --- | --- | --- |
| **Language** | Python 3.11+ | README 要求 |
| **Framework** | FastAPI + Uvicorn | API 与 WebUI 服务 |
| **Crypto** | cryptography | 密钥加解密 |
| **SDK** | lighter-python / paradex-py | 交易所 SDK |
| **Storage** | JSON 文件 | `data/config.json`、`data/runtime_history.jsonl` |

**关键环境配置**:
- Python Version: >= 3.11
- 默认端口: 9999（本地 127.0.0.1）
- 环境变量: `GRID_HOST`、`GRID_PORT`、`GRID_DATA_DIR`

## 3. 🏗 Architecture & Patterns (架构与模式)

**目录结构规范**:
- `apps/server/app`: FastAPI 后端与业务逻辑
- `apps/server/app/web`: 静态 WebUI
- `apps/server/app/exchanges`: Lighter / Paradex 交易所适配
- `apps/server/app/strategies`: 网格策略实现
- `scripts`: 启动与更新脚本

**核心设计模式**:
- 配置由 `app/core/config_store` 统一读写
- 交易所适配与策略实现分层组织

## 4. 📝 Key Decisions Log (关键决策记录)

- **[2026-01-31]**: 建立 `memory.md` 作为项目记忆库。

## 5. ⚠️ Known Issues & Constraints (已知问题与约束)

- README.md 与 PLAN.md 中文显示存在乱码（疑似编码不一致）。
- 测试/CI 流程尚未确认。

## 6. 🎨 User Preferences (用户偏好)

- 所有自然语言回复使用中文。
- 注释与文档必须使用中文，统一 UTF-8 编码。
- 遵循 KISS 与 SOLID。
- 发现缺陷优先修复，再扩展新功能。
- 禁止 MVP 或占位实现，要求完整具体实现。

---

**Last Updated**: 2026-01-31 23:40
