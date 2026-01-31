# 🧠 Project Memory (项目记忆库)

> 注意：此文件由 Agent 自动维护。每次会话结束或重要变更后必须更新。
> 目的：作为项目的长期记忆，确保上下文在不同会话和 Sub-Agents 之间无损传递。

## 1. 📍 Current Status (当前状态)

**当前阶段**: [ ✅ 已交付 ]
**当前任务**:
- [x] 登录页面独立为单独页面，初始化按钮移除并自动初始化
- [x] 内容页调整为顶栏导航样式并加入锚点导航
- [x] 顶栏导航切换为单页显示（点击仅显示对应页面）

**下一步计划**:
- [ ] 等待新的需求指令

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
- **[2026-02-01]**: WebUI 采用 Kanagawa Wave 配色方案。
- **[2026-02-01]**: 登录页与内容页分离，内容页使用顶栏导航。

## 5. ⚠️ Known Issues & Constraints (已知问题与约束)

- 测试/CI 流程尚未确认。

## 6. 🎨 User Preferences (用户偏好)

- 所有自然语言回复使用中文。
- 注释与文档必须使用中文，统一 UTF-8 编码。
- 遵循 KISS 与 SOLID。
- 发现缺陷优先修复，再扩展新功能。
- 禁止 MVP 或占位实现，要求完整具体实现。

---

**Last Updated**: 2026-02-01 00:29
