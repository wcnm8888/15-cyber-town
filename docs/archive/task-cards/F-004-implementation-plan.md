# 已归档实现计划：F-004 短期会话记忆与上下文预算

状态：`completed / archive_prepared_in_PR_4`。

本计划只服务于已归档的 [`F-004 任务卡`](F-004-short-term-memory-context-budget.md)。Step 0–7、真实多轮评估、独立 QA、用户真实 Godot 窗口 UAT、fake-only 最终门禁及首轮 GitHub Linux CI 均已完成；统一交付载体为 GitHub PR #4，归档 HEAD 的最终 CI 与合并事实以 GitHub 为准，不得进入 R-05。

## Step 地图

| Step | 当前状态 | 授权后的范围 | 主要验证与停止条件 |
| --- | --- | --- | --- |
| Step 0 | `completed` | 落盘批准的 F-004 任务卡与本计划；只读复核 Git、公开契约、工具、provider、幂等与 Godot 会话行为 | 只修改两份项目管理文档；不建分支、不装依赖、不读取 `.env`/key、不调用模型 |
| Step 1 | `completed` | 从最新 `main` 创建 F-004 分支；冻结 scope、6 回合、128 sessions、1800 秒 TTL、8192 预算和 2 秒等待，编写失败优先负例 | 配置 142 passed；全量 366 passed；无新增依赖、store、adapter、Godot 或真实调用 |
| Step 2 | `completed` | 失败优先实现进程内 session store、完整 turn、三元 scope、TTL、容量与 LRU | store 102 passed；全量 468 passed；scope/TTL/LRU/在途保护/失败不写通过，未接入 provider |
| Step 3 | `completed` | 实现 provider-neutral history、UTF-8 固定开销预算、整回合裁剪、fake/SDK stub 适配与幂等/并发 | 专项联合 388 passed；全量 545 passed；唯一 system、2 秒 scope 串行、全局并发≤2、取消/晚到不写 |
| Step 4 | `completed` | FastAPI → FakeProvider 多轮与 Godot fake loopback、恢复、隐私、门禁和当前事实文档同步 | 专项 17 passed；全量 562 passed；9 健康 + 10 fake 对话 loopback；公开 v1/Schema 和原有场景不变 |
| Step 5 | `completed` | 单独授权的真实 DeepSeek 多轮上下文、作用域隔离、预算与角色稳定评估 | 实际 8 次；后续 7 次 6326 输入/86 输出 tokens、USD 0.00289696 上界；首次失败请求 usage 无法追溯并已披露 |
| Step 6 | `completed` | 独立 QA 从任务卡重建负例并复核 scope、预算、并发、取消、隐私和 fake 集成 | 7 个 P1/P2 负例先红后绿；后端 412 passed、Godot/API 22 passed；双方 NO FINDINGS，全量 569 passed |
| Step 7 | `completed / user_uat_passed` | 用户真实窗口多轮 UAT、空历史虚构记忆失败优先修复、调用台账和最终本地审查 | 已记录 8 次/USD 0.00112684 并披露原调用上限超额；修复后用户真实 Godot 窗口明确“不知道”，`FAKE_PROVIDER_CALLS=0`，完整门禁 584 passed |
| Git 交付 | `archive_prepared_in_PR_4` | 已获授权精确提交、push、PR、首轮 fake-only CI 和同 PR 归档 | 功能提交 `eb8a9cc`；首轮 Linux CI 通过；最终归档 HEAD 的 CI 和合并事实以 GitHub PR #4 为准 |

## Step 0 完成证据

- 分支为 `main`；HEAD、`main`、`origin/main` 均为 `5ea85a3ec39cdd3df64f39626dfaf3b238305a24`；执行前工作树、staged 和 untracked 均为空，`origin` 正常。
- Python `3.12.10`、uv `0.6.14`、Godot `4.7.2.stable.official.ed1daf0bf` 已本地验证；没有安装软件、修改 PATH 或访问模型服务。
- 公开 `DialogueRequestV1` 已有 `request_id`、`player_id`、`npc_id`、`conversation_id`、`message`；response、error 和 3 份派生 Schema 不需要改变。
- `ProviderRequest` 与 DeepSeek adapter 当前仅传 persona system + 当前 user，应以 SDK-neutral history DTO 扩展内部 messages。
- DialogueService 已有 600 秒/256 项幂等、请求共享、失败清理、provider 全局并发 2、12 秒 deadline 和 completed/degraded 分类；尚无 session store、历史、预算或 scope 串行。
- Godot 每个窗口只创建一次 conversation ID，新 Send 创建 request ID，Retry 复用冻结 JSON；默认无需新页面。
- FastAPI、Pydantic、OpenAI SDK 与 Uvicorn 依赖已具备；禁止新增 tokenizer、数据库依赖和 SDK。
- 现有记忆规划提及未来 SQLite，但 F-004 已明确为纯内存；相关规划及过期状态摘要留待获批的后续文档 Step 更新。
- Step 0 唯一允许修改 `current-task.md` 与 `implementation-plan.md`；没有读取 `.env`、key、玩家原文、模型回复或 persona prompt 内容。

## Step 1 已批准范围：分支、冻结配置和失败优先测试

已按用户明确授权执行：

1. 只读复核仍位于 `main`，HEAD、`main`、`origin/main` 未漂移，staged/untracked 为 0，工作树只有 Step 0 两份已批准文档修改。
2. 从最新 `main` 创建并检出 `feat/f-004-short-term-memory-context-budget`，完整保留 Step 0 修改；不 reset、clean、覆盖或提交。
3. 先编写会失败的配置/策略负例，覆盖三元 scope、turns=6、sessions=128、TTL=1800、budget=8192、envelope=64、message overhead=16、reply reserve=256、scope wait=2 秒，以及非正数、漂移、错误类型。
4. 仅在必要时扩展 `backend/src/cyber_town/config.py` 与 application 冻结配置 DTO；维持 provider 默认 disabled、自动化禁用 dotenv、F-003 冻结参数和公开契约。
5. 不新增依赖，不修改 `pyproject.toml`、`uv.lock`、真实 `.env`、派生 Schema、Godot 场景或 SDK 隔离边界。
6. 运行定向测试、既有统一质量入口、lock、schema、ignore、sensitive 和 `git diff --check`；永久 fake-only，不读取真实 key 或调用模型。
7. 只同步 Step 1 必要任务卡与计划状态；完成后停止，等待 Step 2 明确授权。

Step 1 不实现 store、LRU/TTL 执行逻辑、预算计算、history adapter、多轮 API/Godot、独立 QA、UAT 或 Git 交付。基线漂移、需要新增依赖、调整公开契约、读取 `.env` 或改变批准常量时停止。

## Step 1 完成证据

- 功能分支为 `feat/f-004-short-term-memory-context-budget`，基线 HEAD / `main` / `origin/main` 均为 `5ea85a3ec39cdd3df64f39626dfaf3b238305a24`，Step 0 文档完整保留，未提交或暂存。
- 第一轮配置红灯 94 failed / 38 passed；补充整数伪装浮点和 NaN/Infinity 后另有 10 个失败优先负例，合计增加 104 个 F-004 配置与边界测试。
- `Settings` 增加三元 scope 与 8 个冻结数值配置：6、128、1800、8192、64、16、256、2 秒；scope 缺失/错序/重复、数值漂移、非正值、bool、整数伪装浮点和非有限等待全部 fail-closed。
- 批准值可从正常环境变量字符串解析，provider 默认 disabled 与自动化 dotenv 禁用保持原状；response reserve 固定为既有 `llm_max_tokens=256`。
- 配置定向 pytest 142 passed；2 个文件 ruff/format 通过，mypy 2 source files 通过。
- 完整 `uv run --frozen python scripts/quality.py` 通过：lock 45 packages、ruff、mypy 35 files、schema、Godot import/unit、9 个健康 loopback、8 个 fake dialogue loopback、pytest 366 passed、ignore/sensitive preflight/final。
- 未新增依赖或修改 `pyproject.toml` / `uv.lock`；未实现 store、TTL/LRU、预算计算、provider 消息适配、Godot 改动；未读取真实 `.env` / key、调用真实模型、提交、push 或进入 R-05。

## Step 2 计划：有界会话存储

先证明 store 缺失导致 scope、turn、TTL/LRU 和容量测试失败，再实现进程内 `ConversationScope`、完整 `ConversationTurn` 和 session store。使用可注入单调时钟覆盖 1800 秒边界、最近 6 回合、128→129 session、过期优先、LRU、在途保护和满载 fail-closed。

未知 NPC、失败请求与 degraded 不产生有效历史；不同玩家、NPC、conversation 完全隔离。不修改 DeepSeek adapter、Godot、公开 Schema、依赖或真实 provider。

## Step 2 完成证据

- 失败优先：新增独立 store 测试后，首次运行因 `ModuleNotFoundError: No module named 'cyber_town.application.memory'` 在收集阶段失败。
- 新增 `backend/src/cyber_town/application/memory.py` 和 `backend/tests/test_short_term_memory.py`；没有修改 provider、application 编排、FastAPI、Godot、公开契约、依赖或 Step 1 配置。
- 冻结的 `ConversationScope(player_id, npc_id, conversation_id)` 验证三元完整性、字符串预算和 UUID 类型；不同 player/NPC/conversation 相互隔离。
- 冻结的 `ConversationTurn` 必须一次包含完整 user/assistant，遵守 1000/4000 字符边界，repr 隐藏双方正文；`begin → commit / abort` 保证只有成功 commit 写入，失败/取消/degraded 不产生伪回合。
- `ShortTermSessionStore` 固定 6 完整 turns、128 sessions、1800 秒 idle TTL；可注入单调时钟覆盖 1799/1800/1801 秒、访问刷新、过期优先、确定性 LRU、在途不可驱逐、满载 `SessionCapacityError` 及释放后恢复。
- store 定向 102 passed；store + 既有配置联合 244 passed；新增 2 个 Python 文件 ruff、format、mypy 均通过。
- 统一 fake-only 门禁通过：pytest 468 passed、lock 45 packages、mypy 37 files、ruff、schema、Godot import/unit、9 个健康 loopback、8 个 fake dialogue loopback、ignore/sensitive preflight/final。
- store 未接入 `DialogueService` 或 API，不计算上下文预算、不构造 history messages、不修改 provider/Godot，不读取 `.env` 或 API key，不调用真实模型，不提交或推送。

## Step 3 计划：预算、多消息和一致性

失败优先冻结 `ProviderHistoryMessage(role, content)`、`ProviderRequest.history_messages=()`、唯一 system、交替完整 user/assistant 历史和 UTF-8 预算：

```text
64 + system(16 + UTF-8 bytes)
   + selected history Σ(16 + UTF-8 bytes)
   + current user(16 + UTF-8 bytes)
   + reserved reply 256 <= 8192
```

以最新完整 turn 优先选择、旧到新发送，覆盖中文、emoji、恰好上限、超 1、当前消息超限、persona 最小预算不足和半回合拒绝。

组合现有 request 幂等：同 scope 不同请求全程串行、最多等待 2 秒；同 ID 并发共享；不同 scope 并发但全局 provider≤2；成功只写一次，失败、degraded、取消和晚到不写。仅 synthetic SDK stub，禁止 `.env` 和真实网络。

## Step 3 完成证据

- 失败优先：新建历史/预算/编排负例并扩展 adapter 测试后，pytest 在实现前因 `context_budget` 缺失和 `ProviderHistoryMessage` 无法导入出现 2 个预期收集错误。
- `ProviderHistoryMessage` 为 SDK-neutral、不可变、正文脱敏 DTO；`ProviderRequest.history_messages=()` 保持 F-003 向后兼容，严格拒绝 system/developer/tool、非法类型、半回合与错误顺序，adapter 对篡改 role 再次 fail-closed。
- `context_budget.py` 固定 `64 + system(16 + UTF-8 bytes) + history Σ(16 + UTF-8 bytes) + current(16 + UTF-8 bytes) + 256 <= 8192`；覆盖中文、emoji、组合字符、恰好上限、超 1 及整回合淘汰，不使用 tokenizer。
- provider 始终发送唯一 persona system、从旧到新的完整 user/assistant 历史和当前 user；历史正文不会出现在 repr、日志、异常或公共契约。
- DialogueService 使用原有三元 scope store；同 scope 全事务串行、最多等待 2 秒，不同 scope 并发但 provider 全局≤2；容量、失败、degraded、Retry、replay、冲突、TTL 与最近 6 回合保持已批准语义。
- 新增等待者计数与孤儿清理；同 ID 共享只调用/写入一次，部分等待者取消不影响合法请求，所有等待者取消或 provider 忽略取消后晚到均不产生伪记忆，并释放 scope/store/provider 资源。
- 历史/预算/adapter/application 定向 144 passed；再加 store 与配置联合 388 passed；ruff、ruff format、mypy 定向通过。
- 统一 fake-only 门禁通过：pytest 545 passed、lock 45 packages、mypy 40 files、ruff、schema、Godot import/unit、9 个健康 loopback、8 个现有 fake dialogue loopback、ignore/sensitive preflight/final。
- 未修改公开 v1/Schema、`pyproject.toml`、`uv.lock`、FastAPI 路由/composition、Godot 或既有配置；未读取 `.env`/API key、调用真实 provider、提交、push 或进入 Step 4/R-05。

## Step 4 计划：fake 多轮集成与文档事实

使用 FastAPI + FakeProvider 验证多轮记忆、scope 隔离、turn 裁剪、422/503/502/504、手动恢复和幂等；扩展真实本地 Godot HTTPRequest → FastAPI → FakeProvider loopback，不接入真实 provider。

默认复用既有 Godot 场景与 client；确需修改时先申请范围扩展。实现完成后，再同步 README、项目 AGENTS、docs 地图、architecture、memory-design、evaluation-strategy、testing-strategy、ADR、roadmap、progress 和 evidence 中已经变化的事实；明确纯内存、重启丢失、工程估算与 fake-only。

## Step 4 完成证据

- 失败优先：新增 FastAPI fake 多轮和 harness 合约测试后，首次收集因 `KeyError: 'MEMORY_SCENARIOS'` 失败，确认真实 Godot 多轮场景尚未实现。
- 新增 `test_dialogue_memory_api.py` 和 `test_dialogue_memory_integration.py`；17 个专项覆盖三元 scope、8 次 HTTP 连续对话/6 回合裁剪、422/503/502/504、degraded、成功 replay、409 conflict、手动恢复、历史递增及 ghost turn 检测。
- 只扩展 `scripts/dialogue_integration.py` 与既有 `game/tests/run_dialogue_fake_integration.gd`；真实本地 Godot → FastAPI → FakeProvider 从 8 增至 10 场景，新增 `multi_turn` 与 `multi_turn_recovery`，分别执行 3/4 次离线 fake 调用。
- 真实 loopback 验证同窗口 conversation_id 稳定、每次 Send 新 request_id、手动 Retry 冻结 payload、完整历史计数 `(0,2,4)` 与 `(0,2,2,4)`、失败不写入及 8000 端口释放；原 Godot 场景和客户端零改动。
- 已同步 README、项目 AGENTS、docs 地图、architecture、memory-design、evaluation-strategy、testing-strategy、ADR-014、roadmap、progress、evidence 与当前任务状态；修正 F-003 遗留的无活动任务、未进入 R-04、无短期记忆与当前仅 8 对话 loopback 等过期摘要。
- 全量 pytest 562 passed，mypy 42 files，lock 45 packages、ruff、schema、Godot import/unit、9 健康 + 10 对话 loopback、ignore/sensitive 和 F-004 修改文件格式检查均通过；统一入口和 CI 永久 fake-only。
- 未修改公开 Dialogue v1/Schema、Godot 场景/客户端、依赖、FastAPI 路由、CI workflow 或模型参数；未读取 `.env`/API key、调用真实 provider、产生费用、提交、push 或进入 Step 5/R-05。

## Step 5 计划：真实多轮评估

须先取得独立真实联网、API key 使用、调用次数和费用授权；应用只能经已有 Settings 读取 Git 忽略 `.env`，不得输出、保存或提交 key、prompt、玩家消息、模型回复。

最多 8 次/USD 0.035；验证同 scope 记忆、跨 scope 隔离、裁剪后 persona 和实际 provider usage/费用，尽量复用真实 Godot 调用。认证/余额/网络异常、模型/价格漂移、额度超限、隐私泄漏或角色/隔离失败时立即停止；精确记录请求、prompt/completion tokens 与费用。

## Step 5 完成证据

- 用户明确批准 Step 5 真实 provider、API key、最多 8 次/USD 0.035，并在首次断言失败后另行批准调整验收流程；项目 `.env` 只由现有 Settings 在专项进程中读取，SDK 零自动 retry。
- 第一次真实请求因语义断言先于 usage 输出而退出；该请求计入 8 次上限，但其官方 prompt/completion tokens 与费用无法追溯。后续修正为 provider 一返回就打印脱敏 usage，全部 7 次均有完整 token 台账。
- 7 次已记录请求的官方 usage 合计 6326 prompt tokens 与 86 completion tokens；按官方峰值 cache-miss USD 0.44/百万输入和 USD 1.32/百万输出，已记录部分费用上界 USD 0.00289696。首个失败请求不包含在此金额，不声称已知 8 次完整总费用。
- 真实 FastAPI → DialogueService → DeepSeek 通过同 scope 召回、新 conversation 隔离、同 conversation 不同 player 隔离、裁剪后 Nia persona、后续召回和 6 完整回合容量；HTTP 幂等 replay 零额外真实调用。
- 为节约模型预算，裁剪专项只在验收进程中预置 2 个合成完整回合，再以真实 provider 请求确认仅最新完整回合入选；公开契约、Godot 场景、产品代码和磁盘均不修改。
- SDK 初始化遵循 README：仅从当前验收进程移除 SOCKS `ALL_PROXY`，保留 HTTP/HTTPS 代理；脱敏 audit 不含 API key、system prompt、历史、玩家正文或模型回复。
- Step 5 已用尽 8 次专项调用额度；Step 6 必须 fake-only，Step 7 若获授权仍最多 4 次/USD 0.015，且必须在语义断言前逐次记录 usage。

## Step 6 计划：独立 QA

独立审查重建 scope collision、跨 player/NPC/conversation 泄漏、system 注入、非法 history role、UTF-8 低估、半回合、TTL/LRU 边界、129th session、在途驱逐、2 秒等待、重放、并发取消、孤儿/晚到、fallback 写入、隐私、SDK-neutral 和 fake-only 负例。

运行统一入口、Godot fake loopback、schema、ignore、sensitive 和完整 tracked/untracked diff；P1/P2 必须停留在 Step 6，修复另获授权。不得读取真实 `.env`、调用真实 provider 或产生费用。

## Step 6 独立 QA 首轮结论与授权修复复审

- 后端独立 reviewer 以纯内存 fake provider 复现取消唯一等待者 → provider 抵抗 cancellation → 相同 request ID/payload 立即 Retry → 旧 orphan 结果借新 entry 写入的 P1；实际 `provider_calls=2`、`history_turn_count=2`、provider 历史长度 `(0, 2)`，违反幂等、无伪记忆与不重复计费。
- 根因位于 `application/dialogue.py` 的成功提交判断：仅校验当前 request ID entry 和 waiters，没有确认 `entry.task is asyncio.current_task()`；关联孤儿 entry 删除与新同 ID task 注册。现有取消、晚到、replay 测试均未覆盖三者组合。
- Godot/API 独立 reviewer 以 3 条错误/跨会话 assistant 历史通过 `_assert_memory_scenario("multi_turn", provider)` 复现 P2；当前 verifier 仅比较 history 数量和 user 文本，未比较真实成功 assistant 回复，CI 多轮场景可能假阳性。
- 首轮后端 reviewer 专项 405 passed、Godot/API reviewer 专项 79 passed 与 43 passed，统一质量入口 pytest 562 passed，但旧测试缺少上述组合负例，因此依然正确阻塞。
- 用户明确批准 Step 6 内修复后，新增 7 个失败优先负例：1/2 waiter 取消 orphan 同 ID Retry 均暴露双 provider 调用；普通多轮 3 处与失败恢复 2 处 assistant 历史污染均暴露 verifier 假阳性。
- P1 修复为保留被取消 orphan 的原 task 幂等 entry，让即时 Retry 继续复用同一在途 provider 请求，并在提交完整回合前强制 `entry.task is asyncio.current_task()`；独立 fake 复审验证 1/2/8/32 个 waiter 仅调用一次 provider、仅写一次历史、scope 锁正确回收。
- P2 修复为逐条比对每次 provider 请求 history 的 role、user 内容和对应真实成功 assistant completion；失败 outcome 不写历史，错误信息不暴露正文。P3 同步明确历史已通过 UAT 属于 F-003，F-004 UAT 尚未进行。
- 最终独立 QA：后端 412 passed，Godot/API 22 passed 和 Godot headless 通过，双方 NO FINDINGS；全量 fake-only 门禁 pytest 569 passed、9 健康 + 10 对话 loopback、lock、ruff、mypy、Schema、ignore/sensitive 与 diff 全通过。
- Step 6 已完成且零真实调用；Step 5 首个请求 usage 缺失仍如实披露。Step 7、用户 UAT、真实 DeepSeek/API key/费用和 Git 交付仍须分别授权。

## Step 7 计划：用户 UAT 与本地交付审查

先取得用户真实窗口、API key、最多 4 次/USD 0.015 的独立授权；用户亲自验证同 scope 连续对话、隔离、失败后手动恢复与 persona。

必须明确回传 `UAT_RESULT`、真实调用次数、prompt tokens、completion tokens、实际/保守费用和端口释放状态；禁止沿用 F-003 的 UAT 调用次数空缺。

Step 5 + Step 7 合计不得超过 12 次/USD 0.05；随后 fake-only 复跑统一门禁、格式、schema、Godot、Markdown 相对链接、CI 静态检查、ignore/sensitive 与 `git diff --check`。全部通过后方可收口为 `ready_for_git_delivery`，不得擅自提交、push 或进入 R-05。

## Step 7 用户 UAT、失败优先修复与最终复验

- 用户提供两个独立后端进程的准确 UAT 台账：首轮 4 次/664 输入/196 输出/USD 0.00055088；第二轮 4 次/718 输入/197 输出/USD 0.00057596。Step 7 合计 8 次、1382 输入、393 输出、USD 0.00112684，超过原 Step 7 4 次调用上限；Step 5 + Step 7 总计 16 次，超过原 12 次总上限，不得继续沿用旧授权。
- 当前可核算的 F-004 调用费用为 Step 5 后 7 次 + Step 7 全部 8 次，合计 7708 输入 token、479 输出 token、USD 0.00402380；Step 5 首次失败请求 usage 仍缺失，因此不声称已知完整费用。
- 同 scope 回忆真实代号通过，新 scope 未泄漏该代号，但两次编造其他代号并声称来自既往交流，UAT 因不诚实空历史回答阻塞。
- 用户授权修复且禁止真实模型后，10 个中英文/隔离/API 负例先失败；应用层增加空历史回忆检测并复用既有 `degraded / local-fallback`，零 provider 调用、零记忆写入，不修改冻结 persona、公开 v1/Schema、依赖、Godot 或数据库。
- 用户停止后端后，修复后相关专项 174 passed；完整 fake-only 统一入口 pytest 584 passed，lock、ruff、mypy 42 files、Schema、Godot、9 个健康与 10 个对话 loopback、ignore/sensitive 全通过。
- 用户随后亲自运行真实 Godot 窗口及 fake 本地后端，确认新会话明确回答没有先前信息、不会编造代号；服务退出打印 `FAKE_PROVIDER_CALLS=0`，8000 端口已释放。修复点人工复验通过、零新增真实调用和费用；Step 7 收口为 `ready_for_git_delivery`，Git 操作仍未授权。

## 全局停止条件

- 未获当前 Step、真实 provider/API key/费用、QA 修复、用户 UAT 或 Git 交付授权。
- 需要修改公开 Dialogue v1/Schema、新增依赖或数据库、新建 Godot 页面、进入 R-05 或扩大文件范围。
- `main`/`origin/main`、工作树、冻结模型参数、预算常量或 provider 行为发生不可解释漂移。
- 出现 scope 泄漏、重复/半回合写入、取消/晚到伪记忆、死锁、预算突破、persona 注入或原文泄漏。
- 自动化读取真实 `.env`/API key、调用真实 provider、产生费用或违反 fake-only CI。
- 真实评估、独立 QA、用户 UAT、质量门禁或远程 CI 失败，存在未解决 P1/P2，或未准确记录真实请求/token/费用。

## 交付与归档事实

功能提交为 `eb8a9cc69a93f004a346e8d27f81b10fa3c89a46`，分支为 `feat/f-004-short-term-memory-context-budget`；GitHub PR #4 的首个功能 HEAD 已通过 GitHub-hosted Linux `quality`。本计划与任务卡在同一 PR 归档；归档 HEAD 必须再次通过 CI，最终合并结果以 GitHub 为准。未新增真实模型调用、删除临时资源或进入 R-05。
