# Cyber Town 验收证据索引

本文件只保留可恢复的最终证据摘要；详细任务范围、Step 过程和失败修复记录位于 [`../archive/task-cards/`](../archive/task-cards/)，提交、CI 与合并事实以对应 GitHub PR 为准。

| 任务 / 验证项 | 方法 | 结果 | 未覆盖范围 / 风险 |
| --- | --- | --- | --- |
| F-001 工程与契约基线 | 本地 UAT、独立 QA、统一门禁、GitHub Actions 与归档 | Python 3.12/uv、Pydantic v1 对话契约、派生 schema、统一质量入口和 CI 已建立；交付载体为 PR #1 | 不包含 API、Godot、LLM 或数据库；详细记录见 F-001 归档 |
| F-002 工具与依赖 | 官方发布资产与 SHA-256、普通/headless 版本、uv lock | Godot 4.7.2 Standard official；FastAPI 0.141.1、Uvicorn 0.52.4、HTTPX 0.28.1；lock 38 packages | 未修改系统 PATH，未安装 .NET 或 export templates |
| F-002 健康 API | API 契约、方法、side-effect 和启动入口负例 | `GET /api/v1/health` 精确返回固定三字段；GET-only、无 body/query/dependency；只允许 loopback bind | 不包含 Dialogue、LLM、数据库或生产服务 |
| F-002 Godot 客户端 | Godot unit、scene import/load、真实 HTTPRequest | 五态文案、严格响应、3 秒 timeout、单在途请求与手动 Retry 通过；redirect、重复键、非字符串与非法响应 fail-closed | 低保真 Windows 桌面诊断场景，不是正式游戏 UI |
| F-002 真实集成 | owned FastAPI/loopback fixtures 与 Godot 4.7.2 | 9 个场景通过：停服、503、重复键、非字符串、redirect 拒绝、connected 及三种失败恢复；8000/8001 最终释放 | 仅 loopback，不访问公网、生产、LLM 或数据库 |
| F-002 独立 QA | 两轮修复复验及最终 22 个响应变体重放 | 最终结论 NO FINDINGS；P0/P1/P2/P3 均无；历史 duplicate、redirect、bind、类型和停服 oracle 均通过 | 独立 QA 不替代用户窗口 UAT 或远程 Linux CI |
| F-002 用户 UAT | Windows 真实 Godot 窗口检查环境、connected、timeout/Retry、unavailable/恢复 | `UAT_RESULT=PASS`；用户确认四组流程均通过，结束后返回 `PORT_8000_STOPPED=YES` | 截图未逐帧冻结所有瞬时状态；用户完成确认作为人工证据 |
| F-002 最终本地门禁 | `uv run --frozen python scripts/quality.py` 及交付专项检查 | pytest 134；Godot import/unit；9 integration；ruff、mypy 18 files、schema、lock、ignore、sensitive、Markdown、workflow YAML/静态契约与 diff 全通过 | Windows 本地结果不替代 GitHub Linux runner |
| F-002 GitHub 交付 | 精确暂存 36 文件；提交、push、PR 与 GitHub-hosted Linux CI | 功能提交 `ffe2443`；分支 `feat/f-002-godot-fastapi-connectivity`；PR #2 首个功能 HEAD 的 `Quality` 通过；任务卡与计划已在同一 PR 准备归档 | 归档提交会产生新 HEAD；最终 CI、合并状态与 merge SHA 以 GitHub PR #2 为准 |
| F-003 工具与配置 | 锁文件、SDK import、安全配置与负向测试 | `openai 3.3.1`、lock 45 packages；provider 默认 disabled；批准模型/base URL、12 秒 timeout、零 SDK retry、non-thinking 和 non-stream 已冻结；离线策略测试在 pytest 临时目录隔离真实 `.env` | 真实 key 只允许由专项授权进程从 Git 忽略的本地 `.env` 读取 |
| F-003 Persona 与应用边界 | 冻结 persona、SDK-neutral fake provider、应用/HTTP/Godot 自动测试 | 固定 `neon_guide / Nia`；严格 Dialogue v1、公共错误映射、进程内幂等、单在途请求、手动 Retry 和脱敏 audit 通过 | 无数据库、长期记忆、多 NPC、工具调用或持久幂等 |
| F-003 真实 DeepSeek smoke | 受预算限制的真实 adapter 调用与 usage 审核 | HTTP 200；provider 为 `deepseek`；模型为 `deepseek-v4-flash`；返回严格 Dialogue v1，usage 与安全 audit 可核查 | 单次真实模型行为不保证后续外部 provider 可用性 |
| F-003 Persona 真实评估 | 12 项固定身份、语气、相关性、事实/能力边界、注入和语言用例 | 全部通过；rubric 12/12；最后一项复用真实 Godot 场景并验证 `loading → success`、Nia 身份及脱敏 trace | 不保存原始玩家消息、persona prompt 或模型回复；不能代替用户窗口 UAT |
| F-003 Step 5 历史调用与费用 | 按 provider usage 和官方峰值单价计算 Step 5 专项验收保守上界 | Step 5 为 13/15 次真实请求；输入 1770 token、输出 809 token；费用上界 USD 0.00184668 / USD 0.05；零自动 retry | 该统计只覆盖 Step 5；用户 UAT 真实调用次数与新增费用未单独提供，不推算总量 |
| F-003 Step 6 失败优先修复 | synthetic/fake Python 与 Godot 负例、两轮独立复审 | 首轮 16 个 Python 负例和 4 个 Godot 负例先失败；fake loopback 缺失与复审新增 3 个畸形 `choices` 变体亦先失败，修复后全部通过 | 首轮 3 项 P1、6 项 P2 及同类新增 choices P2 均关闭；无真实模型调用 |
| F-003 对话 fake 集成 | 真实 Godot HTTPRequest → loopback FastAPI → FakeProvider | 8 场景通过：成功，503/504/502 后手动恢复，错误/缺失/重复 Content-Type 和 HTTP 201 拒绝；冻结 payload 与 provider 调用次数受检 | 仅 loopback，不读取真实 `.env`、不调用 DeepSeek；headless 结果不能代替用户 UAT |
| F-003 Step 6 独立 QA | 两名 reviewer 从任务卡独立设计 synthetic/fake 负例并审阅 tracked/untracked 范围 | 后端 `P0/P1/P2/P3=0`、197 passed；Godot/API `P0/P1/P2=0`、58 passed；19 个历史阻塞专项及 14 个畸形 SDK 响应复验通过 | 不替代用户真实窗口 UAT、GitHub Linux CI 或后续远程交付 |
| F-003 Step 6 全量门禁 | `uv run --frozen python scripts/quality.py` | pytest 262；lock 45；mypy 35 files；ruff、schema、Godot import/unit、9 个 F-002 integration、8 个 F-003 fake integration、ignore/sensitive 与 `git diff --check` 全部通过 | workflow 尚未由 F-003 远程 CI 执行；真实 provider 后续调用须另外授权 |
| F-003 用户 UAT | 用户亲自运行真实 Godot 窗口并提供脱敏验收确认 | `UAT_RESULT=PASS`；真实成功回复、503/504/502 后手动 Retry 恢复、提示注入边界和发送期间按钮禁用均通过；`PORT_8000_STOPPED=YES` | 用户未单独提供 UAT 真实模型调用次数与新增费用；不保存截图、原始玩家消息或模型回复 |
| F-003 Step 7 最终本地交付门禁 | 用户 UAT 后重新运行 fake-only 统一入口和交付专项 | pytest 262；9 个健康 loopback、8 个对话 fake loopback、lock、ruff、mypy、schema、Godot、ignore/sensitive、24 个 Python 文件 format、2 个 workflow 静态测试、Markdown 链接和 diff 检查全部通过 | 仅 Windows 本地结果；F-003 GitHub Linux runner、PR、合并和归档尚未执行 |
| 当前范围 | 审阅任务卡、受控代码、项目文档与仓库边界 | 活动任务为 `F-003 / ready_for_git_delivery`；本地 `.env` 被忽略，自动化读取次数为 0，独立 QA 与用户 UAT 均通过 | 等待单独授权 Git 交付；未执行 commit、push、PR、远程 CI、归档或 R-04 |
