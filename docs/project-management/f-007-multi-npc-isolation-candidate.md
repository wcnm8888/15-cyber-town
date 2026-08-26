# 任务卡：F-007 多 NPC 与隔离

状态：`git_delivery_authorized / pending_commit_push_pr_ci_merge_archive`。

来源：已批准路线图的 `R-07`。用户已授权并完成 Step 0—7，且已授权 Git 交付。

## 用户目标与可见价值

玩家可在同一低保真 Godot 对话入口中选择 2–3 个固定 NPC，并与各自稳定的人格对话。切换 NPC 后，玩家只会看到该 NPC 的对话、长期记忆和好感度；任何 player、NPC 或 conversation 之间均不得串扰。

## 已锁定范围

- 保留既有 `neon_guide / Nia`，总数扩展至 2–3 个固定、版本化 persona；每个 persona 具有不可变 `npc_id`、显示名、版本和 system prompt 文件。
- 现有短期 scope 保持 `player_id + npc_id + conversation_id`；长期记忆和关系状态保持 `player_id + npc_id`。所有读、写、重放、幂等、错误路径和 Godot 刷新必须完整携带相应 scope。
- Godot 仅在既有 `dialogue.tscn` 中增加一个低保真 NPC 选择/进入入口和活动 NPC 标识。选择另一个 NPC 必须建立独立 conversation，不得复用或展示前一 NPC 的 reply、trace、retry 上下文、关系快照或输入冻结状态。
- 自动化、独立 QA、loopback 与用户 UAT 一律使用 FakeProvider、临时 SQLite 和本地 loopback；测试 persona 不得触发真实模型调用。
- 复用 F-006 的既有确定性关系、F-005 的长期记忆和 F-004 的短期记忆机制，只能在已批准的项目正式 SQLite 真相源上验证已有 scope 语义；不得读取、修改、删除或复用 F-005 的验收数据库、调用台账或预算。

## 明确非目标

- NPC 自主对话、NPC—NPC 关系或社交图谱、多 Agent 调度、工具调用、WebSocket、交易、任务、礼物、权限/登录体系。
- 真实模型评估、`.env`/API key 读取、真实调用预算、生产数据库、外网服务、部署或正式发布。
- 正式美术、像素素材、动画重做、复杂角色选择页、Figma 以外的正式视觉资产。
- 修改冻结的 `DialogueRequestV1`、`DialogueResponseV1`、`ApiErrorV1` 或其 JSON Schema；不为多 NPC 新增公开 v2 API。

## Step 0 已锁定决策

用户已于 2026-08-26 确认下列产品决策。它们构成 Step 1 的冻结输入，变更须先更新任务卡并重新取得用户授权：

1. **固定人数与身份。**固定 3 个 NPC：`neon_guide / Nia / nia-v1 / nia_v1.json`、`signal_archivist / Ivo / ivo-v1 / ivo_v1.json`（克制的档案管理员）与 `night_courier / Rhea / rhea-v1 / rhea_v1.json`（务实的夜班信使）。三者均沿用现有严格 persona JSON schema、不可变 id/version 与无工具/无状态声称边界。
2. **选择交互。**采用固定 640×400 低保真选择契约：在现有 `dialogue.tscn` 的 `TitleLabel` 下、`StatusLabel` 上新增一行 `OptionButton`，标签为 `NPC`，选项只来自固定 allowlist。默认 Nia；切换时禁用选择与发送直至旧请求失效、生成全新 `conversation_id`、清空旧 NPC 的 reply/trace/retry/输入/关系快照，再显示新 NPC 名称和该 NPC 的 `Relationship: loading…`。不新增场景、素材或正式美术。
3. **启动默认值（已锁定）。**继续进入 Nia；未识别/未批准 `npc_id` 沿用既有安全拒绝路径，不自动回退到其他 NPC。
4. **数据迁移（已锁定）。**不迁移、复制或合并旧 Nia 数据；历史 Nia 数据仍归 Nia，新 NPC 首次读取各自返回确定性空/初始状态。若需要预置数据或 ID 改名，必须另起迁移决策。

## 隔离与失败合同

- 任意 `player_id`、`npc_id` 或 `conversation_id` 不同，均不得共享短期历史、长期事实、关系分数/事件、请求幂等结果、retry payload、Godot 可见 reply/trace 或缓存快照。
- 相同 player + NPC 但不同 conversation：可通过既有长期记忆/关系看到同一持久状态，但短期历史、请求 ID 和 retry 上下文仍严格独立。
- 相同 player + conversation 但不同 NPC：必须视为不同短期 scope；若请求或客户端状态无法表达该组合，fail-closed，不静默重用状态。
- 取消、超时、无效 provider 响应、degraded/local fallback、SQLite 故障、未知 NPC、并发锁超时和晚到结果均不得向任何 NPC 写入记忆或关系，且不得污染另一个 NPC 的 UI。
- persona system prompt 永远只由当前已批准的 NPC 决定；其他 NPC 的 persona、长期事实、关系 reason 或历史不得进入 provider request、日志或错误响应。

## 最小视觉契约（Step 0 已批准）

- 页面：继续复用 `game/scenes/dialogue.tscn`，不新增正式场景或素材。
- idle：可见当前 NPC 名称和选择入口；默认 Nia 的现有文本、关系初始快照与发送体验不回归。
- 切换：显示选中的 NPC 名称及其独立 `Affection`/`Stage`；前一 NPC 的 reply、trace、change、reason 和 Retry 不可见。
- loading/error：只作用于当前选中 NPC；切换期间控制件不得允许把旧请求结果渲染到新 NPC。
- 验收：先提供固定桌面视口的低保真截图/视觉契约供用户确认；自动化测试不替代用户视觉验收。

## 测试与验收矩阵

| 风险 | 最低验证 |
| --- | --- |
| persona registry | 固定 allowlist、ID/版本/文件唯一性、未知 NPC fail-closed、每个 persona system prompt 仅一次 |
| 短期隔离 | `player × npc × conversation` 矩阵；同 NPC 的连续对话保留，任一维变化均零泄漏 |
| 长期/关系隔离 | `player × npc` 矩阵；跨 conversation 保留、跨 NPC/玩家零泄漏、初始状态不写入 |
| 幂等与并发 | 同 scope replay 一致；不同 NPC 并发互不阻塞；同 scope 锁/取消/晚到不重复写且不影响相邻 NPC |
| provider 边界 | FakeProvider 捕获请求，断言 persona、历史、长期事实和受限关系建议只属于当前 NPC |
| API 兼容 | Dialogue v1/schema 不变；关系 GET 仅返回请求 path 对应 NPC 的 snapshot/event |
| Godot | 选择、切换、加载、失败、retry、旧回调抑制、关系刷新以及 2–3 NPC 可见性；真实 HTTPRequest → FastAPI → FakeProvider → 临时 SQLite loopback |
| 对抗/QA/UAT | scope 篡改、NPC ID 注入、并发切换、恶意建议、跨窗口/重启；独立 fake-only QA 和用户 Godot UAT |

## 候选阶段地图

| Step | 内容 | 进入条件 |
| --- | --- | --- |
| 0 | 锁定任务卡、F-006 合并事实、persona 身份与最小视觉契约 | 已完成 |
| 1 | persona registry、失败优先配置/身份边界 | 已完成 |
| 2 | 后端 persona 解析与基础 scope 隔离回归 | 已完成 |
| 3 | 短期/长期/关系、幂等和并发隔离矩阵 | 已完成 |
| 4 | 已确认的 Godot 选择入口和 fake loopback | 已完成 |
| 5 | fake-only 对抗、性质评估与隔离回放 | 已完成 |
| 6 | 独立 fake-only QA | 已完成 |
| 7 | 用户 Godot + FakeProvider UAT、最终本地门禁 | 已完成 |
| Git 交付 | commit、push、PR、CI、合并和归档 | 用户另行授权 |

## Step 0 基线核对与停止条件

- 已只读确认 F-006 最终 squash-merge SHA `3c2059aad7ef5a1e9dd0154ad49d2b0e93f8f47f` 存在于 `origin/main`；当前本地工作目录仍处于历史 `feat/f-006-deterministic-affection`，HEAD 为功能提交 `f943af4`。本 Step 未切换、创建或修改 Git 分支；F-007 也尚无实现分支。
- 已确认既有后端 scope：短期 `player_id + npc_id + conversation_id`、长期记忆/关系 `player_id + npc_id`；关系 SQLite 迁移仅有既有 `0001_long_term_memory.sql` 与 `0002_relationship_state.sql`，本 Step 不修改迁移、数据库或代码。
- 已确认既有 640×400 Godot 对话视口为单列 `VBox`，`dialogue_client.gd` 与 `relationship_client.gd` 当前均固定 Nia。上述候选选择契约明确要求后续实现消除该固定值、使用 allowlist 且隔离旧回调；本 Step 未作任何实现性改动。

Step 0—7 已完成，用户已授权 Git 交付。交付期间只允许提交、推送、PR、远端 CI、合并和归档；仍禁止修改公开契约或迁移，禁止读取 `.env`、调用真实模型或访问/复用 F-005 验收资源。若用户要求多 NPC 以外的自主行为、真实模型、身份权限、正式 UI、数据迁移或部署，立即停止并要求新的架构与范围裁决。

## 本次起草记录

- 起草阶段仅创建本候选任务卡；随后用户于 2026-08-26 授权进入 Step 0。
- Step 0 仅完成文档与只读基线核对；未创建分支，未修改实现、配置、测试、SQLite、Godot、依赖或 CI。
- 用户已确认固定 3 个 NPC（Nia、Ivo、Rhea）及固定 640×400 Godot 选择契约；Step 0 完成，等待单独的 Step 1 授权。
- 用户已授权 Step 1。创建隔离 worktree `E:\Agent\comprehensive-cases\15-cyber-town-f007` 与分支 `feat/f-007-multi-npc-isolation`，其干净基线为 `origin/main` 的 `3c2059aad7ef5a1e9dd0154ad49d2b0e93f8f47f`；原文档工作目录未被带入功能分支。
- 首轮 `test_persona_registry.py` 按预期因 `BUNDLED_PERSONA_FILENAMES`/`load_bundled_personas` 尚不存在而收集失败。实现后新增不可变三 NPC allowlist、Ivo/Rhea 严格 JSON persona 资产和未知 `npc_id` 在 provider/记忆之前 fail-closed 回归；`test_persona.py`、`test_persona_registry.py`、`test_dialogue_application.py`、`test_dialogue_memory.py` 共 `86 passed`，定向 ruff、format、mypy 与 `git diff --check` 通过。
- Step 1 未修改 API composition、Dialogue v1/Schema、SQLite migration、长期记忆、关系、Godot、依赖或 CI；未读取 `.env`、调用真实模型、访问 F-005 验收资源、提交、推送或创建 PR。
- 用户已授权 Step 2。首轮 `test_multi_npc_dialogue.py` 为 `5 failed, 6 passed`：生产 composition 只装配 Nia，Ivo/Rhea 返回 404，内容过滤降级均错误显示 Nia；未知 NPC 与三元 scope 基础隔离已通过。
- composition 现装配不可变三 persona registry；内容过滤降级按已校验 persona 的显示名生成，Nia 原有文案保持不变。新增 fake-only 临时 SQLite 回归验证三 persona 的 Dialogue v1、prompt/version/npc_id、任一短期 scope 维变化零历史、未知 NPC 零 provider/记忆/关系写入，以及长期/关系双元 owner 隔离。
- 实现后 Step 2 专项 `11 passed`；persona、composition、Dialogue API、短期/长期/关系定向回归共 `219 passed`，ruff、format、mypy 与 `git diff --check` 通过。未修改 Dialogue v1/Schema、SQLite migration、长期记忆/关系持久化、Godot、依赖或 CI；未读取 `.env`、调用真实模型、访问 F-005 验收资源、提交、推送或创建 PR。
- 用户已授权 Step 3。新增独立 `test_multi_npc_isolation_matrix.py`，覆盖完整短期三维矩阵、长期/关系二维矩阵及跨 conversation 保留、request replay/跨 scope 冲突、跨 NPC 并发、同 scope 串行和取消抵抗型晚到结果对相邻 NPC 的隔离。
- Step 3 新增 6 组矩阵首轮全部通过，既有生产实现无需修改；相关回归 `285 passed`、全量后端 `1277 passed`，ruff、mypy、变更文件 format 与 `git diff --check` 通过。全仓 format check 仅报告 3 个无关既有基线文件，未越界修改。未修改 Dialogue v1/Schema、SQLite migration、持久化实现、Godot、依赖或 CI。
- 用户已授权 Step 4。新增 Godot 固定三 NPC registry 与低保真 `NPC` + `OptionButton` 选择行；默认 Nia。对话与关系客户端切换时断开/取消旧 HTTP 请求、推进 generation、生成全新 conversation，并清空 reply、trace、retry、input、关系 snapshot/event。
- Godot 失败优先契约首轮因 `npc_registry.gd` 缺失而失败；实现后 unit 通过。真实场景 loopback 首轮发现新增选择行使关系 reason 底部超出 360px 内容视口，最终将 MessageInput 最低高度由 64 调整为 48 后通过。Nia、Ivo、Rhea 依次选择/发送/关系刷新均通过，三次 conversation 均不同、persona prompt 各自匹配且 provider history 均为空。
- Step 4 最终统一质量入口通过：1277 pytest、ruff、70 文件 mypy、schema、Godot import/unit、9 健康 loopback、10 个既有 fake 对话场景 + 1 个三 NPC 切换场景、lock 与 ignore/sensitive 前后复检。未修改 Dialogue v1/Schema、SQLite migration、持久化、依赖或 CI。
- 用户已授权 Step 5。新增纯内存 `multi_npc_evaluation`，对 3 NPC、60 个短期 scope/1770 个不同 scope 对、12 个持久 scope/66 个不同 scope 对、12 个跨 conversation owner 与 20 个对抗 NPC ID 做性质枚举，结果 0 违规。
- 新增真实 API/SQLite 对抗：15 个路径/大小写/同形字/控制字符 NPC ID 均 404，零 provider 与零持久化；复用 request ID 篡改 NPC 返回 409，关系 request event 对跨 NPC/玩家查询保持 null；24 种恶意关系 suggestion × 3 NPC 共 72 项全部记录 `candidate_invalid / delta 0 / score 20`。
- 新增 30 次 Godot 快速切换性质测试，所有旧 generation reply/trace/retry 均保持 inert；使用同一临时 SQLite 重建服务后，2 player × 3 NPC 的长期事实与关系回放只归原 owner，新的短期 history 均为空。Step 5 新增 19 passed、相关回归 101 passed，统一门禁 1296 pytest、73 文件 mypy、ruff、schema、Godot/loopback、lock 与安全复检通过，未确认产品缺陷。
- 未读取 `.env`、调用真实模型、访问 F-005 验收数据库/台账/预算、提交、推送或创建 PR。
- 用户已授权 Step 6。独立 HTTP QA 首轮确认 `npc_id="night_courier\t"` 会在 persona allowlist 前被规范化为合法 ID、返回 200 并调用 FakeProvider，定级 P1；按停止合同中止余下 QA，未自行修复。
- 用户随后单独授权修复。新增 7 个首尾空格、ASCII 控制空白与 Unicode 空白边界案例，修复前 `7 failed`、修复后 `7 passed`；请求侧只对 `npc_id` 保持原值并拒绝有损规范化，不改变 `player_id`、message trim、干净未知 ID 的 404 或 Dialogue v1 JSON Schema。29 个 Unicode 空白码点/87 个边缘组合全部拒绝，合法三 NPC 与通用 `npc-1` 保持兼容，独立补丁复审为 `NO FINDINGS`。
- 用户重新授权继续 Step 6。独立短生命周期 HTTP QA 验证三 persona prompt、短期三元 scope、2 player × 3 NPC 长期/关系双元 scope、同请求重放、跨 scope 冲突、恶意建议、6 个注入 ID、不同 NPC 最大 2 并发、同 scope 最大 1 并发及同库服务重建后的 6 scope 回放；全部业务断言通过。取消抵抗型晚到/相邻 NPC 专项 `2 passed`，Godot unit 及 10 个既有 fake 场景 + 三 NPC 切换 loopback 通过。
- Step 6 最终统一质量入口通过：`1303 passed`、ruff、73 文件 mypy、schema、Godot import/unit、9 健康 loopback、10 个对话 loopback + 三 NPC 切换、lock 与 ignore/sensitive 复检。P1 已关闭，未确认其他产品缺陷；8000 已释放、正式运行时数据库不存在。两个纯合成 QA SQLite 因 Windows 句柄/执行策略未清理，均不在项目正式路径且未读取其内容。
- 用户已授权 Step 7。真实 640×400 Godot + FakeProvider 窗口依次验证 Nia、Ivo、Rhea：每次切换均清空旧 reply、trace、input 和关系 event，新 NPC 从自己的 `20/100` 开始；各 NPC 收到对应 synthetic reply 与独立 `+1 / rule_friendly`，回切 Nia 时仅保留其 `21/100` 快照并以新 conversation 继续。
- 回切 Nia 的合法两行 synthetic reply 稳定把底部 `Reason` 推出 360px 内容视口，仅剩顶部像素；最小复现为固定视口、任一 NPC 已有关系后显示约 74 字符的两行 reply。期望 `Reason` 完整可读，实际不可读；影响所有 NPC 的较长合法回复，定级 P2。未修改功能实现、未运行最终本地门禁，Step 7 停止并等待单独修复授权。UAT 服务已停止、8000 已释放、正式运行时数据库不存在；隔离 UAT SQLite 保留在项目正式路径之外。
- 用户单独授权最小视口修复与重新 UAT。将 `success` fake loopback 固定为同一条两行回复后，修复前稳定失败为 `bottom=372 / viewport=360`；消息输入最低高度 `48→36` 只将其降到 366，最终同时把 VBox 间距 `4→2` 后通过。Godot unit 与 10 个既有对话场景 + 三 NPC loopback 均通过。
- 重新真实窗口 UAT 使用全新隔离 SQLite：Nia 与 Rhea 的两行回复均和完整 `Reason: rule_friendly` 同屏，Ivo 单行路径正常；每次切换清空旧 reply/trace/input/event，回切 Nia 只保留其 `21/100` owner 快照。最终统一门禁通过：`1303 passed`、ruff、73 文件 mypy、schema、Godot import/unit、9 健康 loopback、10 对话 loopback + 三 NPC 切换、lock 与 ignore/sensitive 复检。Step 7 完成；用户随后已授权 Git 交付。
- Git 交付前计划审计、黑盒复现和专项审查一致确认关系 GET 对未批准 `npc_id` 会进入 repository read 并返回 `200 / 20` 初始快照，违反非法 NPC 必须在持久化前 fail-closed 的合同，定级 P1；交付在提交前暂停。用户授权最小修复后，API 边界复用同一不可变 persona allowlist，13 类未知/大小写/空白/控制/路径/同形字 ID 均在 repository 前拒绝，Nia/Ivo/Rhea 保持 `200`。红测 `5 failed, 9 passed`，修复后扩展专项 `21 passed`、相关联合回归 `202 passed`，独立补丁复审 `NO FINDINGS`；最终统一门禁 `1319 passed` 且其余检查全绿。
