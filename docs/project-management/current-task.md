# 当前任务：F-004 短期会话记忆与上下文预算

状态：`approved / step_7_complete / ready_for_git_delivery`。

来源：[`roadmap.md`](roadmap.md) 的 `R-04`。用户已完成 Step 7 真实模型同 scope 回忆和隔离 UAT；初次发现空历史虚构记忆后，授权只用 fake 失败优先修复，并亲自在真实 Godot 窗口确认新会话明确回答“不知道”，`FAKE_PROVIDER_CALLS=0`。完整统一门禁已通过；当前仅等待另行授权 Git 交付，不得进入 R-05。

## 用户目标与可见价值

玩家在既有 Godot 场景连续与固定 NPC `neon_guide / Nia` 对话时，NPC 能参考同一玩家、NPC 和会话最近成功完成的完整回合，维持冻结 persona、公开契约、请求幂等、失败恢复和可控成本。不同 scope 不得串扰，失败、取消、重试和降级不得生成伪记忆。进程重启后记忆允许丢失。

## 已批准默认决策

- 只使用进程内有界工作记忆；不引入 SQLite、PostgreSQL、Qdrant、Redis 或其他数据库、向量库、持久化存储。
- `ConversationScope=(player_id, npc_id, conversation_id)`；三个字段均来自已校验的 `DialogueRequestV1`。
- 每个 scope 最多保留最近 6 个成功完成的完整 `user/assistant` 回合；最多 128 个活动会话，idle TTL 1800 秒。
- 不新增 tokenizer 或其他依赖；以 UTF-8 字节数 + 固定结构开销作为保守工程估算，明确不等于 provider 官方真实 token 数。
- 总预算 8192 估算单位；请求结构开销 64，每条消息开销 16，为冻结 `max_tokens=256` 保留 256 单位。
- 历史 role 只允许 `user`、`assistant`；Nia persona 始终是唯一且排序第一的 `system`。
- provider 顺序固定为 `system(persona)` → 完整历史 user/assistant 对 → 当前 user；从新到旧选择历史，发送时按从旧到新排序。
- persona 与当前 user 不得截断或静默删除；当前输入无法放入预算返回 HTTP 422 + `validation_error`，零 provider 调用；persona/内部容量无法满足最小请求返回可重试 HTTP 503。
- 仅完全校验通过的 `completed` 逻辑请求原子写入一次完整回合；`degraded / local-fallback`、失败、取消、孤儿与晚到结果均不写入。
- 同 scope 不同逻辑请求串行，最多等待 2 秒，超时返回可重试 503；不同 scope 可并发，继续遵守 provider 全局并发上限 2。
- Retry、成功 replay、同 ID 并发不得重复调用 provider 或重复写记忆；同 ID 不同 payload 继续返回 409。
- 默认复用既有 Godot 对话场景、稳定 `conversation_id`、新 Send 独立 `request_id` 和 Retry 冻结 payload，不新增页面。
- 不修改 `DialogueRequestV1`、`DialogueResponseV1`、`ApiErrorV1`、公开 HTTP JSON 结构或派生 JSON Schema。
- 保持 `deepseek-v4-flash`、non-thinking、non-stream、temperature 0.6、max tokens 256、provider timeout 12 秒、Godot timeout 15 秒和 SDK 自动 retry 0。
- 自动化、统一质量入口和 GitHub CI 永久 fake-only，不读取真实 `.env` 或 API key，不调用真实模型或产生费用。
- Step 5 推荐上限 8 次 / USD 0.035；Step 7 推荐上限 4 次 / USD 0.015；F-004 总计不超过 12 次 / USD 0.05，两个 Step 的真实调用/key/费用均须分别批准。
- 用户 UAT 必须明确记录真实调用次数、输入/输出 token 和费用；不得复用 F-003 授权或历史预算。
- 独立 QA、真实多轮评估、用户 UAT 和交付归档完成前，不得宣称 F-004 完成。

## 范围

1. 按三元 scope 隔离的有界进程内工作记忆、完整回合、TTL、容量和 LRU。
2. provider-neutral 历史 DTO，FakeProvider/DeepSeek 多消息适配与严格 role/顺序校验。
3. UTF-8 工程预算、输出预留、整回合裁剪、确定性错误映射与脱敏预算元数据。
4. 既有 request 幂等、取消、同 scope 串行、跨 scope 并发和 provider semaphore 的正确组合。
5. FastAPI 多轮与 Godot → FastAPI → FakeProvider loopback，保留 F-002/F-003 全量回归。
6. 单独授权的真实 DeepSeek 多轮评估、独立 QA、用户 UAT 及必要当前事实文档同步。

## 非目标

- 不实现长期记忆、结构化摘要、embedding、语义检索、遗忘工作流或 R-05。
- 不创建数据库、迁移、运行时数据文件、外部缓存、跨进程共享状态或持久幂等。
- 不增加 tokenizer、Agent 框架、第三方记忆库、工具调用、SSE、WebSocket 或 streaming。
- 不新增 NPC、修改冻结 persona、实现好感度、自治行为、多 Agent 或正式视觉设计。
- 不修改公开 Dialogue v1、Schema、健康契约、已冻结模型参数或生产服务。
- 不保存/展示原始 player message、persona prompt、模型回复、API key 或 provider body。
- 不承诺跨重启、跨 worker、跨进程或跨实例保留工作记忆。

## Step 0 只读复核结论

- 当前分支 `main`；HEAD、`main`、`origin/main` 均为 `5ea85a3ec39cdd3df64f39626dfaf3b238305a24`；修改前工作树干净，staged/untracked 均为 0，remote 为既有 `origin`。
- F-003 已由 PR #3 squash merge，当前提交标题为 `feat: add single-NPC real dialogue`，F-003 任务卡和实现计划均已归档。
- Python `3.12.10`、uv `0.6.14`、Godot `4.7.2.stable.official.ed1daf0bf` 可用；Godot console：`E:\Agent.tools\godot\4.7.2\Godot_v4.7.2-stable_win64_console.exe`。
- 公开请求已有 `request_id`、`player_id`、`npc_id`、`conversation_id`、`message`；现有 response/error 与 `contracts/v1/*.schema.json` 不需要修改。
- `ProviderRequest` 与 DeepSeek adapter 当前只处理 persona system + 当前 user；应以向后兼容的 provider-neutral history DTO 适配多消息。
- DialogueService 已有 600 秒 / 256 项 request 幂等、共享调用、失败清理、provider 并发上限 2、completed/degraded 分类和隐私 allowlist，但尚无会话 store、上下文预算或 scope 锁。
- Godot client 在 `_init()` 只生成一次 conversation ID；新 Send 创建新 request ID，Retry 复用冻结 payload，因此默认不需要新页面。
- FastAPI、Pydantic、OpenAI SDK 和 Uvicorn 依赖均已存在；F-004 不需要新增依赖。
- `docs/memory-design.md` 提及未来 SQLite 恢复可能；F-004 已明确选择纯内存，该规划表述留待后续已授权文档 Step 校正。
- Step 0 时，项目 `AGENTS.md`、`docs/README.md`、roadmap/progress 顶部仍保留 F-003 的过期摘要；该历史漂移已在后续获明确授权的 Step 4 文档同步中修正。
- 未读取 `.env`、API key、原始玩家消息、模型回复或 persona prompt 内容，未调用模型、安装依赖或创建分支。

## Step 1 完成事实

- 已从 `main` / `origin/main` 的 `5ea85a3ec39cdd3df64f39626dfaf3b238305a24` 创建 `feat/f-004-short-term-memory-context-budget`，完整保留 Step 0 两份任务文档，未产生提交或暂存文件。
- 首批失败优先红灯为 94 failed / 38 passed；随后额外验证 7 个整数伪装浮点和 3 个非有限等待值亦先失败。新增 F-004 配置负例共 104 项。
- `Settings` 冻结 `memory_scope_fields=(player_id, npc_id, conversation_id)`、6 回合、128 session、1800 秒 TTL、8192 预算、64 请求开销、16 消息开销、256 回复预留和 2 秒 scope 等待。
- 数值字段接受正常环境变量字符串，但拒绝 bool、整数伪装浮点、非法类型、非正值、NaN/Infinity 与批准值漂移；scope 拒绝缺项、超项、错序、重复、错误字段和非字符串。
- 配置定向测试 142 passed；ruff、ruff format 与 mypy 通过。全量统一门禁为 pytest 366 passed、lock 45 packages、mypy 35 source files、ruff、Schema、Godot import/unit、9 个 F-002 loopback、8 个 F-003 fake loopback 以及 ignore/sensitive 全部通过。
- 自动化设置 `CYBER_TOWN_DISABLE_DOTENV=1`、provider disabled 并保持 fake-only；未读取真实 `.env` 或 API key，未新增依赖，未实现 store、TTL/LRU、预算计算、provider/Godot 改动或 R-05。

## Step 2 完成事实

- 失败优先红灯：新增 `test_short_term_memory.py` 后，pytest 因 `cyber_town.application.memory` 尚不存在而收集失败，证明测试先于实现。
- 新增独立的 `application/memory.py`，仅包含不可变三元 `ConversationScope`、隐藏正文 repr 的完整 `ConversationTurn`、进程内 `ShortTermSessionStore` 和安全 `SessionCapacityError`。
- scope 严格要求已校验的 player/NPC 字符串与 UUID conversation；不同 player、npc、conversation 均完全隔离，缺项、错项、空白、长度超限和错误类型被拒绝。
- 每次成功提交原子写入完整 user/assistant 回合；消息长度沿用既有 1000/4000 字符上限，每个会话只保留最近 6 个完整回合，半回合、失败、取消和 degraded 均不形成伪记忆。
- store 限制为 128 个会话、1800 秒 idle TTL；使用可注入单调时钟验证 1799/1800/1801 边界，过期优先、确定性 LRU、读取/写入刷新、在途保护及全在途满载 fail-closed。
- 完成或取消在途工作可安全释放容量；所有回合只驻留内存，测试证明生命周期操作不打开文件，未导入 SDK、数据库、provider、FastAPI 或 Godot。
- store 定向 102 passed，store + 配置联合 244 passed；全量统一门禁为 pytest 468 passed、lock 45 packages、mypy 37 source files、ruff、Schema、Godot import/unit、9 个健康 loopback、8 个 fake dialogue loopback 与 ignore/sensitive 全通过。
- store 尚未接入 `DialogueService`、FastAPI 或真实 provider；未实现 UTF-8 预算计算、history DTO、provider 多消息、2 秒 scope 调度或 Step 3 逻辑。

## Step 3 完成事实

- 失败优先红灯：新增预算、历史 DTO、会话编排及 adapter 负例后，pytest 收集因 `cyber_town.application.context_budget` 不存在和 `ProviderHistoryMessage` 无法导入产生 2 个预期错误。
- 新增不可变且正文 repr 脱敏的 `ProviderHistoryMessage`；`ProviderRequest.history_messages=()` 向后兼容，只允许完整、交替 `user/assistant` 历史，拒绝非法 role、半回合、类型伪装和篡改注入。
- 新增 `application/context_budget.py`，按冻结的 64 请求开销、16 消息开销、8192 总预算和 256 回复预留计算 UTF-8 字节工程估算；历史仅按最新完整回合裁剪并旧到新发送，覆盖中文、emoji、组合字符、8192/8193 和整对淘汰。
- 当前消息预算不足映射为 `validation_error`，persona/最小结构、会话容量和同 scope 等待失败映射为可重试 `provider_unavailable`；无 provider 调用、伪记忆或敏感正文泄露。
- DeepSeek SDK adapter 按唯一 `system(persona)` → 完整历史 `user/assistant` → 当前 `user` 构造消息，并对篡改的 system/developer/tool role 在 SDK 调用前 fail-closed；SDK 仍只存在于 infrastructure。
- `DialogueService` 接入三元 scope store、6 回合/1800 秒 TTL/128 sessions，同 scope 完整读—调用—写事务串行，等待上限 2 秒；不同 scope 并发但 provider 全局上限保持 2。
- 同 ID 并发只调用一次 provider 并写入一次；成功 replay、冲突、失败、degraded 不重复写入；部分等待者取消保留合法共享请求，全部取消及忽略取消的晚到结果均不生成伪记忆并释放在途资源。
- Step 3 历史/预算/adapter/应用定向及 F-003 application 回归 144 passed；加上 Step 1 配置与 Step 2 store 联合回归 388 passed；统一 fake-only 门禁 pytest 545 passed、lock 45 packages、mypy 40 source files、ruff、Schema、Godot import/unit、9 个 F-002 loopback、8 个 F-003 fake loopback 及 ignore/sensitive 全通过。
- 未修改公开 Dialogue v1/Schema、依赖、FastAPI 路由/composition、Godot 或 Step 1 配置；未读取 `.env`/API key、调用真实模型、产生费用、提交、推送或进入 Step 4/R-05。

## Step 4 完成事实

- 失败优先红灯：新增 FastAPI 多轮和 Godot fake loopback 合约负例后，集成 harness 因尚未定义 `MEMORY_SCENARIOS` 而出现预期 `KeyError`；随后仅扩展测试 harness，不修改 Godot 场景、客户端、FastAPI 路由或公开契约。
- `backend/tests/test_dialogue_memory_api.py` 验证同 scope 多轮严格公开响应、player/conversation/NPC 隔离、最近 6 完整回合、422/503/502/504、安全 degraded、成功 replay、409 conflict 和失败后手动 Retry 不生成伪记忆。
- `backend/tests/test_dialogue_memory_integration.py` 验证多轮场景登记、完整历史递增、缺失历史和失败 ghost turn 拒绝；新增 HTTP/harness 专项共 17 passed。
- `scripts/dialogue_integration.py` 和 `game/tests/run_dialogue_fake_integration.gd` 复用既有真实 Godot 场景/HTTPRequest 与 loopback FastAPI/FakeProvider，将对话集成从 8 扩展到 10 场景：新增连续三轮，以及第二轮 503 → 手动 Retry → 第三轮。
- Godot 多轮真实 loopback 锁定稳定 conversation、新 Send 独立 request_id、Retry 不变 payload、完成历史递增、失败不写、继续对话和 8000 端口释放；未新增游戏页面、改客户端或调用真实模型。
- 已同步项目 README/AGENTS、docs 地图、architecture、memory-design、evaluation-strategy、testing-strategy、ADR-014、roadmap、progress 和 evidence；修正“无活动任务 / 未进入 R-04 / 无记忆 / 8 个当前对话场景”等过期事实。
- 完整 fake-only pytest 562 passed；lock 45 packages、mypy 42 source files、ruff、Schema、Godot import/unit、9 个健康 loopback、10 个 fake dialogue loopback 与 ignore/sensitive 均通过；F-004 修改的 14 个 Python 文件格式检查通过。
- 未读取 `.env`/API key、调用真实 provider、产生模型费用、修改公开 v1/Schema、数据库、Godot 场景/客户端、依赖或 CI workflow；未执行独立 QA、用户 UAT、提交、推送、Step 5 或 R-05。

## Step 5 完成事实

- 用户已单独批准真实 DeepSeek 联网、通过现有 Settings 使用被 Git 忽略的 `.env`、最多 8 次/USD 0.035，并在首轮失败后批准调整验收流程；SDK 继续锁定 `deepseek-v4-flash`、non-thinking/non-stream、0.6、256 tokens、12 秒和零自动 retry。
- 实际真实请求共 8 次：首次请求在语义断言时退出，usage 未打印且无法追溯；随后改为每次 provider 返回立即输出脱敏 usage，再执行语义断言，剩余 7 次全部通过。已向用户明确披露首个请求的 token/费用缺失，不伪造完整总费用。
- 后续 7 次累计 6326 prompt tokens、86 completion tokens，按官方峰值 cache-miss 输入 USD 0.44/百万与输出 USD 1.32/百万估算，已记录部分费用上界为 USD 0.00289696；该数值不包含历史首个无法追溯的请求。
- 真实 HTTP → DialogueService → DeepSeek 验证同 scope 连续召回、不同 conversation/player 零历史、唯一 Nia persona、成功 replay 不产生额外 provider 调用与最终最近 6 个完整回合。
- 两个仅存在于验收进程的合成完整历史回合用于触发 8192 工程预算整回合裁剪；真实模型仍能读取保留的最近回合并维持 Nia 身份。脱敏 audit 不包含 key、persona prompt、玩家消息、历史或模型回复。
- 验收按项目 README 只在专项子进程移除 SOCKS `ALL_PROXY` 并保留 HTTP/HTTPS 代理；未改系统代理、锁定依赖、产品代码、公开 Schema、Godot 或数据库。独立 QA、用户 UAT、Git 交付和 R-05 仍未执行。

## Step 6 独立 QA、失败优先修复与复审

- 两名 reviewer 分别从已批准任务卡独立审阅后端记忆/预算/幂等/并发，以及 Godot/FastAPI 多轮集成、CI、隐私、tracked/untracked diff；全过程设置 `CYBER_TOWN_DISABLE_DOTENV=1` 与 `LLM_PROVIDER=disabled`，零真实 provider 调用。
- 首轮 P1：唯一等待者取消、provider 忽略取消、同 ID 立即 Retry 后，旧 orphan 可借新 entry 提交伪记忆并重复调用 provider；首轮 P2：多轮 verifier 未校验 assistant 回复，跨会话污染可能假通过；另有 F-003 历史 UAT 描述 P3 歧义。
- 用户单独授权 Step 6 内修复后，先新增 7 个组合负例并确认红灯：2 个取消 orphan + 同 ID 1/2 waiter Retry 负例和 5 个普通/失败恢复 assistant 污染负例均失败；随后实施最小修复。
- P1 已关闭：取消 orphan 保留原 task 幂等归属，允许同 request ID Retry 复用仍在途的合法结果；完整回合提交前额外校验 `entry.task is asyncio.current_task()`，防止旧 task 借替换 entry 写入。独立复审验证 1/2/8/32 个 Retry 等待者均只调用一次 fake provider、写入一次完整回合且释放 scope 锁。
- P2 已关闭：Godot/FastAPI fake loopback 逐条验证真实成功 outcome 对应的完整 user/assistant 内容与角色，失败 outcome 不进入历史；普通多轮 3 个污染位置、失败恢复 2 个污染位置均 fail-closed，报错不包含原始正文。
- P3 已澄清：`docs/testing-strategy.md` 明确已通过的历史窗口 UAT 仅属于归档 F-003；F-004 用户 UAT 尚未执行，必须在另获授权的 Step 7 进行。
- 两名独立 reviewer 复审均为 NO FINDINGS：后端专项 412 passed，纯内存最多 32 并发 Retry 无重复调用或伪记忆；Godot/API 专项 22 passed，6 个独立污染/role/异常 outcome 边界均安全拒绝。完整 fake-only 门禁 pytest 569 passed，9 健康 + 10 对话 loopback、lock、ruff、mypy、Schema、ignore/sensitive 与 diff 检查均通过。
- Step 6 完成；Step 5 真实调用额度已用尽，本次修复、门禁和独立复审零真实 provider 调用。用户 UAT、真实调用/API key/费用和 Git 交付仍须分别明确授权，不得自动进入 Step 7 或 R-05。

## Step 7 用户 UAT、授权修复与完成复验

- 用户首轮窗口 UAT 证明同一 scope 能正确回忆临时代号，另一新窗口未泄漏该真实代号；两轮独立后端进程的脱敏台账分别为 4 次/664 输入/196 输出/USD 0.00055088，以及 4 次/718 输入/197 输出/USD 0.00057596。Step 7 合计 8 次、1382 输入、393 输出、USD 0.00112684；已超过原批准的 4 次调用上限，但已记录费用低于 USD 0.015。
- Step 5 + Step 7 真实调用总数为 16 次，超过任务卡原设 12 次总上限。可核算的 Step 5 后 7 次与 Step 7 全部 8 次合计 7708 输入 token、479 输出 token、USD 0.00402380；Step 5 首次失败请求的 usage 仍无法追溯，上述金额不能伪称完整费用。
- 修复前，新 scope 两次分别虚构其他临时代号并声称来自既往交流；这不是跨 scope 内容泄漏，而是空 history 下模型编造记忆。该阻塞现已通过确定性 local-fallback 及用户窗口复验关闭。
- 用户授权只用 fake 修复后，新增 10 个失败优先负例，覆盖中英文空历史追问、player/conversation 隔离与 FastAPI 精确既有契约；修复前全部得到模型伪造的 completed 回复并如期失败。
- 应用层现于无可用历史且请求明确追问先前交流时，返回确定性 `degraded / local-fallback`，中文明确说明当前会话没有先前信息；零 provider 调用、零 token/费用、零记忆写入。已有历史的回忆及首次主动告知仍走原 provider 流程，冻结 persona、公开 Dialogue v1、Schema、依赖和 Godot 均未修改。
- 修复后专项回归 174 passed；用户停止 UAT 后端后，完整 fake-only 统一入口 pytest 584 passed，lock、ruff、mypy、Schema、Godot import/unit、9 个健康 loopback、10 个对话 fake loopback 及 ignore/sensitive 全部通过。修复与门禁没有读取 `.env`、调用真实模型或产生费用。
- 用户随后亲自启动真实 Godot 窗口和禁用 `.env`/真实 provider 的本地 fake 后端；新会话追问既往代号时，界面准确显示“当前会话中还没有你先前告诉我的信息，因此我不知道。”，结束时 `FAKE_PROVIDER_CALLS=0` 且 8000 端口已释放。修复点用户 UAT 通过，新增真实调用/token/费用均为 0。
- Step 7 完成，当前状态为 `ready_for_git_delivery`；提交、推送、PR、远程 CI、合并和归档均须另获明确 Git 授权，不进入 R-05。

## 会话生命周期与一致性

- session key 必须完整使用 `(player_id, npc_id, conversation_id)`；只用 conversation 或 player+NPC 均不合格。
- session 按需创建；非法输入、未知 NPC、失败逻辑请求不得留下有效历史。
- 每个成功 turn 原子写入一条 user 和一条 assistant，且发生在 provider 输出及公开响应完全校验之后。
- 成功 replay 不得写第二次；失败后手动恢复仅允许最终成功执行写一次。
- idle TTL 使用可注入单调时钟；过期 scope 视为新会话，不复用失效内容。
- 超过 128 session 时优先清理过期，再按确定性 LRU 淘汰无在途工作的 session；不得驱逐在途，无法回收时返回可重试 503。
- 同 scope 不同 request 在“读取历史 → provider 调用 → 提交成功 turn”全区间保持串行。
- 同 request ID 先通过现有幂等共享；仍有有效等待者可共享结果，无有效等待者的孤儿/晚到结果不得生成记忆。
- 服务关闭/重启后记忆丢失；禁止用磁盘、Godot 本地持久化或隐式外部缓存绕过。

## Provider-neutral 多消息契约

- 使用仅位于 application 边界的不可变 `ProviderHistoryMessage(role, content)` 或等价 DTO。
- role 只允许严格字符串 `user`/`assistant`；拒绝 `system`、`tool`、`developer`、未知值、空值和非字符串。
- content 必须是经过校验的非空字符串；禁止 SDK 类型、provider 原始对象或任意 JSON value 穿透 application/domain。
- 以兼容字段 `history_messages=()` 扩展 `ProviderRequest`；冻结的 persona、当前 user、模型及执行参数不变。
- adapter 只组装唯一 system、交替完整历史对和当前 user；拒绝重复 system、半回合、顺序错误、历史末尾 user 或 persona 覆盖。
- FakeProvider 只记录测试内 neutral DTO；具体 OpenAI SDK 仍隔离在 infrastructure adapter。

## 上下文预算

```text
estimated_context_units =
    64
    + (16 + utf8_bytes(persona_system_prompt))
    + Σ(16 + utf8_bytes(selected_history_message))
    + (16 + utf8_bytes(current_user_message))
    + 256

estimated_context_units <= 8192
```

- UTF-8 字节计数覆盖中文、emoji、组合字符与边界；8192/64/16/256 均是工程估算单位，不等于官方 token 统计。
- 固定保留 256 回复预算；persona 和当前 user 始终优先，历史以最新完整回合优先，最终旧到新发送。
- 禁止裁剪半回合、截断 user/assistant 文本或从错误 scope 借取历史。
- 当前消息无法放入最小预算：422 + `validation_error`、`retryable=false`，零 provider 调用和记忆写入。
- persona/冻结配置无法容纳最小请求或无可用 session：503 + `provider_unavailable`、`retryable=true`。
- 日志只允许必要 turn 数量、估算单位、裁剪数量和脱敏 trace/request 元数据，不保存 prompt、history、消息正文或模型回复。

## API、Godot 与失败语义

- 继续使用 `POST /api/v1/dialogue` 与既有严格 Dialogue v1，不新增公开字段。
- 同一 conversation 的连续 Send 能参考先前成功 turn；任一 scope 成员变化均不得读取历史。
- Retry 保持逐字节相同 payload；成功 replay 不追加历史。
- 继续保留现有 409/422/502/503/504、Godot 单在途、Send/Retry 禁用、失败恢复、晚到结果丢弃和 F-002 health 场景。
- 默认不修改 `game/scenes/**`、既有视觉文案或 UI 布局；确需修改 Godot 实现时先停止并申请最小范围扩展。

## 测试矩阵

| 风险/行为 | 测试层级 | 必需覆盖 |
| --- | --- | --- |
| 三元 scope 隔离 | 单元 / application / API | 不同 player、npc、conversation 的碰撞、跨 scope 回读和缺字段拒绝 |
| 完整 turn 与 6 回合 | 单元 / application | 首轮空历史、连续回合、6→7 FIFO、交替 role、拒绝半回合 |
| 1800 秒 TTL / 128 LRU | 单元 / 并发 | 到期边界、128→129、过期优先、LRU、在途保护、满载 503 |
| UTF-8 / 8192 预算 | 单元 / API | 中文、emoji、组合字符、刚好预算、超 1、当前消息/长 persona、完整 turn 裁剪 |
| persona / role 安全 | DTO / adapter stub | 唯一 system、拒绝 system/tool/developer、非字符串、顺序错误、provider 消息次序 |
| Retry / 幂等 | application / API | 同 ID 并发、成功 replay、Retry、同 ID 异 payload 409、失败恢复、只写一次 |
| 同 scope 并发与取消 | application / API | 串行顺序、2 秒等待、503、跨 scope 并发≤2、孤儿、取消、晚到结果 |
| 失败不写记忆 | application / API | timeout、503、502、422、degraded/local-fallback、无效输出、取消 |
| Godot 多轮 | headless / fake loopback | 稳定 conversation、连续 Send、失败手动 Retry、无新增页面、FakeProvider 调用计数 |
| 隐私与 CI | pytest / quality / CI | 不读取 `.env`/key，不记录原文，公开 Schema 不变，F-002/F-003 回归和 fake-only |
| 真实多轮 | Step 5 专项 | 另获授权后，同 scope 连贯、不同 scope 隔离、裁剪后 persona 稳定，≤8 次/USD 0.035 |
| 用户 UAT | Step 7 人工 | 另获授权后真实窗口连续对话与恢复，≤4 次/USD 0.015，并明确记录调用/token/费用 |

测试必须从用户价值、风险与失败边界设计；真实 provider 不进入 pytest、统一入口或 GitHub Actions。

## 文件影响范围

Step 0 仅允许：

- `docs/project-management/current-task.md`。
- `docs/project-management/implementation-plan.md`。

后续在对应 Step 单独授权后可能修改：

- `backend/src/cyber_town/config.py` 与必要的安全配置示例；不读取真实 `.env`。
- `backend/src/cyber_town/application/provider.py`、`application/dialogue.py` 和短期记忆/预算必要的 application/domain 模块。
- `backend/src/cyber_town/api/composition.py`；仅在公开错误适配确有必要时修改 `api/dialogue.py`。
- `backend/src/cyber_town/infrastructure/llm/fake.py`、`infrastructure/llm/deepseek.py`。
- `backend/tests/test_config.py`、`test_dialogue_application.py`、`test_dialogue_api.py`、`test_deepseek_provider.py` 及必要的新记忆/预算测试。
- `scripts/dialogue_integration.py`、`game/tests/**`；默认不修改 `game/scenes/**` 或客户端实现。
- 项目 `README.md`、`AGENTS.md`、`docs/README.md`、architecture、memory-design、evaluation-strategy、testing-strategy、decisions 和项目管理文档，仅按真实变化同步。

明确不修改：`backend/src/cyber_town/contracts/v1.py`、`contracts/v1/*.schema.json`、`pyproject.toml`、`uv.lock`、真实 `.env`、其他项目、正式素材、数据库/迁移和 R-05。

## 文档、评估、Git 与 CI 边界

- 本文件是唯一 F-004 活动任务卡；[`implementation-plan.md`](implementation-plan.md) 是唯一 Step 地图。
- Step 0 只同步上述两份文档；README、项目 AGENTS、roadmap、progress、evidence、架构/记忆/ADR 留待后续明确授权。
- 后续只同步已实现和验证的当前事实，校正“无活动任务 / 未进入 R-04 / 无记忆”的过期摘要，不把计划伪报为完成。
- Step 5 / Step 7 真实调用、key、联网、费用分别批准，精确记录请求、prompt/completion tokens、费用和剩余额度；不保留原文。
- 推荐分支 `feat/f-004-short-term-memory-context-budget`，仅在 Step 1 获批后创建，必须完整保留 Step 0 两份修改。
- commit、push、PR、CI、合并和归档必须由后续独立 Git 交付授权覆盖；不得复用 F-003 权限。
- GitHub Actions 保持 fake-only，不增加 secrets、服务容器、真实 provider 或付费服务。
- 任务完成并归档后不得自动开始 R-05。

## 验收标准

1. 同 scope 已有成功回合时，后续请求按 `system → 历史 user/assistant → 当前 user` 调用 provider，公开 Dialogue v1 不变。
2. player、npc 或 conversation 任一变化时，不得读取另一 scope 历史。
3. 第 7 个成功 turn 后仅保留最近 6 对，不产生半回合。
4. 1800 秒 TTL、128 容量、LRU 与在途保护均符合冻结规则，无法安全回收时返回可重试 503。
5. 上下文估算不超过 8192，始终预留 256 回复单位，并以最新完整 turn 优先保留。
6. 当前消息预算不足返回 422；persona/内部容量不足返回 503；均零 provider 调用和零伪记忆。
7. timeout、502、503、422、degraded、取消、孤儿和晚到结果均不写记忆。
8. Retry、replay、同 ID 并发仅写一次；同 scope 顺序一致，不同 scope 服从全局 provider 并发上限 2。
9. 原有 Godot 场景连续 Send、手动 Retry 与稳定 conversation 均通过 fake-only loopback，无新增页面。
10. 统一门禁与 CI 永久 fake-only，不读取真实 `.env` 或 key，公开 Schema 和既有回归保持通过。
11. 单独授权后，Step 5 + Step 7 合计≤12 次/USD 0.05，且两阶段准确记录请求、输入/输出 token 和费用。
12. 独立 QA、真实多轮评估、用户 UAT、本地/远程门禁及 Git 归档全部通过后，方可宣称 F-004 完成。

## 风险、回滚与停止条件

- 主要风险：scope 串扰、persona 覆盖、UTF-8 低估、半回合、重复计费/写入、scope 死锁、孤儿伪记忆、在途 LRU 驱逐、原文泄漏和真实费用失控。
- 服务重启/多 worker 不保证连续，这是已接受边界；不得擅自用数据库消除。
- 开发中不得 reset、clean、删除、覆盖工作树；未来回滚必须遵守另行批准的 Git/部署流程。
- 基线漂移、公开契约/Schema/依赖变化、新页面、数据库、文件越界、未获对应 Step/真实调用/Git 授权时停止。
- 任一 scope 泄漏、伪记忆、预算突破、system 非唯一、`.env` 被自动化读取、敏感原文泄漏、未解决 P1/P2 或质量/评估/UAT/CI 失败时停止。

## 完成定义

- [x] Step 0：批准任务卡与实现计划落盘，Git、公开契约、provider、Godot 与工具完成只读复核。
- [x] Step 1：功能分支、冻结配置及负向测试。
- [x] Step 2：有界 store、三元 scope、完整 turn、TTL/LRU。
- [x] Step 3：history DTO、预算裁剪、adapter、幂等和并发。
- [x] Step 4：fake 多轮 loopback、隐私、回归与当前事实文档。
- [x] Step 5：单独授权的真实多轮评估；共 8 次调用，7 次费用精确记录，首次失败请求的 usage 缺失已如实披露。
- [x] Step 6：独立 QA 无未解决 P1/P2，全量 fake-only 门禁通过。
- [ ] Step 7：单独授权的用户真实窗口 UAT 与最终本地交付审查。
- [ ] Git 交付：另获授权的提交、push、PR、CI、合并与任务归档。

## 未覆盖范围

跨进程一致性、服务重启恢复、持久化审计、官方 tokenizer 精确计数、长期记忆、语义检索、数据库、多 NPC、正式 UI、生产限流与 R-05 不属于本任务承诺。
