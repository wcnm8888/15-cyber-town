# 任务卡：F-008 可观测性与 Agent 评估

状态：`archived / delivered / 2026-08-26`。

来源：已批准路线图的 `R-09`。用户已于 2026-08-26 批准并完成 Step 0—7、restart-recovery P1 最小修复、独立 fake-only QA、用户 Godot/CLI UAT 与最终本地门禁。四个可二分功能提交经 PR #11 的 GitHub Linux `quality` 通过后 squash merge 为 `c78f1c190bd3a3753e849aa7da76c88dbf5c27b2`；本任务卡随后由 PR #12 归档。

## 用户目标与可见价值

开发者能够只凭稳定的 `request_id`、`trace_id` 和脱敏元数据，定位一次玩家与固定 NPC 对话经过了哪些阶段、在哪个边界降级或失败、是否命中重放、是否调用 provider，以及短期记忆、长期记忆和关系系统是否按正确 scope 工作。同时，项目具备可重复的 fake-only Agent 评估基线，后续 R-10 的安全、成本与性能优化可以用数据比较，而不是凭感觉调整。

本任务不改变玩家对话体验。Godot 继续只展示既有 `trace_id`；不新增正式监控页面、原文日志或真实模型评估。

## 当前基线与前置事实

- 正式基线为 `main == origin/main == 742317ca560f01fc2e4a7f1e73ebb2a6096af37f`；F-001—F-007 已交付并归档，当前没有活动实现任务。
- 现有 Dialogue v1 已由 Godot 生成客户端 `request_id`，FastAPI 为每次 HTTP 尝试生成独立 `trace_id`；同一逻辑请求的 retry/replay 可共享 `request_id`，但必须拥有不同 `trace_id`。
- 现有 `DialogueService` 已产生 metadata-only 成功/失败审计，包含部分 persona、provider、结果、延迟、usage、字符数与缓存字段，但该信息只进入日志，没有统一阶段模型、持久查询、保留策略或回放索引。
- 短期状态按 `player_id + npc_id + conversation_id` 隔离；长期记忆与关系按 `player_id + npc_id` 隔离。固定 persona 为 `neon_guide / Nia`、`signal_archivist / Ivo`、`night_courier / Rhea`。
- 现有业务 SQLite 迁移为不可变 `0001_long_term_memory.sql` 与 `0002_relationship_state.sql`。F-005 的验收数据库、真实调用台账和预算不属于 F-008，禁止读取、修改、删除或复用。
- 自动化统一入口永久禁用 dotenv、清除 provider key 并使用 fake/disabled provider；F-008 延续该边界。

## Step 0 已锁定范围与决策

用户已于 2026-08-26 确认以下方案。它们构成 Step 1 的冻结输入，任何改变均须先更新任务卡并重新取得授权：

1. **独立 observability 存储。**新增独立、默认关闭的 metadata-only SQLite 真相源 `data/cyber-town-observability.sqlite3`，迁移路径固定为 `backend/src/cyber_town/infrastructure/observability/migrations/0001_observability.sql`；不向现有业务迁移列表追加 `0003`，不修改 `0001`/`0002`，不与长期记忆、关系或 F-005 验收台账共库。自动化只能注入隔离临时路径，绝不得创建正式路径数据库。
2. **只读开发者查询。**提供本地 CLI `scripts/observability_report.py`，支持按 `trace_id`、`request_id`、时间窗口、结果码、persona version 与脱敏 scope tag 查询严格 JSON/文本摘要；SQLite 必须以只读模式打开，不新增公开 HTTP API，不修改 Dialogue v1，不提供任意 SQL、原文或数据库导出。
3. **稳定脱敏 scope tag。**用带字段名与 schema version 领域分隔的 HMAC-SHA-256 派生 `player_scope_tag`、`npc_scope_tag`、`conversation_scope_tag`。密钥通过 composition 依赖注入，不从 `.env` 读取、不写入 SQLite/日志；自动化与 UAT 仅使用公开 synthetic key。F-008 不解决真实环境密钥托管，真实采集保持关闭。
4. **每次尝试独立记录。**`trace_id` 标识一次 HTTP 尝试，`request_id` 标识逻辑请求；新增内部 `execution_id` 关联共享的 in-flight/provider 执行。cache replay、手动 retry、并发重复请求分别保留自己的 trace，且必须准确记录 `provider_dispatch_count = 0/1`，不得把重放误算成额外调用。
5. **持久 replay 只索引、不保存 payload。**本地 trace 的 replay index 只能保存 trace/request/execution 关联、fixture/case ID、schema/rule/persona version、结果码和摘要 digest；没有原始输入的 trace 明确标记为 `metadata_only_not_executable`。可执行回放只允许引用仓库内版本化 synthetic fixture，不得从真实 trace 重建 prompt、回复或记忆。
6. **Godot 最小契约。**Godot 继续显示既有 `Trace: <uuid>`，不增加监控 UI、上报 endpoint 或持久日志。Godot → FastAPI 的关联由既有 request payload、响应 trace 和 generation/旧回调测试证明；客户端 generation 只作为进程内测试状态，不写入服务端数据库。

## 端到端可观测性契约

### 身份与关联字段

- `schema_version`、`trace_id`、`request_id`、内部 `execution_id`、`attempt_kind`。
- `player_scope_tag`、`npc_scope_tag`、`conversation_scope_tag`；只保存固定长度 tag，不保存原始 scope 字符串。
- `persona_version` 与受限 `provider_kind`；未知值必须拒绝或映射到固定 `unknown`，不得把 provider 原始对象转成字符串落盘。
- `started_at_utc`、`finished_at_utc`、`record_status`、`terminal_outcome`、`error_code`、`retryable`、`degradation_reason`。
- `total_latency_ms`、`provider_wait_ms`、`provider_latency_ms`、上下文工程预算、选中短期回合数、选中长期事实数、输入/输出字符数、prompt/completion/total token 与 `cost_micro_usd`。fake/local/disabled 路径成本固定为 0；F-008 不引用 F-005 预算或台账。
- `idempotency_outcome`、`from_cache`、`provider_dispatch_count`、`short_term_outcome`、`long_term_outcome`、`relationship_outcome` 和规则/fixture/evaluator 版本。

### 固定阶段 allowlist

固定阶段为：

1. `http_received`
2. `request_validation`
3. `persona_resolution`
4. `idempotency_resolution`
5. `scope_lock`
6. `short_term_selection`
7. `long_term_retrieval`
8. `context_budget_selection`
9. `provider_queue`
10. `provider_completion`
11. `relationship_evaluation`
12. `state_commit`
13. `response_mapping`
14. `terminal`

每个阶段事件只允许保存开始/结束时间、结果 enum、计数、耗时和稳定 reason code。未经过的阶段必须显式标记 `not_reached` 或不产生事件，不得伪造成功。非法请求可能没有可用 request/scope 字段，此时只保存 trace、固定错误码和 `null` tag，绝不保存请求 body。

### 终态与边界

- 终态固定为 `completed`、`degraded`、`rejected`、`failed`、`cancelled`、`orphaned`、`replayed`、`conflict` 和 `abandoned_after_restart`。
- 正常存储条件下，每个进入 Dialogue HTTP 边界的尝试必须恰有一条 trace summary；进程崩溃留下的 open trace 在下一次启动时只能收口为 `abandoned_after_restart`，不得推断 provider 或持久化成功。
- 同 request 的 cache replay、新 waiter、手动 retry 和跨 scope 冲突必须产生不同 trace；只有实际共享 provider 执行的记录可共享 `execution_id`。
- 取消、迟到结果与旧 generation 不得增加 provider 调用计数、重复记忆/关系写入或把旧 NPC 状态归给当前 NPC。
- observability 写入失败不得改变既有 Dialogue v1 成功/失败语义，也不得触发额外 provider、记忆或关系写入；它只能产生固定的 metadata-only 诊断并将评估门禁判为失败。schema、脱敏或 allowlist 校验失败必须拒绝该记录，禁止降级为原始字符串日志。

## 严禁记录的内容

以下字段不得出现在 trace SQLite、普通日志、评估结果、回放索引、CLI 输出、异常文本或测试报告中：

- 玩家原始 `message`、模型 `reply`、persona `system_prompt`、完整短期 history。
- 长期记忆 topic/key/value、召回正文、忘记前旧值或任何可恢复原文的片段。
- 原始关系 suggestion、provider response/body、reasoning content、tool call 参数。
- API key、token、cookie、authorization header、`.env` 内容、SDK repr、原始异常和 stack 中的敏感 payload。
- 原始 `player_id`、`npc_id`、`conversation_id`；公开 `request_id` 与 `trace_id` 仅用于关联，不得与原文同表保存。

允许的字符串必须来自版本化 enum/allowlist，或是 UUID、固定长度 HMAC tag、SHA-256 digest。测试必须使用唯一 sentinel 扫描数据库、日志和 CLI 输出，证明禁止原文记录数为 0。

## 已锁定 SQLite、保留与访问契约

### 逻辑数据结构

- `trace_runs`：每次 HTTP 尝试的一条 summary，`trace_id` 唯一。
- `trace_stage_events`：固定阶段、顺序、耗时、结果和 reason code；外键指向 trace。
- `execution_links`：一个实际 provider/本地执行与一个或多个 trace 的关联，支持并发 waiter 和 replay 计数。
- `evaluation_runs`：evaluator/fixture/schema/rule/persona 版本、开始结束时间、聚合指标和 canonical digest。
- `evaluation_cases`：case ID、类别、预期/实际结果码、pass/fail、固定 failure code 与数值指标；不保存 fixture 原文。
- `replay_index`：synthetic fixture ID、trace/request/execution ID、版本和摘要 digest；真实 metadata-only trace 不可执行回放。

所有表必须使用严格约束、外键、允许值检查、固定长度上限和明确索引。查询参数必须有数量/时间上限，默认只读；CLI 不提供任意 SQL、全文搜索或原文导出。

### 保留策略

- trace summary、stage event、execution link 和 replay index：保留 7 天或最近 10,000 个 trace，先到者只标记到期并触发用户可见的处置报告，不自动删除。
- evaluation run/case：保留 30 天或最近 50 次运行；版本化基线摘要可进入项目 evidence，但不得复制 case 原文。
- 清理只允许处理已终态且不属于在途运行的记录；按外键事务处理，失败 rollback。Step 0 未授权自动清理，也未授权 `purge --before` 或数据库整体回收；任何删除均须重新列出到期资源、影响和可恢复性，并取得单独明确授权。
- 访问限制为本机开发者、只读 CLI 与注入的测试 repository。无网络监听、无外部 telemetry、无上传或云同步。

## fake-only Agent 评估框架

### 固定评估维度

| 维度 | 候选验证 |
| --- | --- |
| persona 身份 | Nia/Ivo/Rhea 的 npc tag、persona version、FakeProvider 捕获 system prompt 与当前 registry 严格对应；未知 NPC 在 provider/持久化前失败 |
| 回复结构与降级 | completed/degraded/error 的冻结状态、provider kind、reason code、usage 和 trace 阶段一致；不以 fake 文案宣称真实语义质量 |
| 短期隔离 | `player × npc × conversation` 任一维变化零历史泄漏；同 scope 只保留既有成功完整回合 |
| 长期/关系隔离 | `player × npc` 跨 conversation 保留、跨 player/NPC 零泄漏；关系建议只记录确定性结果码，不记原文 |
| 对抗输入 | 未知/大小写/路径/控制字符/同形字 NPC、scope 篡改、重复 JSON、提示注入与恶意 suggestion 全部在 provider/写入前 fail-closed |
| 幂等/并发 | 同 scope replay、共享 waiter、跨 scope request 冲突、跨 NPC 并发、同 scope 串行均准确归属执行和调用次数 |
| 取消/迟到 | cancel、orphan、旧 generation 与迟到结果不污染当前 scope，不重复提交，trace 终态可解释 |
| 重启/回放 | 同一隔离 observability SQLite 重建应用；open trace 安全收口，synthetic fixture 可按 case ID 重放，真实 metadata trace 不可恢复原文 |

评估 fixture 必须版本化、synthetic、无真实用户信息，并复用 FakeProvider 和隔离 SQLite。主观 persona/回复质量只允许使用明确的结构化 rubric 与固定预期码；F-008 不用 fake 结果冒充真实模型能力。

### 评估输出

- 每次运行产生版本、case 数、pass/fail、失败码、各维度计数、trace 完整率、泄漏数、禁止原文命中数、provider 调用归属率、延迟分位数和 canonical digest。
- 相同 fixture、版本和 synthetic key 在至少 3 个全新进程中，排除时间戳与本机耗时后，case verdict、计数和 canonical digest 必须完全一致。
- 性能报告至少给出无 recorder 与 SQLite recorder 两组 fake-only 样本的 p50/p95/p99、吞吐和数据库增长量。F-008 只建立测量基线，不在未批准前冻结 R-10 的性能优化阈值。

## 明确验收标准

| 门禁 | 必须结果 |
| --- | --- |
| trace 关联完整率 | 健康 recorder 下，所有 Dialogue HTTP 尝试均有且仅有一条 summary；终态或显式 crash-recovery 记录合计 `100%` |
| 阶段一致性 | 所有固定 stage 顺序、可达性、终态和计数不变量通过率 `100%` |
| 敏感原文 | SQLite、日志、CLI、评估结果和回放索引中的禁止原文命中数 `0` |
| scope 泄漏 | 短期三元 scope、长期/关系双元 scope 及跨 restart 的泄漏数 `0` |
| provider/cost 归属 | 实际 FakeProvider 调用与 execution 一一对应；replay/retry/cancel 不重复计数，错误归属数 `0`；成本恒为 `0` |
| 可重复评估 | 3 个全新进程的固定 case verdict、聚合计数和 canonical digest 完全一致 |
| 对抗与失败 | 非法 NPC/scope/JSON/suggestion 在 provider 和状态写入前失败；observability 故障不改变 Dialogue v1 响应或业务写入 |
| 重启与回放 | open trace 只收口为 abandoned；synthetic fixture 可按 ID 重放；真实 metadata trace 恢复原文的数量 `0` |
| Godot | 既有 trace 显示、三个 NPC 切换、retry、快速切换和旧 generation 抑制不回归；不增加新 UI |
| 质量入口 | 定向测试、ruff、format check、mypy、schema、Godot import/unit、既有全部 loopback、完整 fake-only `scripts/quality.py`、`git diff --check`、ignore/sensitive 检查和 GitHub CI 全绿 |

## 明确非目标

- 不实施 R-10 的提示注入防护产品策略、正式限流、真实预算、自动 retry、熔断、压测优化或生产安全加固。
- 不做 R-08 的 NPC 自主行为、NPC—NPC 对话、多 Agent 调度或社交图谱。
- 不新增正式游戏 UI、监控面板、像素素材、动画、Figma 设计、部署或发布。
- 不接 OpenTelemetry collector、Prometheus、Grafana、Sentry、云 telemetry、第三方 SaaS、外部数据库、Qdrant 或网络导出。
- 不读取 `.env`、不调用真实模型、不开展真实模型 rubric、不产生真实费用。
- 不修改 `DialogueRequestV1`、`DialogueResponseV1`、`ApiErrorV1` 或其 JSON Schema；不新增 Dialogue v2。
- 不读取、修改、迁移、清理或复用 F-005 的验收数据库、调用台账和预算。
- 不保存可用于重建真实 prompt、回复、记忆或关系 suggestion 的 payload、片段、embedding 或可逆编码。

## Step 0—7 地图

| Step | 内容 | 当前状态与停止点 |
| --- | --- | --- |
| 0 | 只读核对基线；锁定 trace/schema、脱敏、独立 SQLite、保留/清理、CLI、回放与临时资源决策 | `complete` |
| 1 | 失败优先建立 metadata schema、enum、HMAC scope tag、recorder protocol 与禁止原文测试 | `complete` |
| 2 | 接入 FastAPI、DialogueService、provider、短期/长期/关系阶段 instrumentation | `complete` |
| 3 | 建立版本化 fake-only evaluator、固定 fixture、指标与三进程可重复基线 | `complete` |
| 4 | 实现独立 SQLite migration/repository、只读 CLI、retention 到期标记与 metadata-only replay index | `complete` |
| 5 | fake-only 综合矩阵、对抗、故障注入、性能基线、重启和回放验证 | `complete`；P1 已修复，误生成的 2 个 synthetic `.env` 与 1 个 `.env.example` 已经用户精确授权后清理并复核 |
| 6 | 独立 fake-only QA，重新设计黑盒场景并执行完整门禁 | `complete`；无未关闭产品缺陷，完整 fake-only 门禁通过 |
| 7 | 用户本地开发者查询/Godot trace UAT、最终 fake-only 门禁与 Git 交付准备 | `complete`；无未关闭缺陷，Git 提交/推送/PR/合并仍需单独授权 |

推荐功能分支：`feat/f-008-observability-agent-evaluation`。

## Step 0 只读基线证据与冲突裁决

- **Git 基线。**未 fetch 或访问远端服务；只读确认本地 `HEAD`、`main` 与现有 `origin/main` 引用均为 `742317ca560f01fc2e4a7f1e73ebb2a6096af37f`，upstream 为 `origin/main`，本地 `main` 是现有 `origin/main` 的祖先。仅 `docs/project-management/current-task.md` 有未提交文档差异，当前只有正式 `15-cyber-town` worktree。
- **现有 trace。**`api/dialogue.py` 已在每次 HTTP 尝试中用 `uuid4()` 生成并复用 request-state `trace_id`；成功与所有安全错误响应均保留该 UUID。校验失败发生在 application service 前，因此该路径没有可信 `request_id` 或 scope；F-008 锁定为只记录 trace、固定错误码和空 scope tag，绝不读取或保存原始 body。
- **现有审计与 usage。**`DialogueService` 的成功/失败日志已记录 request/trace、npc、persona、provider/model、结果、缓存、延迟、token 和字符计数，但没有持久 store、阶段事件或查询入口。`ProviderUsage` 只有非负 prompt/completion/total token，没有费用字段；F-008 的 fake/local/disabled `cost_micro_usd` 固定为 0，不接入或推导 F-005 预算。
- **重放与并发。**现有同 request 并发 waiter 和 completed replay 各自返回新的 `trace_id`，但可共享一次 provider task；因此多个 trace 不能被误当作多次模型执行。独立 `execution_id` 与 `provider_dispatch_count` 已锁定为必要关联层。
- **scope。**源码确认短期 `ConversationScope` 为 `player_id + npc_id + conversation_id`，长期 `LongTermMemoryScope` 与 `RelationshipScope` 均为 `player_id + npc_id`。F-008 只为这些已验证 scope 派生 HMAC tag，不改变所有权规则。
- **persona。**不可变 registry 只包含 `neon_guide / nia-v1`、`signal_archivist / ivo-v1`、`night_courier / rhea-v1`，且已有 ID/version/display-name 唯一性检查。F-008 记录 persona version 和脱敏 npc tag，不保存 system prompt。
- **业务 migration。**业务迁移列表仍精确为 `0001_long_term_memory.sql` 与 `0002_relationship_state.sql`；当前 SHA-256 分别为 `3d50bb6116de59b2d15293a50c7ed8bceddcdc567a413f43040d92b76eacf4a4` 与 `7751c9a990ed6825613e738601f4f07cf0affe5f937dfe0396be492edbb89c48`。F-008 独立 migration 不进入该列表。
- **既有评估。**项目已有版本化 synthetic 长期记忆 golden set，以及关系性质评估和多 NPC 隔离评估；它们可作为 F-008 evaluator 的只读参考，但 F-008 不修改或复用 F-005 验收数据库/台账/预算，也不把旧评估结果冒充新 trace 完整率证据。
- **CLI/存储缺口。**当前 `scripts/` 没有 observability 查询工具，infrastructure 也没有 observability migration/repository。正式 `data/cyber-town-observability.sqlite3`、计划的 F-008 worktree、QA 根目录与 UAT 根目录均不存在，证明 Step 0 未提前实现或创建资源。
- **可用性与完整率裁决。**“observability 故障不得改变 Dialogue v1”与“trace 完整率 100%”仅在健康 recorder 条件下同时成立。存储故障场景必须保持业务语义、拒绝原文 fallback，并让评估门禁明确失败；不得伪造已持久化 trace。
- **保留裁决。**7 天/10,000 trace 与 30 天/50 次评估是到期标记门槛，不是自动删除授权。达到门槛后继续按项目生命周期规则报告资源、影响与可恢复性，等待单独处置授权。

## 计划中的临时资源台账

候选任务卡起草和 Step 0 均未创建任何临时资源。若 Step 1 获准推进，以下资源仍须在实际创建前重新报告并取得相应授权：

| 规范化绝对路径 | 候选用途/内容 | 当前状态 | 候选期限与回收方式 |
| --- | --- | --- | --- |
| `E:\Agent\comprehensive-cases\15-cyber-town-f008` | F-008 / Step 1 Git worktree；创建于 `2026-08-26T06:17:16Z`；可能含源码、失败优先测试及 ignored Python 缓存，不得含 `.env`、真实密钥、原始对话或业务 SQLite | `active / created / owner=F-008-Step-1` | Git 交付完成前保留；另获授权后仅用普通 `git worktree remove`，不得 `--force`、递归删除或清理分支 |
| `E:\Agent\comprehensive-cases\15-cyber-town-f008\.ruff_cache` | ruff ignored 工具缓存；Step 6 结束时 5 个文件，5,698 bytes；不含任务 payload | `active / retained` | 随 F-008 worktree 保留至 Git 交付；如需提前清理须另获明确授权，不得递归删除其他内容 |
| `E:\Agent\comprehensive-cases\15-cyber-town-f008\.mypy_cache` | mypy ignored 工具缓存；Step 6 结束时 3 个文件，37,458,149 bytes，其中 `cache.db` 为 mypy 自身缓存，不是业务或 observability SQLite | `active / retained` | 随 F-008 worktree 保留至 Git 交付；如需提前清理须另获明确授权，不得递归删除其他内容 |
| `E:\Agent\comprehensive-cases\15-cyber-town-f008\.pytest_cache` | 既有 pytest ignored 缓存；Step 5 预检发现 5 个文件、81,081 bytes，最后修改早于本轮 Step 5；不含本轮 SQLite | `active / retained / discovered_at_step_5_preflight` | 随 worktree 保留并在 Git 交付清理申请中一并处置；本轮测试已禁用 cache provider，未修改该目录 |
| `E:\Agent\comprehensive-cases\15-cyber-town-f008\game\.godot` | Godot import ignored 缓存；Step 6 结束时 6 个文件、3,079 bytes | `active / retained` | 既有 Godot 质量入口会复用；随 worktree 保留至 Git 交付，清理须另获明确授权 |
| `E:\Agent\comprehensive-cases\15-cyber-town-f008\.venv` | Step 3 首轮误用 `uv run --no-sync` 自动创建的未装依赖虚拟环境外壳；删除前精确复核为 16 个文件、533,132 bytes，非 reparse | `deleted_with_explicit_authorization` | Step 4 开始时已仅删除该精确目录；worktree、源码、测试与两个工具缓存均保持完整，无后续处置 |
| `E:\Agent\cyber-town-f008-step2-tests` | Step 2 固定 pytest 根；删除前精确复核为 249 个文件、22,114,836 bytes，非 reparse 且父目录为 `E:\Agent` | `deleted_with_explicit_authorization` | 已仅删除授权精确目标，父目录、worktree、缓存与其他内容未触及，无后续处置 |
| `E:\Agent\cyber-town-f008-step3-tests` | Step 3 固定 pytest 根；删除前精确复核为 178 个 synthetic SQLite、16,072,704 bytes，非 reparse 且父目录为 `E:\Agent` | `deleted_with_explicit_authorization` | Step 4 开始时已仅删除授权精确目标；父目录、worktree、缓存及其他内容未触及，无后续处置 |
| `E:\Agent\cyber-town-f008-step4-tests` | Step 4 固定 pytest 根；删除前为 544 个文件、51,335,480 bytes，且非 reparse | `deleted_with_explicit_authorization` | 用户接受处置建议后已复核并仅删除精确目标；父目录、worktree 与缓存均未触及 |
| `E:\Agent\cyber-town-f008-step5-tests` | Step 5 固定 pytest 根；删除前包含 757 个文件、33,643,610 bytes，并含 14 个 synthetic 嵌套 Git 仓库 | `deleted_with_explicit_authorization` | 用户先授权包含嵌套仓库的精确根清理；普通递归删除受 read-only/hidden Git object 阻断后，用户再次按剩余 642 个文件、25,140,003 bytes 精确授权强制清理。执行代理拒绝 `-Force` 启动，故仅在目标内部去除受阻属性后普通递归删除；复核目标不存在，父目录、仓库、worktree、分支和缓存未受影响 |
| `C:\Users\24696\AppData\Local\Temp\pytest-of-24696\pytest-946` | 首轮误落 C 盘的 5 个 fake-only SQLite，共 450,560 bytes | `deleted_with_explicit_authorization` | 已核对非 reparse、精确父边界后删除；父目录与其他 pytest 目录保留，不需后续处置 |
| `E:\Agent\comprehensive-cases\15-cyber-town-f008\Agentcyber-town-f008-qafull-quality` | Step 6 首轮完整 pytest 因 Windows `PYTEST_ADDOPTS` 反斜杠解析而误建于 worktree 的 synthetic 根；685 个文件、25,918,593 bytes、945 个目录，含 300 SQLite、18 WAL/SHM、14 个 synthetic Git 仓库和 21 个 synthetic env-like 负向测试文件 | `deleted_with_explicit_authorization` | 发现后停止且未把敏感扫描 fail-closed 误判为产品缺陷；用户精确授权该唯一目标。执行代理拒绝直接 `Remove-Item -Force` 后，仅在目标内部去除受阻属性并普通递归删除；目标不存在、Git 状态恢复，无父目录或功能文件受影响 |
| `E:\Agent\cyber-town-f008-qa` | Step 6 独立 fake-only QA 根；删除前为 976 个文件、54,717,981 bytes、1,192 个目录，含 567 个隔离 SQLite、38 个 WAL/SHM、14 个 synthetic Git 仓库、21 个已预先授权的 synthetic env-like 负向测试文件、独立 QA/Godot metadata-only 报告和失败重试产物；reparse 为 0 | `deleted_with_explicit_authorization` | 用户明确授权本次由 Codex 删除。复核精确路径、父目录、全部 reparse 边界及 17 个 read-only/14 个 hidden 项后，仅在目标内部去除受阻属性并普通递归删除；目标已不存在，`E:\Agent`、正式仓库、功能 worktree、分支和缓存均完整。该删除不可恢复 |
| `E:\Agent\cyber-town-f008-uat` | F-008 Step 7 fake-only UAT 根；创建于 `2026-08-26T10:41:48Z`；删除前终盘为 4 files / 319,488 bytes，含隔离业务/observability SQLite 各 1 个及 1 WAL / 1 SHM；`.env*`、嵌套 Git、reparse、只读/隐藏项均为 0 | `deleted_by_user / verified_absent_before_git_delivery` | Git 交付预检只读确认目标不存在；本轮 Codex 未执行删除，父目录、worktree、源码和分支未受影响 |
| `E:\Agent\cyber-town-f008-step7-tests` | F-008 Step 7 最终门禁根；创建于 `2026-08-26T10:41:48Z`；删除前终盘为 695 files / 952 dirs / 26,533,019 bytes，含 303 SQLite、12 WAL、12 SHM、14 synthetic 嵌套 Git、3 个已授权配置负向测试 `.env*`、17 个只读文件、14 个隐藏项；reparse 为 0；嵌套仓库聚合为 0 tracked modified / 41 untracked / 0 ignored | `deleted_by_user / verified_absent_before_git_delivery` | Git 交付预检只读确认目标不存在；本轮 Codex 未执行删除，父目录、worktree、源码和分支未受影响 |

正式 `data/cyber-town-observability.sqlite3` 不得由自动化、QA 或 UAT 创建。日志、评估报告和性能摘要默认只写入脱敏 evidence；若需额外文件，必须先登记准确路径、内容类别、敏感性、期限和回收方式。

## Step 1 完成记录与停止状态

- **隔离基线。**预检确认正式目录仍为 `main`，`HEAD`、`main` 和现有 `origin/main` 均为 `742317ca560f01fc2e4a7f1e73ebb2a6096af37f`，唯一既有改动为本任务卡。随后按授权从 `origin/main` 建立 `feat/f-008-observability-agent-evaluation` 与独立 worktree；正式目录的文档改动未混入功能 worktree。
- **失败优先证据。**新增测试首次在收集阶段以 `ModuleNotFoundError: cyber_town.application.observability` 失败，证明生产模块尚不存在。实现后定向测试为 `39 passed in 0.11s`。
- **冻结契约。**新增不可变、slots、schema v1 的 `TraceMetadata`、`TraceStageMetadata` 与 `ScopeTags`；固定 trace stage、stage/terminal/record/idempotency、短期/长期/关系 outcome、provider kind、attempt kind 及稳定 reason/error code enum。metadata 仅允许 UUID 关联、HMAC scope tag、persona version、阶段/结果、UTC 时间、延迟、上下文计数、字符/token 与固定零成本字段。
- **scope 与关联。**HMAC-SHA-256 使用 `cyber-town:f008:scope:v1:<player|npc|conversation>\0` 领域分隔，拒绝空/短/错误类型 key 及空、带首尾空白、超过 64 字符或错误类型 identifier，输出固定 64 位小写十六进制。每次 HTTP 尝试拥有独立 `trace_id`；同一逻辑请求可共享 `request_id`；只有同一实际执行可共享 `execution_id`，且共享组只能有一个 provider dispatch owner。
- **recorder 与禁止原文。**建立 runtime-checkable recorder protocol、默认 no-op 与线程安全 in-memory fake recorder，均只接受冻结 DTO；未接 SQLite、composition 或请求链路。sentinel 负向测试确认原始 player/NPC/conversation ID、消息、回复、system prompt、记忆正文、关系建议、provider body 与 API key 均不出现在序列化、repr、日志、异常或 snapshot 中。
- **门禁。**定向 pytest `39 passed`；ruff check、ruff format check、mypy 与 `git diff --check` 全部通过。未创建 SQLite、日志、评估报告或本地服务；未修改 FastAPI、DialogueService、provider、记忆、关系、Godot、Dialogue v1/Schema、业务 migration、依赖、CI 或部署。
- **临时资源偏差。**运行前曾错误声明禁用缓存后不会创建额外持久资源；实际复核发现 `.ruff_cache` 与 `.mypy_cache`。二者属于用户已概括授权的 ignored Python 测试/工具缓存，但准确路径未在创建前报告。未删除、未掩盖，已在上表登记并保留。后续规则：运行任何工具前列出其默认缓存解析路径，运行后立即核对实际文件，不再仅依据命令行 flag 判断“不会创建缓存”。
- 全程未读取 `.env`、未调用真实模型或外部服务，未读取、修改或复用 F-005 验收数据库、调用台账和预算；未提交、推送或创建 PR。
- Step 1 当时停止于 `step_1_complete / awaiting_step_2_authorization`，后续仅在用户单独授权后进入 Step 2。

## Step 2 完成记录与停止状态

- **失败优先。**Step 2 新增集成测试首轮为 `9 failed, 39 passed`，失败集中在尚未存在的 recorder/composition 注入与 HTTP validation 记录接口；实现后专项最终为 `56 passed`。
- **链路接入。**默认 no-op、显式依赖注入的 metadata-only capture 已接入 FastAPI validation、DialogueService、persona/idempotency/scope lock、短期、长期、context budget、provider queue/completion、关系、state commit、response mapping 与 terminal。每个 HTTP 尝试保持独立 `trace_id`；cache replay 无 execution/dispatch；并发 waiter 只共享实际 `execution_id`；失败后 retry 获得新 execution。
- **结果与故障。**覆盖成功、未知 NPC、validation、provider timeout/unavailable/invalid response、content-filter/空历史降级、cache replay、retry、并发 waiter、取消/orphan/迟到结果、长期检索、关系应用/失败及短期 commit/abort。recorder 抛错时 Dialogue v1、422、provider 次数、关系写入次数和短期 commit 均不变且无重复。
- **隐私边界。**旧 dialogue audit 移除原始 `npc_id` 与 provider model，启用采集时只写三类 HMAC scope tag；原始 scope、message/reply、system prompt/history、记忆正文、关系 suggestion、provider body、异常详情和秘密在 DTO、stage、snapshot、repr、日志与异常中的 sentinel 命中数为 0。replay/waiter 的 token 与 provider latency 固定为 0，避免重复计量共享执行。
- **回归门禁。**最终相关 fake-only 回归 `614 passed`；Dialogue v1/contracts/schema/health `63 passed`；ruff、8 文件 format check、mypy、tracked `git diff --check` 与 3 个 untracked 文件 no-index whitespace 检查均通过。未修改 Dialogue v1/Schema、Godot、业务 migration、持久化、依赖、CI 或部署。
- **临时资源事故与处置。**一次既有回归在预检 fixture 不充分时误创建 C 盘 `pytest-946`；发现后立即停止、盘点并取得用户授权，随后仅删除精确目标。余下测试统一限制在获准的 E 盘固定根。该根现已到期但未删除，逐项盘点和建议见上表。
- 全程未读取 `.env`、未调用真实模型或外部服务，未读取、修改或复用 F-005 验收数据库、调用台账和预算；未创建 observability SQLite、日志、报告或本地服务，未提交、推送或创建 PR。
- 当前停止于 `step_2_complete / awaiting_step_3_authorization`；不得自动进入 Step 3。

## Step 3 完成记录与停止状态

- **失败优先与固定数据集。**新增 evaluator 测试首次因 `cyber_town.application.observability_evaluation` 不存在而在收集阶段失败；实现后定向 `14 passed`。仓库内 `f-008-observability-fixture-v1` 固定 24 个 metadata-only case、8 个维度与 Nia/Ivo/Rhea 三份 persona version/content digest，不保存 message、reply、system prompt、记忆正文、关系建议或 provider body。
- **不可变评估契约。**新增 frozen/slots evaluator DTO、固定 dimension/failure-code enum、严格 JSON 成员/重复键/版本/persona digest 校验，以及仅含版本、case verdict、完整率、一致性、泄漏/禁止内容/provider 归属/成本聚合与 canonical digest 的 allowlist 报告。任意 trace 缺失、阶段错序、scope 泄漏、禁止原文、provider 归属错误、非零成本或业务语义变化均以固定失败码拒绝。
- **阈值与可重复性。**24/24 case 通过；trace 关联完整率与 stage 一致性均为 `1,000,000 ppm (100%)`；scope 泄漏、禁止原文命中、provider 归属错误和非零成本 case 均为 0。三个全新 Python 进程使用同一 fixture 与 synthetic HMAC key，得到完全相同的 verdict/聚合与 digest `8266c2e4cc6b32a4525c5b36fffa63d94142d4fb80ea3b42f9fe358c94be81b4`。
- **回归与静态门禁。**Step 1—3 observability、persona、短期/长期/关系 scope、幂等、并发和取消相关回归 `614 passed`；全仓 ruff、严格 mypy `78 source files`、schema drift、tracked/untracked whitespace diff 与新增文件敏感信息扫描均通过。全仓 format check 仅报告 3 个既有且与 F-008 无关的基线文件；F-008 变更文件自身格式通过，未越界修改基线。
- **边界与资源。**未实现 observability SQLite/repository、查询 CLI、retention、replay index、性能基线、Godot、Dialogue v1/Schema、业务 migration、依赖、CI 或部署。Step 2 到期根已按本次明确授权精确删除；Step 3 根、worktree、两个工具缓存和误创建 `.venv` 外壳均已如实盘点并保留，处理建议见上表。
- 全程未读取 `.env`、未调用真实模型或外部服务，未读取、修改或复用 F-005 验收数据库、调用台账和预算；未创建 observability SQLite、日志、持久评估报告或本地服务，未提交、推送或创建 PR。
- 当前停止于 `step_3_complete / awaiting_step_4_authorization`；不得自动进入 Step 4。

## Step 4 完成记录与停止状态

- **失败优先与独立 migration。**Step 4 首轮因 `cyber_town.infrastructure.observability` 与 `scripts.observability_report` 不存在产生 2 个收集错误；实现后专项最终 `21 passed`。新增独立 `observability/0001_observability.sql`，只创建 STRICT `trace_runs`、`trace_stage_events`、`execution_links`、`evaluation_runs`、`evaluation_cases` 与 `replay_index` 六张表及版本/checksum 台账，不进入业务 migration 列表；业务 `0001`/`0002` SHA-256 保持 `3d50…f4a4` / `7751…c48`。
- **repository/recorder。**标准库 SQLite repository 只接受显式 `database_path + allowed_root`，构造与每次连接均复核 root、symlink/junction/reparse 边界；trace summary、14 个 stage 与 execution link 在单一事务中写入，重复 trace/重复 dispatch owner、错误 stage 集、锁冲突、损坏/错误 schema 均安全失败并 rollback。SQLite recorder 故障由现有 Dialogue observability boundary 吞吐为固定 `observability_unavailable`，不改变业务结果。
- **只读 CLI。**新增 `scripts/observability_report.py`，SQLite `mode=ro` 查询 trace、evaluation 摘要与 replay index；trace 支持 UUID、UTC 时间窗、terminal/error、persona、HMAC scope tag 与 `1..200` limit，JSON/text 输出均为固定 allowlist。数据库不存在或损坏只返回固定错误且不创建文件；无任意 SQL、全文搜索、payload 导出、HTTP API 或网络监听。
- **retention 与 replay 边界。**trace/stage/execution/replay 按 7 天或最近 10,000 trace、evaluation/case 按 30 天或最近 50 次运行只写 `expired` 标记，open trace 保持 active，行数不减少；未实现 purge、DELETE、VACUUM 或数据库回收。真实 trace replay 固定为 `metadata_only_not_executable`；只有版本化 synthetic fixture/case 索引可标记 `synthetic_fixture_executable`，本步骤不执行真正回放。
- **门禁。**Step 4 专项 `21 passed`，Step 1—4 observability/evaluator、API、persona、scope、幂等、并发与取消相关回归 `635 passed`；全仓 ruff、严格 mypy `83 source files`、schema drift、15 个 F-008 文件 format、tracked/untracked whitespace、ignore 与敏感信息检查均通过。正式目录和功能 worktree 的 `data/cyber-town-observability.sqlite3` 均不存在，数据库/WAL/SHM/CLI surfaces 禁止原文命中数为 0。
- **资源。**Step 3 根与误创建 `.venv` 已按本次明确授权完成精确删除；Step 4 测试根、worktree 与两个工具缓存保留并完成台账更新，处置建议见上表。
- 全程未读取 `.env`、未调用真实模型或外部服务，未读取、修改或复用 F-005 验收数据库、调用台账和预算；未修改 Godot、Dialogue v1/Schema、业务 migration/持久化、依赖、CI 或部署，未提交、推送或创建 PR。
- Step 4 当时停止于 `step_4_complete / awaiting_step_5_authorization`；后续仅在用户明确授权后进入 Step 5。

## Step 5 P1 修复、验证结果与资源收口

- **失败优先与 P1 修复。**durable open/stage 与 restart recovery 首轮为 `2 failed`：请求开始后 SQLite summary 为 0 行，repository 无 `recover_open_traces`。经单独授权后，复用既有 observability `0001` 的 open schema，增加 durable recorder 的 start/progress/finalize 事务；请求开始即写 open summary，stage 增量持久化并同步安全 metadata，终态原子补齐 14 stage/summary/execution link。重启仅把遗留 open trace 收口为 `partial / abandoned_after_restart / restart_recovery`，已完成 trace 保持不变且重复 recovery 为 0。P1 专项与 Step 4 回归 `57 passed`，相关集成 `47 passed`。
- **synthetic replay。**按 case ID 的 metadata-only runner 首轮因缺函数产生 1 个收集错误；实现严格 case/version runner 后，真实 replay index 仍固定不可执行，synthetic index 可解析到版本化 case。单 case `persona-nia` 在三个全新 Python 进程中的 digest 均为 `dc7c8b02e6805bed23dbc01927637873cb11cb09364a92dd4d9bb26616064023`。
- **综合与对抗矩阵。**Step 5 专项最终 `8 passed`；完整 fake-only 后端 `1416 passed`，覆盖三 persona、短期三元与长期/关系双元 scope、未知/恶意 NPC、提示注入、幂等/replay/retry/waiter/冲突、并发、取消/迟到/orphan、SQLite 锁/损坏、recorder 故障、重启与 replay。SQLite→DialogueService→FakeProvider 实链完成且观测数据库/WAL/SHM 禁止原文命中 0。
- **性能基线。**同机 30 个 fake-only 样本，仅记录不冻结阈值：no-recorder p50/p95/p99 `0.003/0.005/0.015 ms`、吞吐 `275,988.928/s`、增长 0；SQLite recorder p50/p95/p99 `100.763/111.243/116.297 ms`、吞吐 `9.938 trace/s`、数据库增长 `172,032 bytes`。该结果仅供 R-10 后续比较。
- **门禁。**ruff、16 个 F-008 文件 format、严格 mypy `84 source files`、schema、tracked/untracked whitespace、正式/功能 ignore 与 sensitive 均通过；业务 migration `0001/0002` hash 未变，正式与功能目录的正式 observability SQLite 均不存在，8000 监听数为 0。未修改 Dialogue v1、业务 migration、Godot、依赖、CI 或部署，未调用真实模型/外部服务或触及 F-005 资源。
- **资源边界收口。**完整后端回归包含配置负向测试，在授权根内创建了两个 synthetic `.env`：`full-backend-06\test_automation_can_disable_do0\.env`（36 bytes）和 `full-backend-06\test_tracked_ignored_runtime_f0\.env`（11 bytes），另有公开 `.env.example`（44 bytes）。未读取其内容，三者非 reparse，仓库敏感扫描为 0。用户随后精确授权删除这三个文件；仅逐文件删除，三个父目录及其他文件均保留。复核为 757 files/33,643,610 bytes、`.env*` 0，SQLite/WAL/SHM/observability surface 数量保持 344/24/24/106。
- **重复流程问题复盘。**触发原因是“完整后端回归”包含专门验证 dotenv 禁用/ignore 的测试；根因是运行前只审查了 `tmp_path`/SQLite 产物，没有静态扫描所选测试对 `.env*` 的写入。后续规则：任何声明“不含某类文件”的测试根，在运行 broad/full suite 前必须先用源码静态扫描列出该类写入点；若测试本身要求创建，必须先取得精确例外授权或缩小测试集，不再仅依赖运行时禁用 dotenv。
- Step 5 当时停止于 `step_5_complete / awaiting_step_6_authorization`；后续仅在用户明确授权后进入 Step 6。

## Step 6 独立 fake-only QA 与停止状态

- **独立黑盒设计。**没有复用 Step 5 结论作为验收；在独立脚本中重新覆盖 Nia/Ivo/Rhea persona/version/system prompt 归属、短期三元与长期/关系双元 scope、未知/恶意 NPC 与 scope/JSON 篡改、replay/retry/conflict/concurrent waiter、取消/orphan/迟到、recorder 故障、重启收口、retention 标记、只读 CLI 与 synthetic fixture replay。关键运行合计 20 条 trace、280 个 stage；scope 泄漏、禁止原文命中、provider 归属错误和非零成本均为 0，未发现 P0—P3 产品缺陷。
- **关联、重启与重复性。**并发 owner/waiter 共享一次 execution 且只有一个 dispatch；replay/conflict 不伪造 execution；retry 使用不同 execution；取消路径无迟到 commit。open trace 重启后只收口为 `abandoned_after_restart`，completed trace 不变，重复 recovery 为 0。24/24 evaluator case 通过，三个全新进程 digest 均为 `62d1fc6b65e586dd3f05e362114903b20724caf83a6f18c1061c3bd0a3cef135`。
- **Godot 黑盒。**实际 Godot 4.7.2 以固定 640×400 视口通过 `HTTPRequest → FastAPI → DialogueService → FakeProvider → 隔离业务/observability SQLite`；默认 Nia、三个 NPC 选择、新 conversation、切换清空、关系刷新和 trace 显示均通过。3 个 NPC 对应 3 次 provider dispatch、3 条 trace/42 个 stage，禁止原文 0、成本 0，8000 端口已释放。
- **门禁。**独立定向回归 `739 passed`；完整统一入口 `1418 passed`，并通过 lock、ruff、严格 mypy `84 source files`、schema、Godot import/unit、9 个基础 connectivity、10 个 Dialogue + Multi-NPC loopback、ignore/sensitive 前后复检。F-008 的 16 个 Python 改动文件 format 通过；全仓仅有 3 个与 `origin/main` 完全一致的既有格式基线偏差。tracked `git diff --check` 与 13 个 untracked no-index check 通过；业务 migration `0001/0002` 哈希未变，正式业务/observability SQLite 均不存在。
- **QA 编排事故。**首轮完整 pytest 因 Windows 环境变量中的反斜杠被解析为相对路径，误建 worktree 内测试根并使敏感扫描 fail-closed；其余 1417 项已通过。该目录经用户精确授权后删除，改用正斜杠绝对路径重跑 1418/1418 通过。此次属于测试编排错误，不是产品缺陷；后续规则是 Windows `PYTEST_ADDOPTS --basetemp` 只使用正斜杠绝对路径，并在 pytest 启动后立即核对实际根。
- **资源与安全边界。**Step 5 根和 Step 6 QA 根均已按本次明确授权删除并复核；worktree、`.ruff_cache`、`.mypy_cache`、`.pytest_cache` 和 Godot cache 保留至 Git 交付。用户随后将长期规则改为：未来由 Codex 审计并明确给出手动删除建议，用户自行删除，Codex 不再代删。全程未读取 `.env`、调用真实模型或外部服务，未读取、修改或复用 F-005 验收数据库、调用台账和预算；未提交、推送或创建 PR。
- Step 6 当时停止于 `step_6_complete / awaiting_step_7_authorization`；后续仅在用户明确授权后进入 Step 7。

## Step 7 用户 UAT、最终门禁与停止状态

- **Godot 用户 UAT。**首次误启动项目默认 `backend_status.tscn`，用户截图只显示连通性状态；只读核对确认多 NPC UAT 场景为现有 `dialogue.tscn`，未修改代码，重新以固定 640×400 窗口启动。用户实际验证 Nia、Ivo、Rhea 均可选择并完成 fake 对话，四个 completed trace UUID 互异；切回 Nia 生成新 conversation 且关系 owner 快照保持 `21/100`，当日重复变化显示 `cooldown`。用户随后明确确认切换时清空旧可见状态、快速切换无迟到结果污染，Godot UAT 通过。
- **CLI 与重启 UAT。**只读 CLI 按 trace/request/persona/HMAC scope tag/UTC 时间窗/terminal outcome/limit 查询均通过，`traces`、`evaluations`、`replay` 三 section 的 text/JSON 输出均为 metadata-only；查询前后 SQLite SHA-256 不变，缺失数据库返回固定失败且未创建。4 个用户 completed trace 均为 fake provider、各 1 dispatch、成本 0、完整 14-stage；新增 synthetic open trace在同库重建后仅一次收口为 `partial / abandoned_after_restart`，重复 recovery 为 0，原 4 个 completed trace 不变。真实 trace 的 4 个 replay index 均为 `metadata_only_not_executable`，只有版本化 `persona-nia` fixture index 为 `synthetic_fixture_executable`。
- **评估与隐私。**固定 evaluator 为 24/24 case，trace/stage 均为 `1,000,000 ppm (100%)`，scope 泄漏、禁止原文命中、provider 归属错误和非零成本均为 0；三个全新 Python 进程的 canonical digest 均为 `6647287d3c621e0558636a798631a06b423836cd3e92af46b27cd07ffb9103c4`。UAT observability SQLite 以只读连接复核 5 trace/70 stage，无禁止原文字段或精确 sentinel 值。
- **最终门禁。**Step 7 定向 CLI 测试 `5 passed`；完整 `scripts/quality.py` 为 `1418 passed`，lock、ruff、严格 mypy `84 source files`、schema、Godot import/unit、9 个基础 connectivity、10 个 Dialogue + Multi-NPC loopback、ignore/sensitive 前后复检全绿。F-008 的 16 个 Python 文件 format 通过；tracked diff 与 13 个 untracked no-index whitespace 检查通过。全仓 format 仍仅报告 `test_health_api.py`、`test_sqlite_relationship.py`、`dialogue_integration.py` 三个与 `origin/main` 完全一致的既有基线文件。业务 migration `0001/0002` SHA-256 保持 `3d50bb6116de59b2d15293a50c7ed8bceddcdc567a413f43040d92b76eacf4a4` / `7751c9a990ed6825613e738601f4f07cf0affe5f937dfe0396be492edbb89c48`。
- **Git 交付。**功能改动按 metadata 核心、链路 instrumentation、deterministic evaluator、durable SQLite/CLI/recovery 拆为 `fb732f0`、`eda6b54`、`5fc19a5`、`9afa28b` 四个提交并推送。PR #11 的 GitHub Linux `quality` 在 58 秒内通过，随后 squash merge 为 `c78f1c190bd3a3753e849aa7da76c88dbf5c27b2`；功能分支和 worktree 均保留，文档未混入功能 PR。
- **端口与资源。**正式/功能目录的正式业务与 observability SQLite 均不存在，8000 监听数为 0。两个 Step 7 根在 Git 交付预检时已不存在，本轮只读复核且未执行删除；worktree 与 `.ruff_cache`、`.mypy_cache`、`.pytest_cache`、`game/.godot` 继续保留，后续清理仍须单独授权。
- 全程未读取 `.env`、未调用真实模型或外部服务，未读取、修改或复用 F-005 验收数据库、调用台账和预算；未部署、未进入 R-10 或选择下一 roadmap 任务。
- 最终状态为 `archived / delivered`；当前任务页恢复 `no_active_task`。
