# 项目进度

## 当前状态

- 生命周期：`git_delivery_authorized / F-006_deterministic_affection`。
- 当前能力：Godot/FastAPI 健康诊断、固定 Nia 对话、三元 scope 进程内短期记忆，以及双元 scope 标准库 SQLite 低敏感长期事实；公开 Dialogue v1、既有 Godot 场景和唯一 Nia persona 保持不变。
- F-005 交付：功能提交 `338852e4dd03f8c679f8a2db920e2ba7bd6f968e` 已通过 PR #5 合并；当前 `main` / `origin/main` 为 `c9d11b0a3c441a10463ad4522bb226f055f07f35`。
- 最终自动化：统一 fake-only 质量入口 `1095 passed`；lock、ruff、mypy、Schema、Godot import/unit、9 健康 + 10 对话 loopback、ignore/sensitive 均通过，自动化不读取 `.env` 或调用真实 provider。
- 检索评估：72 项固定 golden set precision `1.00`、recall `1.00`；跨 scope 泄漏、已遗忘召回、旧值复活和空结果虚构均为 0。
- 独立 QA：首轮 5 项 P1、3 项 P2 及近邻全部失败优先修复；两名 reviewer 最终均为 `NO FINDINGS`。
- 真实评估与用户 UAT：Step 5 为 7 次、1244/106 tokens、USD 0.000690；Step 7 为 3 次、500/141 tokens、USD 0.000408；合计 10 次、1744/247 tokens、USD 0.001098，pending=0，未超预算。
- 用户真实 Godot 窗口已验证初始 unknown、记住、跨窗口/重启召回、更新、遗忘及最终 unknown；8000 端口已释放，正式业务数据库不存在。
- 运行资源：Step 5/Step 7 隔离 SQLite、metadata-only 调用台账及 SQLite sidecar 均受 Git 忽略并保留；项目 `.venv`、`.env`、Godot 缓存与共享工具同样保留，未获得任何删除授权。
- F-006 Step 0 已锁定：双元关系 scope、追加 SQLite `0002` 迁移策略、确定性五分类/状态机、只读关系 API、fake-only 评估边界和最小 Godot 视觉契约。
- F-006 Step 1 已完成：本地分支 `feat/f-006-deterministic-affection`、冻结 relationship 配置及失败优先负例；首次 77 failed，最终 `test_config.py` 354 passed，定向 ruff/format/mypy/diff 通过。未创建数据库、表、migration 或运行时 data。
- F-006 Step 2 已完成：纯领域严格 suggestion parser、确定性五类映射、置信度阈值、0–100 饱和、四阶段、UTC 冷却和参数化穷举不变量；首次模块缺失，最终领域 68 passed、配置联合 422 passed，定向 ruff/format/mypy/diff 通过。未接入 provider、SQLite、API 或 Godot。
- F-006 Step 3 已完成：保持 `0001` 不变，增加有序迁移前缀校验与 `0002_relationship_state.sql`；实现双元 scope 状态/metadata-only 事件仓储、`BEGIN IMMEDIATE` 原子写入、request 幂等/冲突、锁边界和顺序审计回放。定向 34 passed；全套自动化分两批 `672 + 576 = 1248 passed`，mypy、ruff、format、diff 通过。未接入 DialogueService、API、Godot 或 provider；仅 pytest 临时 SQLite，不存在项目运行时数据库。
- F-006 Step 4 已完成：同次 provider completion 的 JSON 内部建议经严格 parser 进入确定性关系服务；仅 completed 有效请求写入。新增只读关系 GET，Dialogue v1/schema 不变；Godot 低保真快照与 request 刷新已接入。140 项定向后端测试、Godot 单测和 10 场景 Godot→FastAPI→FakeProvider→临时 SQLite loopback 通过；未读取 `.env`、调用真实模型、复用 F-005 资源、创建项目运行时数据库、提交或推送。
- F-006 Step 5 已完成：新增纯内存评估器，遍历 2020 个基础 + 2020 个冷却的规则判定、24 个越权/注入建议与 2 个 UTC 日界案例，违规为 0；completion→API 的 3 个操纵 suggestion 回归均完成正常 Dialogue v1、记录 inert `candidate_invalid` 事件并保持 20 分。关系专项 82 passed，定向 ruff/format/mypy 通过；仅使用 pytest 临时 SQLite，未读取 `.env`、调用真实模型、复用 F-005 资源、提交或推送。
- F-006 Step 6 已完成：三个临时 FakeProvider FastAPI 黑盒服务验证关系初始/成功/重放/scope/422、越权 completion 仍 inert、4 个并发 completed 请求只保留一次有效 +2；未确认产品缺陷。统一质量入口运行至既有对话 loopback，8000 已释放但终端未捕获其末行摘要；应用内浏览器拒绝 loopback 并作为工具限制记录，不替代 Step 7 UAT。临时服务均已停，正式运行时数据库不存在。
- F-006 Step 7 已完成：最小修复将关系区内容间距设为 4、消息输入最小高度设为 64；场景/集成几何断言通过。用户 Godot + FakeProvider 窗口重新 UAT 确认 reply、`21/100`、`Acquaintance`、`Change: +1` 与完整 `Reason: rule_friendly`。交付前审查补强客户端 reason 白名单、409 冲突映射、关系 GET OpenAPI 参数和审计回放/状态表一致性校验；最终统一质量入口通过（1257 pytest、Godot import/unit、9 连通性 + 10 对话 loopback、ruff、67 文件 mypy、schema、lock、ignore/sensitive）。临时服务已停、8000 已释放，正式运行时数据库不存在。
- 未覆盖：Qdrant/embedding、多 NPC、正式素材、生产部署，以及单独授权后的 Git 交付。

## 下一批准动作

F-006 Git 交付已获授权，正在执行 commit、push、PR 和 CI；仍不得进入 R-07、读取 `.env`/API key、调用真实模型或复用 F-005 资源。
