# 🧠 Project Memory (项目记忆库)

> 注意：此文件由 Agent 自动维护。每次会话结束或重要变更后必须更新。
> 目的：作为项目的长期记忆，确保上下文在不同会话和 Sub-Agents 之间无损传递。

## 1. 📍 Current Status (当前状态)

**当前阶段**: 📝 规划中
**当前任务**:
- [ ] 查看目录结构并核对 AGENTS.md/memory.md

**下一步计划**:
- [ ] 等待用户后续需求（功能开发/修复/改造）

## 2. 🛠 Tech Stack & Config (技术栈与配置)

| 类别 | 选型/版本 | 备注 |
| --- | --- | --- |
| **Language** | Python 3.11+ | 见 README |
| **Framework** | FastAPI | `apps/server/app/main.py` |
| **Web** | 静态 WebUI | 由后端 StaticFiles 托管 |

**关键环境配置**:
- 端口: 9999
- 环境变量: `GRID_HOST`、`GRID_PORT`
- 依赖拉取: `apps/server/requirements.txt` 使用 `git+https://` 获取 `lighter-python` 与 `paradex-py`

## 3. 🏗 Architecture & Patterns (架构与模式)

**目录结构规范**:
- `/apps/server/app/core`: 配置与安全、日志等核心能力
- `/apps/server/app/exchanges`: 交易所对接（Lighter/Paradex）
- `/apps/server/app/services`: 运行管理与历史数据
- `/apps/server/app/strategies`: 策略逻辑
- `/apps/server/app/web`: WebUI 静态资源

**核心设计模式**:
- FastAPI 提供 API，并静态托管 WebUI

## 4. 📝 Key Decisions Log (关键决策记录)

- **[2026-01-31]**: 后端采用 FastAPI，同时静态托管 WebUI，减少部署复杂度。

## 5. ⚠️ Known Issues & Constraints (已知问题与约束)

- 需要 Python 3.11+，并可访问 GitHub 与 PyPI。
- 公网部署需设置强管理员密码并注意安全配置。

## 6. 🎨 User Preferences (用户偏好)

- 语言要求：所有自然语言回答、注释、文档必须使用中文（UTF-8）。
- 原则：遵循 KISS 与 SOLID；优先修复缺陷，再扩展功能；禁止 MVP/占位实现。
- 工作流：非简单任务需并行使用多个子代理。
- Git：仓库已连接远程，所有更改必须提交。

---

**Last Updated**: 2026-01-31 23:24
