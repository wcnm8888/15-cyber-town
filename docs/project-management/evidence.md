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
| 当前范围 | 审阅代码、文档、tracked/untracked 和仓库边界 | 当前无活动任务；未实现 R-03；未发现真实凭证、运行时数据、Godot cache 或兄弟项目改动 | 下一任务必须由用户从 roadmap 另行选择并批准 |
