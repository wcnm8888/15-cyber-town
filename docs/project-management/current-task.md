# 任务卡：F-006 确定性好感度系统

状态：`git_delivery_authorized / pending_commit_push_pr_ci`。

## 用户目标与用户可见价值

玩家在完成与 Nia 的正常对话后，能够看到当前好感度、关系阶段、本次变化及稳定原因码；关系变化必须可由确定性规则和脱敏审计解释，而非由 LLM 直接决定。

## 当前基线与前置条件

- 当前 Git 基线：`main` / `HEAD` / `origin/main` 均为 `c9d11b0a3c441a10463ad4522bb226f055f07f35`；工作树在 Step 0 开始时干净。
- F-005 已通过 PR #5 合并并归档；其真实调用、隔离 UAT 数据库、调用台账和预算不属于 F-006，禁止读取、修改、删除或复用。
- 既有单 NPC 为 `neon_guide / Nia / nia_v1`；Dialogue v1、短期三元 scope、长期 SQLite 双元 scope、FakeProvider 与 fake-only CI 均为冻结前提。
- F-006 不读取 `.env` 或 API key，不调用真实模型，不产生费用。

## 已批准范围与默认决策

- 关系所有权固定为 `player_id + npc_id`；跨 conversation 与服务重启保持，不同 player/NPC 严格隔离。
- 初始值为 `20`，范围 `0..100`，单次最大变化 `±2`；阶段为 `newcomer (0–19)`、`acquaintance (20–49)`、`friend (50–79)`、`trusted_ally (80–100)`；不允许负分或跨阶段跳跃。
- 允许候选分类为 `supportive (+2)`、`friendly (+1)`、`neutral (0)`、`dismissive (-1)`、`hostile (-2)`；非零变化要求整数 `confidence >= 80`。
- 每个 `(player_id, npc_id)` 每 UTC 日最多一次有效非零变化；冷却、低置信度、无效或未知建议均为 `delta = 0` 且给出稳定 reason code。
- LLM 仅通过现有对话调用提供内部严格分类建议；它不得指定分数、阈值、权限、规则版本、状态转移或持久化操作。非法类型、额外字段、未知类别、越界置信度和提示注入均 fail-closed。
- 复用既有 SQLite 真相源；迁移机制改为有序追加、逐项 checksum 校验，新增不可变 `0002_relationship_state.sql`，不得修改 F-005 的 `0001_long_term_memory.sql`，不得创建第二数据库。
- 关系状态和事件在单个 `BEGIN IMMEDIATE` 事务中写入；沿用 2 秒锁等待。`request_id` 唯一，附带 request fingerprint；同 ID 同 payload 重放原判定，不同 payload 返回冲突。
- 事件审计只保存 scope、request/trace/conversation ID、分类、置信度、规则/版本、reason code、delta、before/after、阶段和时间；严禁保存原始玩家消息、prompt、模型回复、provider body 或 API key。
- 新增只读 `GET /api/v1/relationships/{player_id}/{npc_id}?request_id=<optional UUID>`；使用新的严格关系契约，绝不修改 `DialogueRequestV1`、`DialogueResponseV1`、`ApiErrorV1` 或其 JSON Schema。
- Godot 只复用既有 Nia 对话场景展示关系快照；最小视觉契约已获用户批准，但任何 Godot 改动仍须等待获批的 Step 4。
- 自动化、CI、独立 QA 与用户窗口 UAT 均使用 FakeProvider；F-006 不需要真实 provider 专项评估或费用预算。

## 明确非目标

- 多 NPC、R-07、社交图谱、NPC 与 NPC 关系、自主 Agent、交易、礼物、任务、复杂权限、正式 UI 资产、部署和生产访问。
- embedding、Qdrant、Redis、PostgreSQL、第二数据库、公开 Dialogue v1 契约改动。
- 关系数据清除功能；长期记忆的忘记命令不得被扩展为关系删除。

## 触发与失败边界

仅普通对话在 provider 回复已通过现有校验、结果为 `completed`、未取消且未晚到时才可进入关系判定。timeout、unavailable、非法 provider 响应、degraded/local fallback、内容过滤、取消、晚到、重试失败、长期记忆管理命令和 scope/SQLite 故障均不得改变关系。

持久化关系评分幂等，不等同于为 Dialogue v1 保存原始回复或提供跨重启对话缓存；后者会扩大隐私与现有冻结设计边界，因此不属于 F-006。

## 数据、回放与隐私

建议新增 `relationship_states` 与不可变 `relationship_events`。首次只读查询可返回虚拟初始快照，不产生写入。事件回放从初始值按时间、事件 ID、规则版本和已记录的裁决验证 before/after；不读取任何原文。迁移损坏、checksum 漂移、数据库损坏、锁超时或回放不一致必须 fail-closed。

## API 与 Godot 行为

关系 GET 返回 `npc_id`、当前 `score`、`stage`、`rule_version`，以及可选的同 scope、同 request 的事件摘要（分类、实际变化、reason code、结果分数/阶段、时间）。不存在持久化状态时返回初始快照；该本地接口只做 scope 隔离，不应被描述为公网身份认证或多人授权机制。

Godot 场景加载时读取快照；正常成功对话后以其 request ID 再读取一次。错误、降级或缺少事件时不得伪造变化。

## 最小视觉契约

状态：`approved / 2026-08-25`。

- 页面：复用 `game/scenes/dialogue.tscn`，不新增场景或正式素材。
- 位置：在现有回复/trace 区域下方增加只读 `Relationship` 信息区。
- 正常：显示 `Affection: 20/100`、`Stage: Acquaintance`；本轮有事件时再显示 `Change: +1` 与 `Reason: rule_friendly`。
- 初始/空：只显示初始分数和阶段；不显示伪造的 change 或 reason。
- loading：首次关系 GET 或对话后的刷新期间显示 `Relationship: loading…`，不覆盖最后一个已验证快照。
- error：显示 `Relationship unavailable`，保留对话本身的既有成功或错误状态，不显示内部异常。
- 交互：关系区纯只读；发送、Retry、禁用与现有 DialogueState 保持不变。
- 验收视口：现有桌面 `dialogue.tscn`，固定 `local_player / neon_guide` 和 FakeProvider fixture；先完成一张同尺寸截图/用户视觉确认，再进入 Godot 实现。

## 测试与验收

使用参数化和穷举而非新增 Hypothesis：覆盖五分类、置信度边界、分数/阶段边界、冷却、饱和、同 ID 重放/冲突、并发、rollback、锁竞争、跨 player/NPC、跨 conversation、重启、失败/降级、记忆命令、迁移兼容、审计回放和原文零落盘。FastAPI、Godot、真实 loopback 均只接 FakeProvider；CI 永久 fake-only。

## Step 地图

| Step | 内容 | 当前状态 |
| --- | --- | --- |
| 0 | 锁定任务卡、迁移决策、F-005 合并事实与最小视觉契约 | 已完成 |
| 1 | 功能分支、失败优先边界测试与配置 | 已完成 |
| 2 | 分类契约、规则与状态机 | 已完成 |
| 3 | SQLite migration、repository、事务、幂等、回放 | 已完成 |
| 4 | DialogueService、关系 GET、Godot、fake loopback、文档 | 已完成 |
| 5 | fake-only 对抗与性质评估 | 已完成 |
| 6 | 独立 QA | 已完成 |
| 7 | 用户 Godot + FakeProvider UAT、最终本地门禁 | 已完成 |
| Git 交付 | commit、push、PR、CI、合并和归档 | 已授权，进行中 |

推荐功能分支：`feat/f-006-deterministic-affection`。

## Step 1 完成证据

- 已创建本地功能分支 `feat/f-006-deterministic-affection`；未提交、推送或创建 PR。
- 新增 F-006 冻结配置与失败优先负例的首次定向运行得到 `77 failed, 277 deselected`，证明关系配置尚不存在。
- `config.py` 现锁定双元 relationship scope、`f-006-v1`、`20 / 0 / 100 / ±2 / 80 / 每日 1 次`和五个允许分类；拒绝 mutable sequence、bool/float 强制转换、类型/边界/环境漂移。
- 实现后 `uv run --frozen pytest backend/tests/test_config.py` 为 `354 passed`；定向 ruff、ruff format、mypy 及 `git diff --check` 均通过。
- 未创建数据库、表、migration 或运行时 `data/`；未读取 `.env`、调用真实模型、复用 F-005 资源、安装依赖、提交或推送。

## Step 2 完成证据

- 新增纯领域 `relationship.py`；未接入 provider、DialogueService、SQLite、FastAPI 或 Godot。
- 新增严格 `InteractionSuggestion.from_untrusted`：只接受精确 `category + confidence` JSON 对象；额外字段、未知分类、非整数/越界置信度和提示注入样式内容均返回无分类的 `candidate_invalid / delta 0` 判定。
- 已冻结五类到 `+2 / +1 / 0 / -1 / -2` 的唯一映射、`confidence >= 80`、`0..100` 饱和、四阶段、UTC 日冷却和规则版本检查；模型没有分值、规则或状态写入接口。
- 首次运行新领域测试因模块不存在于收集阶段失败；实现后 `test_relationship.py` 为 `68 passed`，与 `test_config.py` 联合为 `422 passed`。定向 ruff、ruff format、mypy 与 `git diff --check` 均通过。
- 未创建数据库、表、migration 或运行时 `data/`；未读取 `.env`、调用真实模型、复用 F-005 资源、提交或推送。

## Step 3 完成证据

- `0001_long_term_memory.sql` 未改动；迁移初始化改为按版本有序的已批准前缀校验，仅在事务内追加缺失的 `0002_relationship_state.sql`。旧 v1 SQLite 文件可无损升级，未知版本、名称或 checksum 漂移均 fail-closed。
- 新增 `relationship_states` 与 metadata-only `relationship_events`；事件不存放原始消息、prompt、模型回复、provider body 或 key。单调 `event_sequence` 固定回放顺序。
- `SqliteRelationshipRepository` 在单个 `BEGIN IMMEDIATE` 事务内读取当前 state、调用既有确定性 engine、写入 state 与 event；同 request ID/同 fingerprint 返回原事件，任何 scope 或 fingerprint 差异均冲突失败。
- 覆盖作用域隔离、写入回滚、2 秒锁边界、并发写串行化、审计回放与篡改检测、重启后的持久状态，以及 v1 迁移升级。首次缺少模块的红测后，关系与既有 SQLite 定向测试 `34 passed`；全套自动化分两批为 `672 + 576 = 1248 passed`，全量 mypy、ruff、format 与 `git diff --check` 均通过。
- 未接入 DialogueService、FastAPI、Godot 或 provider；未读取 `.env`、调用真实模型、创建项目运行时数据库、复用 F-005 数据/台账/预算、提交或推送。测试仅使用 pytest 临时目录中的隔离 SQLite 文件。

## Step 4 完成证据

- 同一次受限 JSON completion 同时给出正常 `reply` 与内部 `relationship` 建议；只接受精确的 `category + confidence`，所有建议仍由既有确定性 engine 裁决。DeepSeek adapter 使用官方 JSON Output 参数和明确 JSON 指令，未增加第二次模型调用；公开 Dialogue v1 字段和派生 schema 未改动。
- 已接入 `RelationshipService`：仅完成态、未取消且仍为有效 in-flight request 的普通对话才在提交短期回合前原子记录关系。degraded、provider 故障、无效响应、取消、晚到和长期记忆命令不写关系；SQLite 故障使该对话安全失败而非返回未审计的关系变更。
- 新增只读 `GET /api/v1/relationships/{player_id}/{npc_id}?request_id=<optional UUID>`，只返回当前 snapshot 与同 scope/同 request 的 metadata-only 事件摘要；无服务、越权 query 或畸形 scope 均返回无细节的安全错误，未改变 Dialogue v1。
- Godot 对话场景新增低保真只读区域：首次加载 `Relationship: loading…`，成功快照显示 `Affection` 与 `Stage`，正常 completed 对话后按 request 刷新并显示 `Change`/`Reason`；关系请求失败只显示 `Relationship unavailable`，不覆盖对话结果。初始请求与后续刷新使用排队避免竞态丢失。
- `scripts/dialogue_integration.py` 的 10 个 FakeProvider loopback 场景都在短生命周期临时 SQLite 内运行；success 场景已验证 Godot 实际显示 `21/100`、`Acquaintance`、`+1` 和 `rule_friendly`。未读取 `.env`、调用真实模型、复用 F-005 数据/台账/预算、创建项目运行时数据库、提交或推送。

## Step 5 完成证据

- 新增纯内存、无 provider/HTTP/SQLite 依赖的 `RelationshipPolicyEvaluation`。它遍历 `101 × 5 × 4 = 2020` 个基础状态/分类/置信度组合和同等数量的 UTC 冷却组合（合计 4040 次确定性裁决），验证范围、阶段、实际变化、单次上限、饱和、低置信度、neutral 和冷却不变量；另验证 24 个类型混淆、越权字段与提示注入样式建议，以及 2 个 UTC 日界案例，违规数为 0。
- FakeProvider → DialogueService → 只读关系 GET 集成额外覆盖 `score`、`instruction` 与 bool 置信度三类操纵 completion。三者都保留正常 `completed` Dialogue v1 结果、只记录 `candidate_invalid / delta 0` metadata-only 事件并保持初始 20 分；不会让 provider 提供的字段取得规则或分数权限。
- 关系专项测试（领域、评估、Dialogue/API、SQLite）为 `82 passed`；全量 Python 套件因终端单次时限分为 `730 + 526 = 1256 passed`。其中既有 4 writer 并发同 scope 测试仍断言总有效变化仅为 +2。全量 ruff check、67 个源文件的 mypy 和 `git diff --check` 通过，新增/修改 Python 文件的 format 检查通过。所有 SQLite 仅为 pytest 临时目录；未读取 `.env`、调用真实模型、复用 F-005 数据库/台账/预算、提交或推送。

## Step 5 完成条件与停止条件

## Step 6 完成证据

- 使用三个短生命周期、临时 SQLite 的 FakeProvider FastAPI 服务进行黑盒 HTTP QA。关系初始 GET 为 20 分且无事件；普通成功 Dialogue 的公开字段仍精确为冻结的七字段 v1，关系为 `21 / acquaintance / +1 / rule_friendly`；非法关系 query 为 422，其他 player scope 保持初始 20 分；同 request 重放仅产生新的每次 HTTP `trace_id`，其余公开结果一致。
- 单独的 provider completion 携带越权 `score` 字段时，正常 Dialogue 仍为 `completed`，关系 GET 为 `20 / category=null / delta=0 / candidate_invalid`。四个并发正常 completed 请求共享同一 scope 后最终为 22 分，验证只保留一次有效 +2 变化。
- 统一 fake-only 质量入口完成了 ignore/敏感信息预检、lock、ruff、67 文件 mypy、schema、Godot import/unit、9 个连接 loopback 并继续运行对话 loopback；终端受 30 秒回传窗口限制，末行摘要未捕获，但 owned 8000 listener 已自行释放。Step 5 的全量 Python 套件仍为 `1256 passed`；本次黑盒场景未确认产品缺陷。
- 应用内浏览器拒绝访问本机 loopback（`ERR_BLOCKED_BY_CLIENT`），因此本 Step 没有浏览器截图；这属于本次 QA 工具表面的限制，不是产品接口的失败。它不替代、也未提前执行 Step 7 的用户 Godot 窗口 UAT。
- 所有临时服务均已停止，8000/8010/8011/8012 均未监听，正式 `data/cyber-town.sqlite3` 不存在。未读取 `.env`、调用真实模型、复用 F-005 数据库/台账/预算、修改实现、提交或推送。

## Step 6 完成条件与停止条件

## Step 7 完成证据

- 经用户授权的最小 Godot 修复仅将内容间距从 `10` 调整为 `4`、消息输入最小高度从 `96` 调整为 `64`；新增场景契约和 fake 集成几何断言，验证关系原因行不超出固定 640×400 验收视口。未改变关系规则、API 或 Dialogue v1。
- 用户在真实 Godot 窗口、短生命周期 FakeProvider 和临时 SQLite 下重新发送普通消息；截图确认正常 reply、`Affection: 21/100`、`Stage: Acquaintance`、`Change: +1` 及完整可见的 `Reason: rule_friendly`。UAT 通过。
- 最终 `uv run --frozen python scripts/quality.py` 通过：lock、ruff、67 个源文件 mypy、schema、Godot import/unit、9 个连通性 loopback、10 个 fake 对话 loopback、`1257 passed` pytest、ignore/sensitive 复检均成功。交付前审查还补强了未知 Godot reason code 的 fail-closed、关系 request 冲突的 Dialogue v1 409 映射、关系 GET 的 OpenAPI 参数，以及状态表与规则重算审计回放的一致性校验。
- 临时 FakeProvider 已停止、8000 已释放，正式 `data/cyber-town.sqlite3` 不存在；未读取 `.env`、调用真实模型、复用 F-005 资源、提交或推送。仅 Git 交付仍需单独授权。
