# 🧠 Project Memory (项目记忆库)

> 注意：此文件由 Agent 自动维护。每次会话结束或重要变更后必须更新。
> 目的：作为项目的长期记忆，确保上下文在不同会话和 Sub-Agents 之间无损传递。

## 1. 📍 Current Status (当前状态)

**当前阶段**: [ ✅ 已交付 ]
**当前任务**:
- [x] 策略币对支持动态增删，market_id 自动填充，运行控制与统计改为动态展示
- [x] 移除主界面“初始化中”状态胶囊
- [x] 同步远程仓库最新代码
- [x] 重写 README，整理结构与步骤说明
- [x] 排查 Python 3.12 环境依赖安装卡在 starknet-crypto-py 构建问题
- [x] 服务器使用 PPA 安装 Python 3.11，重建 .venv 并成功完成依赖安装
- [x] 服务器已启动服务（Uvicorn 监听 0.0.0.0:9999）
- [x] WebUI 适配移动端：新增导航下拉与策略表格卡片化
- [x] 模拟模式统计改为默认可用（干跑仍统计挂单/仓位）
- [x] 精简交易所配置：隐藏网络选择，Lighter 自动查询 account_index，Paradex 仅保留 L2
- [x] 同步服务器并重启服务，已应用最新改动

**下一步计划**:
- [ ] 如需长期避免误建 3.12 venv，可考虑调整启动脚本优先使用 python3.11
- [ ] 如需后台常驻/开机自启，可增加 systemd 服务或使用 nohup

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
- 运行参数: `runtime.simulate_fill`（仅模拟模式生效）

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
- **[2026-02-01]**: 启用 Angular 风格提交信息校验规则并沉淀到 `.githooks/commit-msg`。
- **[2026-02-01]**: 策略配置支持动态币对增删，market_id 改为自动填充，运行控制/统计/挂单选择同步动态币对。
- **[2026-02-01]**: 移除主界面“初始化中”状态胶囊。
- **[2026-01-31]**: 增加模拟成交模式（价格触线成交），运行统计走模拟成交数据。

## 5. ⚠️ Known Issues & Constraints (已知问题与约束)

- 测试/CI 流程尚未确认。

## 6. 🎨 User Preferences (用户偏好)

- 所有自然语言回复使用中文。
- 注释与文档必须使用中文，统一 UTF-8 编码。
- 遵循 KISS 与 SOLID。
- 发现缺陷优先修复，再扩展新功能。
- 禁止 MVP 或占位实现，要求完整具体实现。
- 改动后自动提交（自动生成符合 Angular 规范的提交信息）。
- 以后任务默认执行并推送到远端仓库，无需单独确认。

---

**Last Updated**: 2026-02-01 11:58

