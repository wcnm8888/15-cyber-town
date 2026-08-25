# 任务卡：F-005 长期记忆与检索评估

状态：`approved / step_7_complete / ready_for_git_delivery`。

来源：[`roadmap.md`](roadmap.md) 的 `R-05`。前置任务 F-001—F-004 均已通过 PR #1—#4 交付并归档；F-004 squash merge 后当前 `main`、`origin/main` 与 HEAD 均为 `3e03d64d129871495f3fe73295ee9b11478f2e71`。本任务为 L 级，只允许执行已获用户明确授权的当前 Step。

## 用户目标与可见价值

玩家明确要求 Nia 记住允许保存的游戏内结构化事实后，在新 conversation 与本地服务重启后仍能召回；不同 player/NPC 相互隔离，更新、过期与遗忘后旧值不再被召回，没有可用记忆时明确回答不知道，不编造既往交流。

长期记忆不得保存原始聊天全文、完整 prompt、模型回复、API key、凭证或真实个人敏感信息；Godot 继续复用既有低保真对话场景与公开 Dialogue v1。

## 已批准默认决策

- SQLite 是唯一长期结构化事实真相源，只使用 Python 3.12 标准库 `sqlite3`；不新增 SQLAlchemy、Alembic、FTS、embedding、Qdrant、PostgreSQL、Redis 或其他存储依赖。
- 正式本地数据库路径为 `data/cyber-town.sqlite3`；UAT 使用 `data/uat/f-005/<run-id>/cyber-town.sqlite3`，自动化只使用 pytest `tmp_path`；数据库、WAL/SHM/journal、UAT 数据和调用台账均不得进入 Git。
- 短期 scope 保持 `(player_id, npc_id, conversation_id)`；长期 scope 固定 `(player_id, npc_id)`，conversation/request/trace 只作为来源，不阻碍跨会话召回。
- 首批白名单 fact key 为 `game_alias`、`preferred_language`、`reply_style`、`favorite_cyber_town_topic`；memory type 仅允许 `profile`、`preference`。
- 只接受确定性的 `请记住：<key>=<value>`、`请永久记住：<key>=<value>`、`请忘记：<key>` 及对应英文模板；普通对话不自动写入，模型不得决定持久化。
- 默认过期 30 天；永久保存必须明确要求，并且只能用于任务批准的低敏感白名单事实。
- 每个 player/NPC 最多 64 条 active 记忆，全局最多 4096 条；每次最多召回 4 条，禁止 LRU 静默删除有效长期事实。
- 更新保持同一 `memory_id`、递增 `version`；遗忘清空 `fact_value` 并保留不含正文的 tombstone，过期或遗忘后绝不召回。
- 显式记忆管理命令不调用 provider，通过现有 Dialogue v1 返回确定性 `completed / local-memory` 结果；不新增公开 memory API，不修改公开 Schema 或 Godot 场景。
- Nia persona 仍为唯一最高优先级 system；长期事实通过独立 SDK-neutral DTO 作为不可信、低优先级 user 数据注入，不得伪装成 system/developer/tool。
- 继续固定 8192 UTF-8 工程预算和 256 回复预留；先保留 persona、当前问题与回复额度，再选择精确长期事实，最后按完整回合加入最近短期历史。
- SQLite 写事务使用参数化 SQL、`BEGIN IMMEDIATE` 与 2 秒锁等待；初始化/schema version、损坏、锁冲突和事务异常均 fail-closed，不自动删除或重建正式数据库。
- Golden set 最少 60 项，precision ≥ 0.95、recall ≥ 0.90，scope 泄漏、过期/遗忘后召回、旧值误召回和空结果虚构均为 0。
- Step 5 真实评估最多 8 次 / USD 0.035，Step 7 用户 UAT 最多 4 次 / USD 0.015，F-005 合计最多 12 次 / USD 0.05；两个 Step 的真实调用、API key 与费用均须独立明确授权。
- 跨进程预算台账路径为 `data/acceptance-ledgers/f-005.sqlite3`；每次真实请求前原子预留调用与费用，provider 返回后先记录脱敏 usage，再执行语义断言；缺失 usage、额度耗尽、台账冲突或进程中断一律 fail-closed。

## 范围

1. 白名单长期记忆值对象、scope、来源、importance、confidence、status、version、过期与无正文 tombstone。
2. 标准库 SQLite schema version、初始化、受限路径、参数化 repository、唯一约束、事务、锁等待、容量、故障与恢复边界。
3. 显式记住/忘记命令、同 player/NPC 跨 conversation 召回、FastAPI 服务重启后恢复，以及跨 player/NPC 严格隔离。
4. 确定性 exact fact_key 与固定别名检索、过滤、排序、冲突处理、撤销、过期与诚实空结果。
5. provider-neutral 事实 DTO、唯一 persona system、不可信事实边界及长期事实与短期完整回合的统一 8192 预算。
6. 请求 Retry/replay/concurrency 不重复写；失败、取消、degraded、无效响应和晚到结果不生成长期事实。
7. FakeProvider、Godot loopback、固定 golden set、跨进程真实调用台账、独立 QA、单独授权的真实评估与用户 UAT。
8. 当前事实文档、SQLite ignore、临时资源生命周期、最终本地门禁和另行授权的 Git/PR/CI/归档交付。

## 非目标

- 不进入 R-06，不实现好感度、关系状态机、交易、多 NPC 或自主 Agent 行为。
- 不安装/启动/连接 Qdrant，不引入 embedding、FTS、PostgreSQL、Redis 或第二存储。
- 不备份完整聊天，不保存真实个人敏感信息、API key、prompt、原始玩家消息或模型回复。
- 不修改 `DialogueRequestV1`、`DialogueResponseV1`、`ApiErrorV1`、公开 JSON Schema、Godot 生产场景、依赖锁文件或 GitHub Actions workflow。
- 不新增公开 memory API、正式 UI、正式美术、公网部署或生产数据库。
- 不复用 F-004 的真实模型预算、API key 调用授权或 Git 授权。

## 数据模型、保留与隔离

`long_term_memories` 必需字段：`memory_id`、`player_id`、`npc_id`、`memory_type`、`fact_key`、active 时必需的受约束 `fact_value`、`source_conversation_id`、`source_request_id`、`source_trace_id`、`importance`、`confidence`、`created_at`、`updated_at`、`version` 和 `status`；`expires_at` 可空且仅允许明确永久保存。

- `memory_id` 和来源 ID 使用 canonical UUID；scope 字段遵守现有 1–64 字符边界。
- `importance` 为 1–5；`confidence` 为 0–1000，首版显式用户事实固定为 1000；时间为 UTC Unix 秒。
- `status` 允许 `active/superseded/forgotten/expired`；forgotten/expired 的正文必须清空。
- 唯一业务键为 `(player_id, npc_id, memory_type, fact_key)`；索引覆盖 scope/status/expiry、scope/fact_key 和更新时间。
- `memory_operations` 以 `request_id` 保证写入、遗忘、Retry/replay 和请求指纹幂等；同 ID 不同 payload 映射现有 409。
- `memory_events` 仅保存创建、更新、遗忘、过期等无正文事件；禁止复制原始消息、旧值或 provider 回复。
- DB 路径必须解析到项目 `data/` 内，拒绝 `..`、外部绝对路径、symlink/reparse point 和兄弟项目路径。
- 正式运行数据属于用户状态，不得因临时资源盘点而自动删除、覆盖、迁移或重建。

## 显式命令、事务与失败语义

首版示例：

```text
请记住：game_alias=BLUE-47
请永久记住：preferred_language=zh-CN
请忘记：game_alias
Remember: game_alias=BLUE-47
Forget: game_alias
```

`game_alias` 仅接受 1–32 位字母、数字、`_`、`-`；`preferred_language` 限 `zh-CN/en-US`；`reply_style` 限 `concise/balanced`；`favorite_cyber_town_topic` 为 1–64 字符并拒绝控制字符、URL、角色伪装和指令式内容。

写入顺序：验证公开 request → 解析白名单命令 → 同长期 scope 写锁 → 检查 SQLite operation 幂等 → 在单事务中写入或遗忘 → 提交 → 返回确定性成功公开响应。事务失败不得返回 completed；普通对话、取消、degraded、晚到结果与 provider 失败不得形成长期记忆。

锁超时、容量用尽、路径/初始化异常、数据库损坏与事务失败统一 fail-closed，沿用现有 HTTP 503 / `provider_unavailable` / `retryable=true`，不泄漏 SQL、文件内容或内部异常。正式数据库损坏不得自动删除或覆盖。

## 检索、上下文与 Qdrant 升级门槛

只检索同 `(player_id, npc_id)`、`status=active`、未过期且满足 confidence 的事实；先精确 key，再固定别名，按匹配等级、importance、confidence、updated_at 与 memory_id 确定性排序，每次最多 4 条。

内部 provider 消息顺序：唯一 Nia system → 明确标记为不可信的长期事实 user 数据 → 从旧到新的完整短期 user/assistant 回合 → 当前 user。长期事实最多占 2048 工程单位；超额按完整事实裁剪，短期历史按完整回合裁剪；最小上下文无法安全构造时沿用既有 422/503。

固定 golden set 先比较短期基线与结构化长期事实。Qdrant 明确排除在 F-005；只有固定改写子集经规则优化仍低于 0.90 recall、独立原型提高至少 10 个百分点且 precision ≥ 0.95、零 scope 泄漏/删除复活、可证明第二存储一致性及隐私/费用、p95 ≤ 50 ms 且不超过结构化基线两倍时，才可另起独立候选任务。

## 测试矩阵

| 风险 / 行为 | 测试层级 | 最低断言 |
| --- | --- | --- |
| schema、路径与初始化 | 单元 / SQLite integration | 受限路径、schema version、重复初始化、临时 DB、WAL/SHM ignore |
| 数据模型与查询 | 单元 / SQLite integration | 字段类型、enum、唯一键、参数化 SQL、索引、容量、TTL |
| player/NPC 隔离 | repository / HTTP / FakeProvider | 同 scope 跨 conversation/重启召回，不同 player/NPC 零泄漏 |
| 写入、更新与遗忘 | application / SQLite integration | 显式白名单、version、正文清空 tombstone、过期不复活 |
| 事务与幂等 | application / concurrency | Retry/replay 只写一次，409 conflict，锁超时、rollback、取消/late result 不写 |
| persona 与工程预算 | application / adapter stub | 唯一 system、长期事实不可信、8192/256 固定、整条事实/完整回合裁剪 |
| golden set | fake-only evaluation | 至少 60 项；precision ≥ 0.95、recall ≥ 0.90、泄漏/旧值/虚构为 0 |
| 端到端联调 | FastAPI + FakeProvider / Godot loopback | 新会话、服务重启、更新、遗忘、空结果与既有 F-001—F-004 回归 |
| 真实调用治理 | 离线台账 / 独立专项授权 | 跨进程原子预留、逐次 usage、预算上限、未知调用 fail-closed |
| 独立 QA 与用户 UAT | 独立 reviewer / 真实 Godot 窗口 | P1/P2 全关闭，人工确认跨会话、重启、更新、遗忘与调用账本 |

自动化、统一质量入口与 GitHub CI 永久 fake-only，只使用 pytest 临时 SQLite；真实 provider 评估和真实用户 UAT 须分别取得当前 Step 专项授权。

## 文件影响与文档更新契约

候选实现范围：`backend/src/cyber_town/domain/**`、`application/**`、`infrastructure/persistence/**`、`api/composition.py`、`config.py`、`backend/tests/**`、`scripts/**` 与 `.gitignore`。

允许的长期事实文档：项目 `README.md`、`AGENTS.md`、`docs/README.md`、`architecture.md`、`tech-stack.md`、`agent-design.md`、`memory-design.md`、`evaluation-strategy.md`、`testing-strategy.md`、`decisions.md` 和 `docs/project-management/**`；按当前 Step 的实际触发条件最小更新。

默认不修改公开契约/Schema、Godot 生产场景、`pyproject.toml`、`uv.lock`、GitHub workflow 或新增公开 API；确需扩大范围时必须先停止并重新审批。

Step 0 只允许同步本任务卡、实现计划与必要入口/当前事实摘要；不修改历史归档、架构实现文档、代码、配置、ignore、依赖、Godot 或 CI。

## 真实评估、共享台账与隐私

F-005 独立调用上限：Step 5 最多 8 次/USD 0.035；Step 7 最多 4 次/USD 0.015；总计最多 12 次/USD 0.05。两次真实专项必须分别明确批准，不继承 F-004 的任何调用、费用、密钥或 Git 授权。

跨进程共享 `data/acceptance-ledgers/f-005.sqlite3`；台账仅保存 authorization/step/model、调用序号、状态、prompt/completion tokens、整数 micro-USD 与时间戳。网络请求前使用事务原子预留调用和保守费用；provider 一返回先提交脱敏 usage，再执行语义断言。

进程重启不得重置台账；额度用尽、`reserved/unknown` 未结清、usage 缺失、锁冲突、费用异常均 fail-closed，任何人工调账须用户明确批准。台账不得保存 API key、persona、原始消息、模型回复或 prompt。

## Step 0 已批准执行与完成事实

- 当前分支仍为 `main`；HEAD / `main` / `origin/main` 均为 `3e03d64d129871495f3fe73295ee9b11478f2e71`，origin 指向现有项目私有仓库，开始前工作树干净。
- F-004 已通过 PR #4 squash merge 并归档；任务卡和实现计划分别位于 `docs/archive/task-cards/F-004-short-term-memory-context-budget.md` 与 `F-004-implementation-plan.md`。
- 当前 Python 为 3.12.10，标准库 SQLite 版本为 3.47.1；现有项目没有 SQLite 数据文件、repository、migration、embedding 或向量依赖。
- 公开 Dialogue v1、短期 scope、8192/256 预算、provider-neutral 历史、DeepSeek adapter、FastAPI composition 和 Godot conversation/retry 行为已只读核对。
- 现有 `.gitignore` 已覆盖 `data/*.db`、`data/*.sqlite*` 与 `data/qdrant/`；分层 UAT 数据、共享台账和旁路文件的显式规则留待 Step 1 单独批准。
- 只同步获批任务卡、实现计划、项目入口及 F-004 已合并/归档的当前状态；未创建分支、数据库、目录、表、migration 或运行时文件。
- 未读取 `.env` / API key，未调用真实 provider，未修改公开契约、代码、依赖、Godot、CI 或已归档任务，未提交、推送或进入 R-06。

## Step 1 已批准执行与完成事实

- 创建并检出 `feat/f-005-long-term-memory-retrieval-evaluation`；HEAD / `main` / `origin/main` 均为 `3e03d64d129871495f3fe73295ee9b11478f2e71`，Step 0 八份已批准文档修改完整保留，未暂存或提交。
- 先新增长期 scope、fact key、冻结数值、配置类型、路径逃逸、模拟 symlink 与 SQLite ignore 负例，首次专项执行为 `130 failed, 5 passed`，确认测试先于实现。
- `Settings` 锁定长期 scope `(player_id, npc_id)`、4 个已批准 fact keys、64 条/scope、4096 条全局、每次 4 条、30 天 TTL、2048 长期工程预算与 2 秒 SQLite 锁等待；F-004 的 8192 总预算/256 回复预留保持不变。
- 正式数据库、UAT 数据根与共享台账路径分别固定为 `data/cyber-town.sqlite3`、`data/uat/f-005`、`data/acceptance-ledgers/f-005.sqlite3`；外部绝对路径、`..`、未批准同根路径、错误类型及 symlink/junction 逃逸 fail-closed，不创建任何目录或数据库。
- `.gitignore` 保留原有根目录 SQLite 规则，并补充任意层级 `.db/.sqlite*`、`data/uat/` 与 `data/acceptance-ledgers/`；WAL/SHM/journal 和 UAT 非数据库附件均已通过负例验证，可审查 `data/public-policy.md` 不被误隐藏。
- F-005 专项 `135 passed`；全部配置测试 `277 passed`；两文件 ruff/format/mypy 均通过。统一 fake-only 质量入口 `719 passed`，lock 45 packages、mypy 42 files、Schema、Godot import/unit、9 健康 + 10 对话 loopback、ignore/sensitive 全通过。
- 未创建 `data/`、SQLite 数据库、schema、表、migration、repository、记住/忘记/检索能力或调用台账；未修改公开 Dialogue v1、Godot、依赖、CI；未读取 `.env` / API key、调用真实 provider、提交、推送或进入 Step 2/R-06。

## Step 2 已批准执行与完成事实

- 开始前只读复核功能分支、HEAD / `main` / `origin/main` 均未漂移，工作树正好保留 Step 0—1 的 11 项已批准修改；项目 `data/` 不存在。
- 先新增领域值对象与 SQLite repository 两组专项测试，首次执行因 `cyber_town.domain.long_term_memory` 尚不存在产生 `2 errors during collection`，确认失败测试先于实现。
- `LongTermMemoryScope` 固定 `(player_id, npc_id)`；不可变 `LongTermMemoryRecord` 锁定 UUID 来源、`profile/preference`、4 个白名单 fact keys、事实值边界、importance/confidence、UTC Unix 秒、version、状态与无正文 forgotten/expired tombstone；事实正文不进入 `repr`。
- 新增版本化 `0001_long_term_memory.sql`，仅使用标准库 SQLite 定义 `long_term_memories`、`memory_operations`、`memory_events` 与 migration 版本/校验；业务唯一键、scope/status/expiry、scope/fact 与更新时间索引已覆盖。
- repository 使用显式隔离路径、WAL、foreign keys、2 秒 busy timeout、`BEGIN IMMEDIATE` 与参数化 SQL；验证重复初始化、scope 隔离、SQL 注入字符串、唯一键冲突、无正文事件、事务 rollback、损坏/版本异常与锁冲突 fail-closed。
- 所有 SQLite 数据库只由 pytest `tmp_path` 创建：长期记忆专项 `130 passed`，既有配置回归 `277 passed`，统一 fake-only 质量入口 `849 passed`；ruff、mypy 47 files、lock 45 packages、Schema、Godot unit/import、9 个健康 loopback、10 个 fake 对话 loopback、ignore/sensitive 均通过。
- 未创建项目 `data/`、正式/UAT SQLite 数据库或调用台账；未接入 DialogueService/provider/Godot，未实现记住/忘记命令、应用检索或 Step 3，未修改公开契约、依赖、CI，未读取 `.env` / API key、调用真实模型、提交、推送或进入 R-06。

## Step 3 已批准执行与完成事实

- 开始前只读复核分支仍为 `feat/f-005-long-term-memory-retrieval-evaluation`，HEAD / `main` / `origin/main` 均为 `3e03d64d129871495f3fe73295ee9b11478f2e71`；Step 0—2 的 11 项 tracked 修改和 6 个新增文件完整保留，项目 `data/` 不存在。
- 先新增显式命令、TTL、容量、version、tombstone、事务、重启和幂等专项测试；首次执行因 `cyber_town.application.long_term_memory` 尚不存在产生 `1 error during collection`，确认失败测试先于实现。
- 独立 `LongTermMemoryService` 只接受已冻结的中英文记住/永久记住/忘记模板和 4 个白名单事实；显式命令返回现有 `DialogueResponseV1`、`completed / local-memory`，普通消息返回未处理，不调用 provider，不暴露 fact value。
- 标准库 SQLite 使用 `(player_id, npc_id)` 双元 scope 和 `BEGIN IMMEDIATE` 原子完成：幂等 request fingerprint 校验、30 天过期或显式永久、64/4096 活跃容量、同 ID/version 更新、遗忘正文清空、无正文事件及 operation 落库。
- 验证新 conversation 与 repository 重启、跨 player/NPC 隔离、30 天整点边界、过期事务 rollback、遗忘后重新记住、容量满时不驱逐、Retry/replay、同 request 不同 payload 409、并发重复请求和并发不同请求串行。
- Step 3 新增应用专项 `69 passed`；领域 + repository + 应用长期记忆专项共 `199 passed`，既有配置 `277 passed`；统一 fake-only 质量入口 `918 passed`，ruff、mypy 49 files、lock 45 packages、Schema、9 个健康 loopback、10 个 fake 对话 loopback、ignore/sensitive 均通过。
- 所有 SQLite 数据仍只由 pytest `tmp_path` 创建；未创建项目 `data/`、正式/UAT 数据库或调用台账，未接入 FastAPI/DialogueService/provider/Godot，未实现确定性检索、事实注入、上下文预算改动或 Step 4；未读取 `.env` / API key、调用真实模型、提交、推送或进入 R-06。

## Step 4 已批准执行与完成事实

- 开始前功能分支、HEAD / `main` / `origin/main` 和既有 Step 0—3 文件范围均未漂移，项目 `data/` 不存在；新增检索、HTTP/Godot 联调及 adapter 专项首次运行产生 `3 errors during collection`，证明统一上下文选择器、长期检索器与 provider-neutral 事实 DTO 均尚未实现。
- SQLite 参数化查询只读取同 `(player_id, npc_id)`、`active`、未过期且 `confidence > 0` 的事实；应用层采用精确 fact key 优先、固定中英文别名及 importance/confidence/updated_at/memory_id 确定性排序，最多返回 4 条，跨 player/NPC、已遗忘、已过期和零 confidence 均不可召回。
- 不可变 `ProviderLongTermFact` 复用白名单事实验证、隐藏正文 `repr`、拒绝角色伪装/重复事实并以 `UNTRUSTED_LONG_TERM_MEMORY` 标记为 user 数据；现有 DeepSeek adapter 仅使用 SDK stub 验证消息顺序为唯一 Nia system → 长期事实 user → 完整短期 user/assistant → 当前 user，没有真实网络调用。
- 继续固定总预算 8192、长期事实预算 2048、回复预留 256 和 UTF-8 字节/固定结构开销；优先保留 persona、当前问题与回复额度，再按整条事实和最新完整短期回合裁剪，不把工程估算冒充 provider token。
- 现有 `POST /api/v1/dialogue` 已接入显式记住/忘记与 FakeProvider 查询；覆盖跨 conversation、player 隔离、更新不复活旧值、服务重启后恢复及无记忆诚实回答；管理命令使用 `completed / local-memory` 且不调用 provider。
- 真实 Godot headless 使用既有生产对话场景，通过本地 FastAPI、pytest 隔离 SQLite 和 FakeProvider 完成记住 → 召回 → 忘记 → 明确不知道；联调额外发现并以失败优先负例修复“同会话遗忘后旧短期历史复活事实”，忘记后即使当前 conversation 保留历史也不会再次调用 provider 或泄漏旧值。
- 全部长期记忆领域/repository/应用/检索/HTTP/Godot 专项 `254 passed`，既有配置 `277 passed`；最终统一 fake-only 质量入口 `975 passed`，ruff、mypy 51 files、lock 45 packages、Schema、Godot import/unit、9 个健康 + 10 个既有对话 loopback、ignore/sensitive 均通过。
- 所有 SQLite 数据仍只由 pytest `tmp_path` 创建；未创建项目 `data/`、正式/UAT 数据库或调用台账，未修改公开 Dialogue v1/Schema、Godot 生产场景、依赖或 CI；未读取 `.env` / API key、调用真实模型、提交、推送或进入 Step 5/R-06。

## Step 5 已批准离线评估与真实 DeepSeek 专项验收

- 用户先批准 Step 5 的 fixed golden set、跨进程预算台账、FakeProvider 联调和必要当前事实文档，随后另外明确授权真实 DeepSeek、现有 Settings 读取 Git 忽略 `.env`、外部网络及最多 8 次/USD 0.035；不复用其他任务或 Step 7 授权。
- 先新增 golden set 和 SQLite 调用台账失败优先专项，首次执行产生 `2 errors during collection`，分别证明 `long_term_evaluation` 和 `acceptance_ledger` 模块缺失；随后为 usage 先落账的计量 provider 另增专项，首次产生 `1 error during collection`。
- 新增版本化 `f-005-v1` 固定 72 项 synthetic golden set，覆盖四类白名单 fact keys、精确 key、固定中英文别名、跨 player/NPC、更新、遗忘、过期、空结果及无关问题；结果 precision `1.00`、recall `1.00`，scope 泄漏、遗忘/过期召回、旧值复活与空结果虚构均为 `0`；纯短期跨 conversation baseline recall 为 `0.00`。
- 新增标准库 SQLite metadata-only 跨进程 acceptance ledger，自动测试只使用 pytest 隔离路径，真实专项使用受 Git 忽略的 `data/acceptance-ledgers/f-005.sqlite3`；Step 5 限 8 次/USD 0.035，Step 7 限 4 次/USD 0.015，总计 12 次/USD 0.05；`BEGIN IMMEDIATE` 在 provider 调用前原子预留次数和整数 micro-USD，`reserved/unknown`、模型漂移、费用超额、锁冲突和数据库损坏 fail-closed。
- 新增 provider-neutral `MeteredAcceptanceProvider`，FakeProvider 专项证明先持久化授权 reservation，再调用 provider，completion 返回后先落 prompt/completion tokens 与 micro-USD，然后才允许调用方进行语义断言；外部失败保留 `unknown`，后续跨进程调用不可绕过。
- golden + ledger + 计量 provider 专项共 `59 passed`；最终统一 fake-only 门禁 `1034 passed`，ruff、mypy 57 files、lock 45 packages、Schema、Godot import/unit、9 个健康 + 10 个既有对话 loopback、ignore/sensitive 全通过。
- 用户专项批准后，现有 Settings 只在验收进程启用冻结的 `deepseek-v4-flash`，使用 `data/uat/f-005/step-5-real-20260825/cyber-town.sqlite3` 隔离数据库和 `data/acceptance-ledgers/f-005.sqlite3` 正式 metadata-only 台账；`data/cyber-town.sqlite3` 正式业务数据库未创建。
- 真实 FastAPI → DialogueService → DeepSeek 专项验证跨 conversation 召回、repository/service 重建后恢复、不同 player 零泄漏、更新值替换、四类批准 fact keys、Nia persona 优先、遗忘后同 conversation 不复活及空结果诚实 unknown；显式记住/忘记、跨 scope 拒绝和空结果均零 provider 调用。
- Step 5 实际真实调用 `7 / 8`，prompt tokens `1244`、completion tokens `106`；按已冻结峰值 cache-miss 单价逐次向上取整的保守台账费用为 `690 micro-USD / USD 0.000690`，低于 `USD 0.035`；所有请求先原子预留、返回后先落 usage，未结算 reservation 为 `0`。
- 验收进程首次初始化因继承的 SOCKS `ALL_PROXY` 与既定 SDK 依赖不兼容而停止；此时台账调用/费用均为 `0`。随后仅在当前验收子进程移除该变量、保留 HTTP/HTTPS 代理；未安装依赖、未修改系统配置或 `.env`。
- Step 5 已完成；独立 QA、用户真实窗口 UAT、Git 交付、后续真实模型调用和 R-06 均未授权或执行。

## Step 6 独立 QA 首轮阻塞结论

- 用户随后授权 Step 6 独立 QA；两名未参与 F-005 实现的 reviewer 分别依据任务卡审阅后端 SQLite/事务/幂等/调用预算与 FastAPI/Godot/评估 oracle，全部复现使用纯内存 SQLite、现有隔离 pytest 数据库或 FakeProvider；未读取 `.env`、未调用真实模型、未修改实现。
- **P1：默认启动未装配长期记忆。** `api/__main__.py` 调用 `build_dialogue_service(settings)` 时没有注入 repository，`api/composition.py` 因默认 `long_term_repository=None` 不启用任何长期记忆；显式记住命令反而进入 provider，正常用户无法持久化或跨会话召回。
- **P1：记忆更新后旧值通过短期历史复活。** 同 conversation 先召回旧值再更新时，新长期事实与携带旧值的 assistant 历史同时发送给 provider；FakeProvider 可把已替换旧值重新返回玩家。
- **P1：跨普通对话/记忆管理的 request_id 冲突绕过 409。** 同一 request_id 在两类执行路径之间复用不同 payload 时，双向均返回 HTTP 200，分别产生额外 provider 调用或持久化写入。
- **P1：零 token/零费用被当作有效调用结算。** 计量 provider 与 acceptance ledger 接受 prompt/completion/费用均为 0 的完成结果，将已发生调用标记 completed，破坏冻结 usage/费用治理。
- **P1：低敏感话题白名单不足。** `favorite_cyber_town_topic` 接受任务卡禁止的非话题数据和变体角色/指令式内容；两名 reviewer 对同一输入校验根因的发现合并计数，不重复记 P2。
- **P2：跨 scope 过期状态和事件归属污染。** 某 player/NPC 的写操作清理全部 scope 的过期事实，并把当前请求标识记录到其他 scope 的 expired 事件。
- **P2：golden evaluator 接受全负例退化集。** 60 个无正例、零召回的合法 case 仍产生 precision=recall=1.0 且 passes=true；短期 baseline 固定为 0，并非实际测量。
- **P2：遗忘抑制的第二次 SQLite 查询错误映射。** `is_suppressed_recall()` 的存储异常漏过统一捕获，实际返回 HTTP 500 / `internal_error` / 不可重试，而任务卡要求 HTTP 503 / `provider_unavailable` / 可重试。
- 首轮后端专项 `661 passed`、独立 Godot/API 专项 `92 passed` 及补充 `175 passed / 1 deselected`；当时统一 fake-only 质量入口为 `1034 passed`，但未覆盖上述独立组合负例，因此首轮结论为 **BLOCKED / 5 P1 / 3 P2**。
- 正式 Step 5 acceptance ledger 保持 `7` 次、`1244 / 106` tokens、`690 micro-USD`、`pending=0`；本轮独立 QA 新增真实调用和费用均为 `0`。

## Step 6 已授权失败优先修复、独立复审与运行时文件处置

- 首轮 5 项 P1、3 项 P2 对应组合负例先失败，再修复默认启动 SQLite 装配、跨普通/管理请求及重启的指纹幂等、正数 usage 结算、低敏感中英文话题许可词汇、仅本 scope 过期、不可退化 golden oracle 和存储异常 503 映射。
- 独立复审追加覆盖更新/遗忘后的同 owner 跨 conversation 旧值、NFKC/casefold 变体、在途 provider 结果和已完成幂等缓存；事实变更按双元 scope 递增代次、清除所有包含旧值的完整短期回合，旧缓存 replay 返回 409；其他 owner 不受影响。
- 已持久化的 Remember/Forget operation 在服务重启后 replay 不触发伪变更、不清理有效新值历史，也不中断合法在途请求；同 request ID 不同 payload 仍返回 409。对应独立追加负例先得 `5 failed`，扩展后 `8 passed`。
- 默认启动链路使用 FakeProvider、pytest 隔离 SQLite 与真实 FastAPI/Godot loopback 回归；当前完整统一 fake-only 门禁 `1095 passed`，ruff、mypy 57 files、lock 45、Schema、Godot unit/import、9 健康 + 10 对话 loopback、ignore/sensitive 全通过。
- 修复默认启动装配后，旧 fake-provider 测试此前只隔离工作目录、未隔离项目根，曾误创建受 Git 忽略的 `data/cyber-town.sqlite3`；已改为 monkeypatch 项目根到 pytest `tmp_path` 并增加默认路径隔离负例。用户随后明确授权仅定向删除该 `53248` 字节文件；删除前只核对精确绝对路径与元数据，未读取内容，未删除其他文件，Step 5 隔离验收库与真实调用台账完整保留。
- 真实台账保持 `7` 次、`1244 / 106` tokens、`USD 0.000690`、pending `0`；本轮未读取 `.env`/API key，未调用真实模型，未进入 Step 7/R-06。

## 验收标准与完成定义

1. Given 已批准白名单事实，when 显式记住后新建 conversation 或重启服务，then Nia 仅在同 player/NPC scope 正确召回。
2. Given 不同 player 或 NPC，when 检索同名 fact key，then 不存在跨 scope 泄漏。
3. Given 已更新、过期或明确遗忘的事实，when 请求召回，then 只使用新值或确定性回答不知道。
4. Given 同一 request 的 Retry/replay/concurrency，when 命令成功提交，then SQLite 只产生一次逻辑写入且不重复递增 version。
5. Given provider 失败、取消、degraded、非法内容或晚到结果，when 请求结束，then 不产生长期事实。
6. Given 长短期上下文超额，when 构造 provider request，then persona 唯一 system、回复预留 256、总预算 ≤ 8192，且只裁剪完整事实/回合。
7. Given 60 项固定 golden set，when fake-only 评估，then precision ≥ 0.95、recall ≥ 0.90，泄漏、旧值、删除复活和虚构均为 0。
8. Given SQLite 损坏、路径逃逸、事务失败或锁超时，when 请求处理，then fail-closed，不泄漏内部细节，也不删除或覆盖用户数据库。
9. Given 获独立批准的真实评估或用户 UAT，when provider 调用完成，then 先持久化脱敏 usage，跨进程总调用 ≤ 12 次且费用 ≤ USD 0.05。
10. 只有独立 QA、用户 Godot UAT、fake-only 全量门禁、文档一致性与单独授权的 Git/PR/CI/归档全部完成后，才可宣布 F-005 完成。

## 风险、回滚与停止条件

主要风险：跨 player/NPC 泄漏、旧值复活、SQLite 锁阻塞、提交后响应丢失、Retry 重复写、事实注入 persona、预算低估、运行时数据入 Git 和跨进程真实调用超额。

正式 SQLite 数据属于用户状态，回滚默认保留数据库、停止长期记忆能力并人工检查；migration 只向前版本化，备份/恢复只在临时测试库验证，删除/覆盖/重建正式数据必须另获明确授权。

出现基线漂移、需要修改公开契约/Godot/依赖/CI、需要访问真实 `.env`、新增 Qdrant、scope 泄漏、删除复活、调用 usage 缺失、P1/P2 或任一门禁失败时停止，不自动扩展 Step 或进入 R-06。

## Step 7 用户 UAT 与本地交付门禁完成证据

- 用户亲自在真实 Godot 窗口使用 `data/uat/f-005/step-7-user-20260825/cyber-town.sqlite3` 完成验收：初始 unknown、显式记住 `game_alias`、新窗口召回、停止并重启后端后召回、更新替换、明确遗忘和最终 unknown 均符合预期；管理命令与空结果未调用 provider。
- 跨进程台账只读核对为 Step 7 `3` 次、`500 / 141` tokens、`408 micro-USD / USD 0.000408`、pending `0`；F-005 累计 `10` 次、`1744 / 247` tokens、`USD 0.001098`、pending `0`，低于 4/12 次和 USD 0.015/0.05 上限。
- UAT 后 `PORT_8000_STOPPED=YES`、`FORMAL_DATABASE_CREATED=NO`；隔离 UAT 数据库与 metadata-only 台账均受 Git ignore，不读取或记录 API key、原始消息或模型回复。
- 最终 fake-only 统一入口 `1095 passed`，既定 lock、ruff、mypy、Schema、Godot、loopback、ignore/sensitive 与 diff 门禁全部通过；当前已达到 `ready_for_git_delivery`。

当前唯一下一动作：等待用户另行授权 F-005 Git 交付；不得自动提交、推送、创建 PR、归档或进入 R-06。
