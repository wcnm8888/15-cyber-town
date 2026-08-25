# 技术栈审查与候选基线

| 领域 | 推荐候选 | 解决的问题 | 替代项 / 成本 | 本轮结论与验证 |
| --- | --- | --- | --- | --- |
| 游戏前端 | Godot 4.7.2 Standard + GDScript | 2D 场景、输入、动画和 UI | Web/Unity；Godot 学习成本低且适合目标 | F-002 诊断场景与 F-003 独立对话场景均已验证；对话采用 `HTTPRequest`、15 秒 timeout、单在途和手动 retry，无 addon、.NET 或 export templates。 |
| API | Python 3.12 + FastAPI 0.141.1 + Pydantic v2 | schema、错误语义、异步编排、OpenAPI | Flask/Starlette；FastAPI 需谨慎处理阻塞库 | 已锁定 Uvicorn 0.52.4、HTTPX 0.28.1；实现 `GET /api/v1/health` 与严格 `POST /api/v1/dialogue`。 |
| LLM | DeepSeek `deepseek-v4-flash` + OpenAI SDK 3.3.1，经 Provider adapter | 固定 Nia 的单轮角色对话 | 其他 OpenAI-compatible 模型；成本和可用性外部化 | F-003 锁定 non-thinking/non-stream、temperature 0.6、max tokens 256、12 秒 timeout 和零 SDK retry；真实 smoke、12 项 persona 评估及端到端通过。 |
| Agent runtime | 自建轻量领域运行时 | 显式控制上下文、状态、日志和安全边界 | HelloAgents；后者适合作为学习对照 | 倾向自建；先做 provider/agent 端口，避免框架锁定。 |
| 结构化状态 | SQLite（未来候选，当前未引入） | 本地开发的关系、会话、审计索引与事务 | PostgreSQL；后者留给多人/部署阶段 | F-003 只有进程内幂等，不保存历史、关系、记忆或审计正文；数据库必须由后续任务另行批准。 |
| 语义记忆 | 首阶段不引入；后续评估 Qdrant | 有明确价值的语义召回 | SQLite FTS、Qdrant local/remote；增加 embedding、运维和隐私成本 | 先测短期记忆 + 结构化摘要；基准证明不足才引入。 |
| 通信 | HTTP REST | 单轮对话及状态查询 | SSE/WebSocket；复杂度更高 | 第一版锁定 REST，设定升级触发条件。 |
| 可观测性 | 结构化日志 + trace_id + 脱敏事件 | 调试、成本、延迟和安全审计 | OpenTelemetry/外部平台；后续再选 | F-003 只输出 allowlist 元数据，不写 JSONL/SQLite；禁止 key、prompt、玩家消息、模型回复和 provider body 落盘。 |

## 时效性核对（2026-08-24）

- 参考章使用 Godot + FastAPI + HelloAgents + SQLite/Qdrant 的四层结构，源码仍位于 `code/chapter15/Helloagents-AI-Town`；架构思想有效，但不能视其为生产模板。
- Godot stable 文档仍提供 `HTTPRequest`，并要求同一节点避免并发请求，建议普通 REST 设置 1–10 秒的显式 timeout。
- FastAPI 官方仍支持混用 `def` 与 `async def`；路径函数应按所调用库是否 awaitable 选择，不能把同步存储/SDK 伪装为异步。
- DeepSeek 官方当前列出 `deepseek-v4-flash`，支持 JSON 输出、工具调用和流式响应；thinking 默认开启，首切片应显式评估/配置非思考模式与输出上限以控制交互延迟。价格和限流会变化，实施当天必须复核。
- Qdrant Python client 支持 local mode，但向量服务不是“免费记忆”；仍有 embedding、检索质量、隔离、备份与数据留存成本。

## F-001 Step 0 工具链锁定

- Python：项目基线 `3.12`；已由 `uv` 安装 3.12.10 到项目内 `.tools/python`，缓存位于 `.cache/uv`；两者与 `.venv` 均被 Git 忽略。
- 包与解释器管理：现有 `uv 0.6.14`；根目录维护 `pyproject.toml` 与 `uv.lock`，直接依赖使用兼容范围，锁文件固定实际解析版本。
- 包布局：`backend/src/cyber_town/` + `backend/tests/`；根 `pyproject.toml` 统一管理。
- 构建后端：Hatchling `1.27.0`；在 `pyproject.toml` 精确固定，仅用于可安装包基线，不引入服务路由。
- 契约唯一源：`backend/src/cyber_town/contracts/v1.py` 的 Pydantic v2 strict models（`extra=forbid`）；`contracts/v1/*.schema.json` 为可重复生成的派生产物。
- Schema validator：开发依赖 `jsonschema 4.26.x`，用 Draft 2020-12 validator 和 UUID format checker 直接验证派生契约；`types-jsonschema` 提供严格类型检查。
- 统一质量入口：`uv run --frozen python scripts/quality.py`，顺序运行安全预检、lock freshness、ruff、mypy、schema drift、Godot import/unit、真实 loopback integration、pytest 和安全复检。
- CI：GitHub Actions `ubuntu-latest`；checkout 与 setup-uv 固定完整 commit，uv 固定 `0.6.14`，Python 由 `.python-version` 固定为 `3.12.10`；仅 `contents: read`，无 secrets、服务容器、发布或业务外部调用。
- Git：`origin` 指向私有仓库 `wcnm8888/15-cyber-town`；F-001 通过 PR #1 交付，F-002 的交付与归档事实由 PR #2 记录。
- v1 契约：Pydantic v2 strict models 已实现；未知字段和类型强制转换被拒绝，JSON Schema 使用 Draft 2020-12 并由导出器确定性生成。

## F-002 连通基线

- Godot：4.7.2-stable Standard；Windows 便携工具固定在批准路径，CI 使用官方 Linux x86_64 Standard zip 和发布资产 SHA-256。
- 本地 API：`uv run --frozen python -m cyber_town.api`，默认只监听 `127.0.0.1:8000`。
- 游戏入口：`game/project.godot`，单一 `Control` 场景；原生桌面 HTTPRequest 不启用 CORS。
- 统一门禁已扩展为 Godot editor import、GDScript unit、9 个真实 loopback 场景和 Python pytest；集成工具不访问公网、LLM 或数据库，并验证 redirect target 不被访问。
- 已验证事实：Windows Godot 4.7.2 对无监听 loopback 的结果为 `RESULT_TIMEOUT`；非 2xx fixture 映射为 unavailable。该平台差异已由独立 QA、用户 UAT 和 GitHub Linux CI 共同复核。

## F-003 单 NPC 对话基线

- Python 运行依赖新增并锁定 `openai 3.3.1`；SDK 只允许由 `infrastructure/llm` adapter 导入，application/domain 使用 provider-neutral protocol。
- DeepSeek 固定 `deepseek-v4-flash` 与 `https://api.deepseek.com`，non-thinking、non-stream、temperature 0.6、max tokens 256、12 秒 timeout、SDK `max_retries=0`；provider 默认 disabled。
- 固定 persona 为 `neon_guide / Nia`、版本 `nia_v1`；API 为严格 `POST /api/v1/dialogue`，Godot timeout 15 秒且只允许手动 Retry。
- 真实 Step 5 验收共 13 次请求、1770 输入 token、809 输出 token；按 2026-08-25 官方峰值价格保守估算 USD 0.00184668，rubric 12/12，真实 Godot 端到端通过。
- 本机 SOCKS `ALL_PROXY` 与未锁定的 `socksio` 不兼容；验收只在子进程移除该变量并保留 HTTP/HTTPS 代理，不新增依赖或修改系统配置。
- 自动测试与 CI 继续 fake-only，无 API key、真实 provider 或费用。数据库、记忆、多 NPC、流式输出与 R-04 均未实现。

来源： [HelloAgents 第十五章](https://github.com/datawhalechina/hello-agents/blob/main/docs/chapter15/%E7%AC%AC%E5%8D%81%E4%BA%94%E7%AB%A0%20%E6%9E%84%E5%BB%BA%E8%B5%9B%E5%8D%9A%E5%B0%8F%E9%95%87.md)、[Godot HTTPRequest](https://docs.godotengine.org/en/stable/classes/class_httprequest.html)、[FastAPI 并发说明](https://fastapi.tiangolo.com/async/)、[DeepSeek 模型与价格](https://api-docs.deepseek.com/quick_start/pricing/)、[Qdrant local mode](https://qdrant.tech/documentation/frameworks/langchain/)。

## 参考方案保留与修改

| 参考设计 | 结论 | 本项目调整 |
| --- | --- | --- |
| Godot → FastAPI → Agent 分层 | 保留 | 用显式 API schema、trace、错误语义与 adapter 边界补强。 |
| 每个 NPC 一个 `SimpleAgent` | 部分保留 | NPC 必须拥有独立配置/状态/记忆 scope；运行时对象不必一 NPC 一套框架和 LLM client。 |
| 每个 NPC 各建 LLM | 修改 | 共享受限并发的 provider client；请求上下文严格隔离。 |
| SQLite + Qdrant | 修改 | SQLite 是结构化真相；Qdrant 仅在评估证明语义检索必要后引入，不与 SQLite 重复存相同事实。 |
| 一开始保存全部长期记忆 | 修改 | 先工作记忆和可审计摘要；记忆必须提取、冲突、过期和遗忘。 |
| LLM 直接给好感度加分 | 修改 | LLM 只输出受校验类别；确定性映射、范围、幂等与状态机负责写入。 |
| 内存 `dict` 保存 NPC/关系状态 | 修改 | 内存只作缓存/锁，持久化状态由 SQLite 事务保存和恢复。 |
| REST 轮询状态 | 条件保留 | 单轮对话/查询够用；仅在流式、推送、多玩家广播或高频同步时升级 SSE/WebSocket。 |
| 批量生成多个 NPC 对话 | 首版拒绝 | 合并 prompt 易造成角色/记忆串扰，且“成本降至 1/3”需基准而非假定；先保证单 NPC 质量。 |
| 对话全文写控制台/文件日志 | 修改 | 默认记录脱敏结构化事件和 hash/长度；原文仅在明确开发许可、最小保留期和访问控制下保存。 |
| Prompt 仅要求角色扮演 | 修改 | 采用来源标记、不可覆盖 persona、输入/输出策略、长度限制、注入测试和拒绝/降级路径。 |
| LLM 返回直接使用 | 修改 | 使用 Pydantic/schema 和枚举校验；无效 JSON、`content_filter`、超时和限流都有明确错误映射。 |
| 只记录“能回复” | 修改 | 评估 persona、记忆、隔离、安全、p95 延迟、tokens/cost、失败率和 trace 完整率。 |
| NPC 间自主协作 | 延后 | 先完成玩家—NPC 闭环；未来必须有跨 NPC 协议、调度、锁、审计、成本预算与 kill switch。 |
