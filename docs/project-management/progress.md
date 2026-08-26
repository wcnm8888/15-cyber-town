# 项目进度

## 当前状态

- 生命周期：`git_delivery_authorized / F-007_multi_npc_isolation / pending_commit_push_pr_ci_merge_archive`。
- 当前能力：`origin/main` 仍为已交付的固定 Nia 版本；F-007 独立 worktree 已由 production composition 解析 Nia/Ivo/Rhea，通过完整后端隔离矩阵，并在既有 Godot 场景提供固定 allowlist 选择、全新 conversation、可见状态清空与旧回调抑制。公开 Dialogue v1 不变。
- F-006 交付：功能提交 `f943af4` 已通过 PR #6 合并；当前 `origin/main` 为 `3c2059aad7ef5a1e9dd0154ad49d2b0e93f8f47f`。
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
- F-006 Git 交付已完成：功能提交 `f943af4` 的 PR #6 已通过 GitHub Linux `quality`，并 squash merge 到 `main` / `origin/main` 的 `3c2059aad7ef5a1e9dd0154ad49d2b0e93f8f47f`；任务卡与实施计划已归档。
- 当前 F-007《多 NPC 与隔离》已完成 Step 7；固定视口 P2 和交付前关系 GET allowlist P1 均已关闭，隔离分支为 `feat/f-007-multi-npc-isolation`，用户已授权 Git 交付。持续 fake-only，且不得读取 `.env`、调用真实模型、读取/修改/复用 F-005 验收数据库、台账或预算。
- F-007 Step 0 已完成：F-006 merge SHA 存在于 `origin/main`；既有短期为三元 scope、长期/关系为双元 scope，既有迁移为 `0001` 与 `0002`。用户已确认 Nia、Ivo、Rhea 三 persona 及固定 640×400 Godot 选择契约。
- F-007 Step 1 已完成：以 `origin/main` 的 `3c2059a` 创建干净隔离 worktree 与 `feat/f-007-multi-npc-isolation` 分支；新增不可变 Nia/Ivo/Rhea registry 与两份严格 persona JSON。首次身份边界测试因缺 registry 收集失败；实现后 persona、registry、dialogue application/memory 定向测试共 `86 passed`，ruff、format、mypy 与 diff 通过。API composition、Dialogue v1、迁移、长期记忆、关系、Godot、依赖与 CI 均未修改。
- F-007 Step 2 已完成：红测 `5 failed, 6 passed` 精确暴露 Ivo/Rhea composition 404 与 Nia 降级串扰；实现三 persona composition 和 persona-aware 安全降级后，Step 2 专项 `11 passed`，相关 persona、API、短期/长期/关系回归 `219 passed`，ruff、format、mypy 与 diff 通过。未知 NPC 零 provider/持久化写入，基础三元/双元 scope 隔离通过；Dialogue v1/Schema、迁移、持久化实现、Godot、依赖和 CI 未改。
- F-007 Step 3 已完成：新增 6 组 fake-only 隔离矩阵，覆盖 2 player × 3 NPC × 2 conversation 的短期历史、2 player × 3 NPC 的跨 conversation 长期事实/关系、同 scope replay、跨 scope request ID 冲突、跨 NPC 并发、同 scope 串行和取消抵抗型晚到结果。Step 3 专项 `6 passed`，相关回归 `285 passed`，全量后端 `1277 passed`；ruff、mypy、变更文件 format 与 diff 通过。矩阵首轮即通过，未修改生产实现、公开契约、迁移、持久化、Godot、依赖或 CI。
- F-007 Step 4 已完成：新增 Godot 固定三 NPC registry 与 `OptionButton` 选择行；对话和关系客户端均按活动 NPC 构造 scope，切换时取消/断开旧 HTTP 回调、推进 generation、生成新 conversation，并清空 reply/trace/retry/input/关系状态。首轮 Godot 契约因 registry 缺失失败；loopback 暴露新增选择行导致关系 reason 超出 360px 内容视口，最终将输入最低高度 `64→48` 后通过。统一质量入口通过 1277 pytest、70 文件 mypy、ruff、schema、Godot import/unit、9 健康场景及 10 个既有对话场景 + 1 个 Nia/Ivo/Rhea 切换 loopback。
- F-007 Step 5 已完成：新增纯内存多 NPC 性质评估，覆盖 3 NPC、60 个短期 scope/1770 对、12 个持久 scope/66 对、12 个跨 conversation owner 与 20 个对抗 ID，违规为 0；真实 HTTP 验证 15 个 NPC ID 注入均在 provider/持久化前 404；72 个三 NPC 恶意关系建议全部 `candidate_invalid / delta 0 / score 20`。API scope 篡改、30 次快速 Godot 切换和 6 个 player+NPC 的服务重建回放均零泄漏。新增专项 19 passed、相关回归 101 passed；统一门禁 1296 pytest、73 文件 mypy 及其余既有检查全部通过，未确认产品缺陷。
- F-007 Step 6 已完成：独立 HTTP QA 首轮确认控制空白 `npc_id` 被有损 trim 后绕过 allowlist 的 P1；用户授权后以 7 个失败优先案例修复，29 个 Unicode 空白码点/87 个组合与独立补丁复审均通过。恢复 QA 后，三 persona、短期/长期/关系 scope、重放/冲突、恶意建议、注入、跨 NPC 并发、同 scope 串行、取消晚到、服务重建及 Godot 切换均无未关闭缺陷。最终统一门禁 `1303 passed`，ruff、73 文件 mypy、schema、Godot/loopback、lock 与安全复检通过。
- F-007 Step 7 已完成：首轮真实窗口 UAT 的三 NPC 隔离通过，但两行合法 reply 稳定复现 `Reason` 裁切 P2。失败优先回归为 `bottom=372 / viewport=360`；最小修复将 MessageInput 最低高度 `48→36`、VBox 间距 `4→2`。重新 UAT 确认 Nia/Rhea 两行回复与完整 reason 同屏、Ivo 正常、切换清空及回切 owner 快照；最终统一门禁 `1303 passed`，其余检查全绿。
- F-007 Git 交付前 P1 已关闭：计划审计与黑盒复现确认关系 GET 对未知 NPC 返回 200 初始快照并进入 SQLite read。失败优先专项为 `5 failed, 9 passed`；最小修复在 API 边界复用固定 persona allowlist，扩展后的 13 类非法路径与 3 个合法 NPC 专项 `21 passed`、相关联合回归 `202 passed`，独立补丁复审 `NO FINDINGS`。最终统一门禁 `1319 passed`，ruff、73 文件 mypy、schema、Godot import/unit、9 健康 + 10 对话 + 三 NPC loopback、lock 与安全复检全部通过。
- 未覆盖：远端 GitHub PR/CI/合并与最终归档尚在本次交付中执行；Qdrant/embedding、正式素材和生产部署不在范围。

## 下一批准动作

完成 F-007 可二分提交、推送、PR、GitHub Linux `quality`、squash merge 与最终文档归档；不进入 R-08 或部署。
