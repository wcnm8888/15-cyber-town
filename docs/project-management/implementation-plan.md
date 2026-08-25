# 实现计划：F-005 长期记忆与检索评估

状态：`approved / step_7_complete / ready_for_git_delivery`。

本计划只服务于 [`F-005 当前任务卡`](current-task.md)。F-001—F-004 均已通过 PR #1—#4 交付并归档；当前基线分支为 `main`，HEAD / `main` / `origin/main` 均为 `3e03d64d129871495f3fe73295ee9b11478f2e71`。每个 Step 必须单独获得用户授权，不得复用 F-004 的实现、真实 provider、费用或 Git 授权。

## Step 地图

| 阶段 | 当前状态 | 范围 | 停止边界 |
| --- | --- | --- | --- |
| Step 0 | `complete` | 已批准任务卡/计划落盘；Git、sqlite3、公开契约、架构适配点与 F-004 合并事实只读复核 | 不创建分支、数据库、目录、migration、实现或真实调用 |
| Step 1 | `complete` | 功能分支、长期记忆冻结配置、SQLite 路径/权限/ignore 边界、调用台账路径和失败优先配置测试 | 配置专项 277 passed，全量 fake-only 719 passed；未创建数据库 |
| Step 2 | `complete` | 长期记忆值对象、schema v1、标准库 sqlite3 repository、唯一约束/索引/参数化 SQL 和 pytest 临时数据库 | 专项 130 passed，全量 fake-only 849 passed；未创建正式数据库 |
| Step 3 | `complete` | 确定性记住/忘记、scope 隔离、过期、容量、version、tombstone、事务与幂等 | 应用专项 69 passed，长期专项 199 passed，全量 fake-only 918 passed |
| Step 4 | `complete` | 确定性检索、排序、provider-neutral 注入、8192 工程预算、FastAPI + FakeProvider 与 Godot loopback | 长期专项 254 passed，全量 fake-only 975 passed；未创建正式数据库 |
| Step 5 | `complete` | 72 项 fixed golden set、当前事实文档同步、跨进程 SQLite 预算台账及专项授权的真实 DeepSeek 长期记忆评估 | golden precision/recall 1.00；离线专项 59 passed；真实调用 7 次、1244 输入/106 输出 tokens、USD 0.000690 |
| Step 6 | `complete` | 独立 QA、失败优先修复、默认启动 fake-only 联调、scope/持久化/事务/预算与幂等负例 | 首轮 5 项 P1、3 项 P2 及近邻已修复；fake-only 全量 1095 passed；两名独立 reviewer NO FINDINGS；误创建文件已依专项授权定向删除 |
| Step 7 | `complete / user_uat_passed` | 用户真实 Godot 窗口 UAT、隔离 SQLite、重启/遗忘验证、跨进程调用台账核对和最终本地交付审查 | 3 次、500/141 tokens、USD 0.000408；正式数据库未创建、端口已释放；ready_for_git_delivery |
| Git 交付 | `not_authorized` | 按方法论另行审批提交、push、PR、CI、合并与最终归档 | 禁止复用 F-004 Git 授权或提前归档 |

## 已冻结的技术与数据边界

- 短期 scope 为 `(player_id, npc_id, conversation_id)`；长期 scope 为 `(player_id, npc_id)`。
- SQLite 是唯一长期事实真相源；只使用 Python 3.12 标准库 `sqlite3`，不引入 SQLAlchemy、Alembic、FTS、embedding、Qdrant、PostgreSQL 或 Redis。
- 正式数据库为 `data/cyber-town.sqlite3`；UAT 数据库为 `data/uat/f-005/<run-id>/cyber-town.sqlite3`；自动化仅使用 pytest `tmp_path`；真实调用跨进程台账为 `data/acceptance-ledgers/f-005.sqlite3`。
- 批准的 fact keys 为 `game_alias`、`preferred_language`、`reply_style`、`favorite_cyber_town_topic`；只支持 `profile/preference`、显式确定性记住/永久记住/忘记命令，不保存原始对话与凭证。
- 默认 TTL 30 天；每 scope 最多 64 条、全局最多 4096 条，每次召回最多 4 条；永久保存必须显式授权，遗忘清空正文并保留无正文 tombstone。
- SQLite `BEGIN IMMEDIATE` / `busy_timeout=2000`，参数化 SQL、版本化 schema、事务幂等和故障 fail-closed；数据库异常沿用 503 / `provider_unavailable`，不增加公开错误码。
- Nia 为唯一 system；长期事实是独立 SDK-neutral 不可信 user 数据；总预算 8192、固定回复预留 256、长期事实最多 2048 工程单位，短期历史仍按完整回合裁剪。
- 公开 Dialogue v1、派生 JSON Schema、现有 Godot 场景、`pyproject.toml`、`uv.lock` 和 GitHub workflow 保持不变；自动化与 CI 永久 fake-only。

## Step 0 完成证据

- Git 只读复核：分支为 `main`，HEAD / `main` / `origin/main` 均为 `3e03d64d129871495f3fe73295ee9b11478f2e71`；origin 为当前项目现有 GitHub remote，开始前工作树干净。
- F-004 已通过 PR #4 squash merge 并归档；旧任务卡与实现计划均存在，历史归档本轮不修改。
- Python 3.12.10 自带 `sqlite3`，SQLite runtime 版本为 3.47.1；当前无 `.db/.sqlite/.sqlite3` 文件、长期 repository、migration、embedding 或向量依赖。
- 已只读核对 `DialogueRequestV1/DialogueResponseV1/ApiErrorV1`、三元 scope store、8192/256 工程预算、provider-neutral 历史、DeepSeek/Fake adapter、FastAPI composition、Godot conversation/retry 和现有 `.gitignore`。
- 当前 ignore 已覆盖根 `data/*.db`、`data/*.sqlite*`、`data/qdrant/`；分层 UAT、acceptance-ledgers 和 SQLite sidecar 显式规则留待 Step 1 批准。
- 仅同步任务卡、实现计划及入口/管理文档中 F-004 已合并、F-005 已批准的事实；未读取 `.env` / API key，未创建分支、数据库、目录、表、migration 或运行时文件，未提交、推送或进入 R-06。

## Step 1 已批准范围：分支、冻结配置与 SQLite 路径边界

用户已明确授权并按以下范围完成：

1. 只读确认 HEAD / `main` / `origin/main` 保持 `3e03d64d129871495f3fe73295ee9b11478f2e71`，staged/untracked 为 0，工作树仅包含 Step 0 批准的八份文档修改。
2. 从最新 `main` 创建并检出 `feat/f-005-long-term-memory-retrieval-evaluation`，完整保留 Step 0 文档修改，不提交到其他任务分支。
3. 先写会失败的配置和路径负例：长期 scope、4 个 fact keys、64/4096/4 上限、30 天 TTL、2 秒 DB lock、8192/256 兼容、正式/UAT/台账路径与 no FTS/no Qdrant。
4. 验证 `data/` 下的路径边界，拒绝 `..`、外部绝对路径、兄弟项目、symlink/reparse point 逃逸，以及把正式数据库误用于 pytest/UAT。
5. 仅在获批范围内修改 `backend/src/cyber_town/config.py`、`backend/tests/test_config.py` 或相关配置测试、`.gitignore`、当前任务卡和本计划；入口摘要只在状态确有变化时最小更新。
6. 明确 Git ignore 覆盖 `data/**/*.db`、`data/**/*.sqlite*`、SQLite WAL/SHM/journal、`data/uat/**` 与 `data/acceptance-ledgers/**`；只验证规则，不创建正式数据库或目录。
7. 运行配置定向测试、ruff、mypy、既有 fake-only 统一质量入口、lock、schema、ignore、sensitive 和 `git diff --check`。
8. 全部通过后只更新 Step 1 必要状态，并停在 `step_1_complete / awaiting_step_2_authorization`。

Step 1 禁止创建正式 SQLite 数据库、schema、表、migration、repository、记住/忘记命令、provider DTO、Godot 改动、预算台账实现或 Qdrant；不读取 `.env` / API key，不调用真实模型，不新增依赖，不提交、推送、创建 PR 或进入 R-06。

## Step 1 完成证据

- 分支为 `feat/f-005-long-term-memory-retrieval-evaluation`；HEAD / `main` / `origin/main` 均为 `3e03d64d129871495f3fe73295ee9b11478f2e71`，原 Step 0 八份文档完整保留。
- 失败优先红灯：新增 F-005 配置/路径/ignore 测试后，首次运行得到 `130 failed, 5 passed`；原因为长期配置尚不存在、嵌套 UAT/台账路径未被忽略。
- `config.py` 新增双元长期 scope、4 个批准 fact keys、64/4096/4 容量、30 天 TTL、2048 长期预算、2 秒 SQLite lock 及正式/UAT/台账冻结路径；拒绝类型强制、参数漂移、路径逃逸与模拟 symlink/junction。
- `.gitignore` 新增 `data/**/*.db`、`data/**/*.sqlite*`、`data/uat/` 和 `data/acceptance-ledgers/`；SQLite WAL/SHM/journal 及 UAT 附件受保护，可审查数据说明保持可见。
- F-005 专项 `135 passed`；全部配置测试 `277 passed`；配置与测试两文件 ruff、ruff format、mypy 通过。
- `uv run --frozen python scripts/quality.py` 通过：pytest `719 passed`、lock 45 packages、ruff、mypy 42 files、Schema、Godot import/unit、9 个健康 loopback、10 个 fake 对话 loopback、ignore/sensitive preflight/final 全通过。
- 项目未创建 `data/`、数据库文件、migration、表、repository、预算台账或业务代码；未修改公开契约、Godot、依赖、CI，未读取 `.env` 或 API key、调用真实模型、提交、push 或进入 R-06。

## Step 2 已批准范围：长期记忆模型与 SQLite repository

用户已明确批准，先从任务卡编写会失败的长期记忆值对象、schema v1、标准库 sqlite3 repository、字段/唯一键/索引、参数化 SQL、重复初始化、事务 rollback、锁冲突、scope 查询与损坏 fail-closed 测试。只在 pytest `tmp_path` 创建隔离 SQLite；不得创建正式数据库、接入 DialogueService/provider/Godot、实现记住/忘记或进入 Step 3。

## Step 2 完成证据

- 开始前分支为 `feat/f-005-long-term-memory-retrieval-evaluation`，HEAD / `main` / `origin/main` 保持 `3e03d64d129871495f3fe73295ee9b11478f2e71`；Step 0—1 的 11 项已批准工作树修改完整保留，`data/` 不存在。
- 首次运行新增的领域模型与 repository 测试产生 `2 errors during collection`，明确证明 `cyber_town.domain.long_term_memory` 尚不存在，满足失败优先。
- 领域层新增不可变双元 `LongTermMemoryScope`、不可变 `LongTermMemoryRecord`、`MemoryType` 和 `MemoryStatus`；验证四类白名单事实、严格 UUID、数值/时间/version 边界、正文脱敏与 bodyless tombstone。
- 持久化层新增标准库 `sqlite3` repository 和 `0001_long_term_memory.sql`；schema 包含长期事实、幂等 operation 预留表、无正文 event 表、migration checksum、唯一业务键与 scope/status/expiry、scope/fact、updated 索引。
- repository 验证显式受限路径、重复初始化、WAL/foreign keys、固定 2 秒 busy timeout、参数化 SQL、双 scope 查询、唯一键冲突、事件失败整体 rollback、数据库损坏/版本漂移与锁冲突 fail-closed。
- SQLite 数据文件全部位于 pytest `tmp_path`；Step 2 专项 `130 passed`，Step 1 全部配置 `277 passed`，统一 fake-only 门禁 `849 passed`；ruff、mypy 47 files、lock 45 packages、Schema、9 个健康 loopback、10 个 fake 对话 loopback、ignore/sensitive 均通过。
- 项目 `data/` 和正式/UAT/台账 SQLite 均未创建；未接入 DialogueService/provider/Godot，未实现记住/忘记或应用检索，未读取 `.env` / API key、调用真实模型、提交、推送或进入 R-06。

## Step 3 已批准范围：显式命令、生命周期与事务幂等

用户已明确批准，先为确定性记住/永久记住/忘记命令、双元 scope 隔离、30 天过期、64/4096 容量、version 更新、无正文 tombstone、SQLite 事务与 request 幂等编写失败优先测试；只使用 pytest 临时数据库与 fake provider，不进入确定性检索/上下文注入、真实模型调用、Git 交付或 R-06。

## Step 3 完成证据

- 开始前分支、HEAD / `main` / `origin/main` 及 Step 0—2 文件范围均未漂移，项目 `data/` 不存在；新增应用专项首次运行因 `cyber_town.application.long_term_memory` 不存在而产生 `1 error during collection`。
- 独立应用层严格解析已冻结的中英文显式记住/永久记住/忘记模板；只允许 4 个批准 fact keys 和各自合法值，普通对话不落库，成功复用既有 Dialogue v1 返回 `completed / local-memory`，不调用 provider。
- SQLite repository 在单个 `BEGIN IMMEDIATE` 事务内完成 request fingerprint/replay 校验、过期转换、64/scope 和 4096/global 容量、首次创建、同 `memory_id` 的 version 更新、正文清空 tombstone、无正文 event 与 operation 记录。
- 已验证 30 天到期前/整点/之后、显式永久、新 conversation、repository 重启、跨 player/NPC 零泄漏、遗忘后恢复新值、无活跃记忆时安全遗忘、容量满时不驱逐、已存在更新不消耗新容量。
- 已验证同 request replay、重启后 replay、不同 payload/scope 409、并发重复请求仅写一次、并发独立更新不丢 version、operation 失败后 memory/event/过期副作用统一回滚，以及 2 秒锁边界故障 fail-closed。
- Step 3 应用专项 `69 passed`；全部长期记忆专项 `199 passed`，既有配置 `277 passed`，统一 fake-only 全量 `918 passed`；ruff、mypy 49 files、lock 45 packages、Schema、Godot unit/import、9 个健康 + 10 个 fake 对话 loopback、ignore/sensitive 全通过。
- SQLite 仅出现在 pytest `tmp_path`；未创建正式/UAT/台账数据库或 `data/`，未接入 FastAPI/DialogueService/provider/Godot，未实现检索、事实注入、8192 预算改动或 Step 4；未读取 `.env` / API key、调用真实模型、提交、推送或进入 R-06。

## Step 4 已批准范围：确定性检索、上下文注入与 fake-only 联调

用户已明确批准，先为精确 fact key/固定别名检索、未过期 active 过滤、确定性排序、最多 4 条召回、唯一 persona system、不可信长期事实 DTO、8192/256 总预算及长短期完整裁剪编写失败优先测试；再只使用 pytest 隔离 SQLite 完成现有 FastAPI + FakeProvider 与 Godot 生产对话场景的真实本地 loopback，不读取真实 `.env`、不调用真实模型、不增加公开 API/Godot 页面或进入 Step 5/R-06。

## Step 4 完成证据

- 首次运行新增检索、HTTP/Godot 联调和 provider adapter 专项时得到 `3 errors during collection`；缺失对象分别为 `select_context_messages`、`LongTermMemoryRetriever` 和 `ProviderLongTermFact`，证明失败测试先于实现。
- SQLite 新增参数化、双元 scope、`active`、未过期、`confidence > 0` 的只读查询；检索器先精确 key、再匹配固定中英文别名，并按 importance、confidence、updated_at、memory_id 稳定排序，最多召回 4 条。
- provider-neutral 事实 DTO 严格复用低敏感白名单校验，正文不进入 `repr`，只序列化为带 `UNTRUSTED_LONG_TERM_MEMORY` 明确标记的 user 数据；SDK stub 证明消息顺序为唯一 persona system → 长期事实 → 完整短期回合 → 当前 user。
- 总上下文继续使用 UTF-8 工程估算 8192、回复预留 256、长期事实最多 2048；persona/当前问题/回复额度不被挤占，事实按整条、短期历史按完整 user/assistant 回合裁剪。
- 现有 FastAPI Dialogue v1 支持显式管理命令、跨 conversation/重启恢复、跨 player 隔离、更新替换、遗忘和 honest unknown；显式命令为 `completed / local-memory`，不调用 provider，也不新增公开 memory API。
- 真实 headless Godot 复用既有生产对话场景，通过本地 FastAPI、隔离 SQLite 和 FakeProvider 完成记住 → 召回 → 忘记 → 明确不知道；已用失败优先负例修复同 conversation 遗忘后短期历史导致旧值复活的边界。
- 全部长期专项 `254 passed`，配置专项 `277 passed`，统一 fake-only 全量 `975 passed`；ruff、mypy 51 files、lock 45 packages、Schema、Godot import/unit、9 个健康 + 10 个既有对话 loopback、ignore/sensitive 全通过。
- 未创建项目 `data/`、正式/UAT/台账 SQLite，未修改公开契约/Schema、Godot 生产场景、依赖或 CI；未读取 `.env` / API key、调用真实 provider、提交、推送或进入 Step 5/R-06。

## Step 5 已批准离线范围与独立真实专项授权

用户先批准固定 fake-only golden set、跨进程 SQLite acceptance ledger、计量 provider 包装器和当前事实文档同步，随后独立明确授权现有 Settings 读取 Git 忽略 `.env`、真实 DeepSeek 网络调用、正式验收台账和隔离 SQLite；Step 5 上限仍为 8 次/USD 0.035，不自动授权 Step 6、Step 7、Git 交付或 R-06。

## Step 5 已完成的离线证据

- golden set 与 SQLite acceptance ledger 首次失败优先测试得到 `2 errors during collection`；后续 `MeteredAcceptanceProvider` 首次专项再得到 `1 error during collection`，均证明测试先于实现。
- 固定版本 `f-005-v1` golden set 共 72 项，覆盖四类 fact keys、精确 key、中英文别名、跨 player/NPC、更新、遗忘、过期、空结果和无关问题；precision `1.00`、recall `1.00`，scope 泄漏、遗忘/过期召回、旧值复活与空结果虚构均为 0，纯短期跨 conversation baseline recall `0.00`。
- 隔离 SQLite acceptance ledger 仅保存授权标识、Step、模型、状态、token、整数 micro-USD 与时间戳；Step 5 `8 / USD 0.035`、Step 7 `4 / USD 0.015`、总计 `12 / USD 0.05` 均在 provider 调用前通过 `BEGIN IMMEDIATE` 原子预留，跨线程/进程、reserved/unknown、模型漂移、预算超限和损坏均 fail-closed。
- provider-neutral 计量包装器经 FakeProvider 证明：先提交 reservation，再发起调用；completion 返回即先持久化 usage，然后才交回上层执行语义断言。后续断言失败不会丢失已发生的 token/费用；provider 异常保留 unknown 并阻断后续调用。
- golden、ledger 和计量 provider 专项 `59 passed`；统一 fake-only 入口 `1034 passed`，ruff、mypy 57 files、lock 45 packages、Schema、Godot unit/import、9 健康 + 10 对话 loopback、ignore/sensitive 均通过。
- 已同步项目入口、架构、技术栈、Agent/记忆设计、测试/评估策略、ADR、roadmap/progress/evidence 与当前任务状态，纠正旧文档的“Step 1 / 无 SQLite / 无长期记忆”漂移；未创建正式业务数据库。

## Step 5 已完成的真实 DeepSeek 专项证据

- 用户独立批准现有 Settings 读取 Git 忽略的 `.env`、启用已冻结的 DeepSeek adapter、初始化 `data/acceptance-ledgers/f-005.sqlite3` 和使用 `data/uat/f-005/step-5-real-20260825/cyber-town.sqlite3`；两个运行时 SQLite 均被 Git 忽略，正式 `data/cyber-town.sqlite3` 未创建。
- 首次 SDK 初始化遇到继承的 SOCKS `ALL_PROXY`，在网络调用前退出；台账证明请求/token/费用均为 `0`。随后仅对一次性验收进程移除 SOCKS 代理、保留 HTTP/HTTPS 代理，不安装依赖、不修改系统或 `.env`。
- 真实 FastAPI → DialogueService → DeepSeek 依次验证跨 conversation 召回、repository/service 重建后恢复、跨 player 隔离、更新值替换、四类白名单事实、唯一 Nia persona 优先、遗忘后同 conversation 不复活和空结果不虚构；记住/忘记、无记忆和跨 scope 路径均未调用 provider。
- 实际真实请求 `7 / 8`，官方 usage `1244` prompt tokens、`106` completion tokens；每次先原子预留，再于 provider 返回后立即提交脱敏 usage，然后进行语义断言；按峰值单价逐次向上取整的 metadata-only 台账费用 `690 micro-USD / USD 0.000690`，未结算请求为 `0`。
- Step 5 完成时仅允许等待独立 QA 的 Step 6 授权；当时 Step 7 真实用户 UAT 仍须另外明确授权且继续限 4 次/USD 0.015。后续完成事实见 Step 6 与 Step 7 章节。

## Step 6 独立 QA 首轮结论与授权边界

- 用户已授权 fake-only 独立 QA；后端 reviewer 使用 9 个纯内存复现，Godot/API reviewer 运行 `92 passed` 以及 `175 passed / 1 deselected` 的定向回归，主流程运行后端联合专项 `661 passed` 和完整统一门禁 `1034 passed`。
- 去重后 **5 项 P1**：正常 FastAPI 启动未装配 SQLite 长期记忆且管理命令误调用 provider；同 conversation 更新后旧 assistant 历史复活旧值；普通对话与记忆命令之间复用 request_id 不返回 409；zero usage/zero cost 被真实调用台账接受；低敏感话题输入校验允许任务卡禁止的数据/角色变体。
- 去重后 **3 项 P2**：过期清理跨 player/NPC 修改状态并串线事件 request_id；golden evaluator 对全负例零召回误报 precision/recall=1；遗忘抑制阶段 SQLite 查询失败错误映射 500 而不是可重试 503。
- 输入数据类别与角色伪装属于同一低敏感 topic 校验根因，按单个 P1 合并；不得把既有 1034 测试通过或 Step 5 真实结果冒充这些独立组合已覆盖。
- 首轮状态曾为 `blocked / awaiting_fix_authorization`；用户随后已明确授权仅在 Step 6 内修复、补失败优先负例和重新独立复审，禁止读取 `.env`、调用真实模型或进入 Step 7/R-06。

## Step 6 已授权修复、复审与正式路径文件处置完成

- 首轮组合负例先产生 `27 failed, 4 passed`，修复默认 SQLite 装配、双路径/跨重启 request 指纹、usage 严格正数、许可话题词汇、scope-only 过期、真实 baseline/golden 完整性及 SQLite 故障 HTTP 503；旧值通过短期历史、跨 conversation、NFKC/casefold 和在途请求复活的独立近邻同样先红后绿。
- 后续 completed replay / durable replay 组合先产生 `5 failed`；更新/遗忘后的旧 provider 缓存按双元 owner 代次返回 409，不泄漏旧值也不重复调用；重启后的 Remember/Forget 持久化 replay 不清理合法新值历史、不误取消在途请求；专项扩展为 `8 passed`。
- 两名 reviewer 使用纯内存/pytest SQLite、FakeProvider 与真实 Godot loopback 独立复验；Godot/API reviewer 定向 `360 passed`。统一 fake-only 全量 `1095 passed`，lock 45、ruff、mypy 57、Schema、Godot unit/import、9 健康 + 10 对话 loopback 与 ignore/sensitive 均通过。
- 默认装配修复后，旧 FakeProvider 测试因只修改工作目录而曾误创建受 Git 忽略的 `data/cyber-town.sqlite3`；已统一把 composition 项目根隔离到 pytest 临时目录，并锁定默认启动链路不再触碰正式路径。用户随后明确授权仅定向删除该 `53248` 字节文件；删除前验证精确绝对路径，未读取数据库内容，未删除其他文件。
- Step 5 隔离验收数据库与正式 metadata-only acceptance ledger 完整保留；Step 6 收口时台账为 7 次、1244/106 tokens、USD 0.000690、pending=0，零新增真实调用和费用。用户随后授权进入 Step 7，仅等待其亲自执行受限真实窗口 UAT，不进入 R-06。

## Step 7 用户 UAT 执行边界

- 后端必须通过现有 `Settings`、冻结 DeepSeek adapter、`MeteredAcceptanceProvider`、`AcceptanceStep.STEP_7` 与既有 `data/acceptance-ledgers/f-005.sqlite3` 组装；每次真实调用前原子预留，返回后先记录官方 token 和保守 micro-USD。
- 只允许使用 `data/uat/f-005/step-7-user-20260825/cyber-town.sqlite3` 隔离数据库；普通 `python -m cyber_town.api` 会创建正式数据库且绕过计量，因此不得用于本轮 UAT。
- 用户亲自在既有 Godot 对话场景验证初始 unknown、显式记住、新窗口/新 conversation 召回、停止并重启后端后召回、更新替换、明确遗忘与最终 unknown。记住/更新/忘记/空结果零 provider；预计 3 次真实请求，硬上限 4 次/USD 0.015。
- 只有用户回传 UAT 结果、Step 7 调用/token/费用与 8000 端口释放证据后，才可执行最终 fake-only 门禁和必要状态收口；不得自动执行 Git 交付或进入 R-06。

## Step 7 完成证据

- 用户真实 Godot 窗口依次验证初始 unknown、显式记住、新窗口召回、后端重启后召回、更新替换、遗忘和最终 unknown，全部通过；没有旧值复活或空结果虚构。
- Step 7 台账为 `3` 次、`500` prompt tokens、`141` completion tokens、`408 micro-USD / USD 0.000408`、pending `0`；F-005 累计 `10` 次、`1744 / 247` tokens、`USD 0.001098`、pending `0`。
- UAT 数据库使用批准的受忽略隔离路径；`PORT_8000_STOPPED=YES`，`FORMAL_DATABASE_CREATED=NO`。
- 最终 fake-only 统一入口 `1095 passed`，既定本地交付门禁通过，状态收口为 `ready_for_git_delivery`；Git 交付仍为 `not_authorized`，未进入 R-06。

## 后续 Step 的失败优先和验收约束

- Step 2 先证明 schema/repository 不存在，再在 pytest 临时数据库验证字段、唯一键、索引、重复初始化、参数化 SQL、损坏、锁等待与事务 rollback。
- Step 3 先证明显式写入、跨 conversation 恢复、更新/遗忘与 request 幂等缺失，再实现 scope 隔离、64/4096 容量、30 天过期、无正文 tombstone 和成功后提交边界。
- Step 4 先证明 exact key/别名、唯一 system、长短期共同预算和 Godot/FakeProvider 联调缺失，再实现确定性排序与 honest unknown；禁止读取真实 `.env`。
- Step 5 golden set 最少 60 项，precision ≥ 0.95、recall ≥ 0.90，跨 scope 泄漏、已遗忘召回、旧值复活和空结果虚构均为 0；真实评估必须先获独立 API key/网络/费用授权并完成台账预留。
- Step 6 独立 QA 从任务卡重建跨 scope、事务中断、重复 request、并发、TTL、损坏、SQLite 文件入 Git、prompt 注入、台账竞争和预算突破负例；P1/P2 必须经用户授权修复并复审。
- Step 7 用户亲自使用现有 Godot 场景确认记住→新 conversation→重启召回→更新→遗忘→不知道；真实 UAT 须独立授权、记录调用/token/费用并释放端口，随后只运行最终本地 fake-only 交付门禁。

## 调用预算与停止条件

真实专项独立上限：Step 5 ≤ 8 次/USD 0.035，Step 7 ≤ 4 次/USD 0.015，F-005 总计 ≤ 12 次/USD 0.05。台账先使用原子事务预留调用与保守费用，再进行网络请求；provider 返回后先落脱敏 usage，再做语义断言；未知调用、缺失 usage、预算冲突或进程重启均 fail-closed。

以下情况立即停止：Git 基线/文件范围漂移；需要修改公开契约、依赖、Godot、CI 或正式 UI；创建未授权正式数据库、读取 `.env` / API key、调用真实模型或引入 Qdrant；出现 scope 泄漏、旧值复活、原文落盘、重复写入、台账异常、P1/P2 或任一既定门禁失败；需要进入尚未授权的后续 Step、Git 交付或 R-06。
