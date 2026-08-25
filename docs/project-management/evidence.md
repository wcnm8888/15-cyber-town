# Cyber Town 验收证据索引

本文件只保留可恢复的最终证据摘要；详细任务范围、Step 过程和失败修复记录位于 [`../archive/task-cards/`](../archive/task-cards/)，提交、CI 与合并事实以对应 GitHub PR 为准。

| 任务 / 验证项 | 方法 | 结果 | 未覆盖范围 / 风险 |
| --- | --- | --- | --- |
| F-001 工程与契约基线 | 本地 UAT、独立 QA、统一门禁、GitHub Actions 与归档 | Python 3.12/uv、Pydantic v1 对话契约、派生 schema、统一质量入口和 CI 已建立；交付载体为 PR #1 | 不包含 API、Godot、LLM 或数据库；详细记录见 F-001 归档 |
| F-002 工具与依赖 | 官方发布资产与 SHA-256、普通/headless 版本、uv lock | Godot 4.7.2 Standard official；FastAPI 0.141.1、Uvicorn 0.52.4、HTTPX 0.28.1；lock 38 packages | 未修改系统 PATH，未安装 .NET 或 export templates |
| F-002 健康 API | API 契约、方法、side-effect 和启动入口负例 | `GET /api/v1/health` 精确返回固定三字段；GET-only、无 body/query/dependency；只允许 loopback bind | 不包含 Dialogue、LLM、数据库或生产服务 |
| F-002 Godot 客户端 | Godot unit、scene import/load、真实 HTTPRequest | 五态文案、严格响应、3 秒 timeout、单在途请求与手动 Retry 通过；redirect、重复键、非字符串与非法响应 fail-closed | 低保真 Windows 桌面诊断场景，不是正式游戏 UI |
| F-002 真实集成 | owned FastAPI/loopback fixtures 与 Godot 4.7.2 | 9 个场景通过：停服、503、重复键、非字符串、redirect 拒绝、connected 及三种失败恢复；8000/8001 最终释放 | 仅 loopback，不访问公网、生产、LLM 或数据库 |
| F-002 独立 QA | 两轮修复复验及最终 22 个响应变体重放 | 最终结论 NO FINDINGS；P0/P1/P2/P3 均无；历史 duplicate、redirect、bind、类型和停服 oracle 均通过 | 独立 QA 不替代用户窗口 UAT 或远程 Linux CI |
| F-002 用户 UAT | Windows 真实 Godot 窗口检查环境、connected、timeout/Retry、unavailable/恢复 | `UAT_RESULT=PASS`；用户确认四组流程均通过，结束后返回 `PORT_8000_STOPPED=YES` | 截图未逐帧冻结所有瞬时状态；用户完成确认作为人工证据 |
| F-002 最终本地门禁 | `uv run --frozen python scripts/quality.py` 及交付专项检查 | pytest 134；Godot import/unit；9 integration；ruff、mypy 18 files、schema、lock、ignore、sensitive、Markdown、workflow YAML/静态契约与 diff 全通过 | Windows 本地结果不替代 GitHub Linux runner |
| F-002 GitHub 交付 | 精确暂存 36 文件；提交、push、PR 与 GitHub-hosted Linux CI | 功能提交 `ffe2443`；分支 `feat/f-002-godot-fastapi-connectivity`；PR #2 首个功能 HEAD 的 `Quality` 通过；任务卡与计划已在同一 PR 准备归档 | 归档提交会产生新 HEAD；最终 CI、合并状态与 merge SHA 以 GitHub PR #2 为准 |
| F-003 工具与配置 | 锁文件、SDK import、安全配置与负向测试 | `openai 3.3.1`、lock 45 packages；provider 默认 disabled；批准模型/base URL、12 秒 timeout、零 SDK retry、non-thinking 和 non-stream 已冻结；离线策略测试在 pytest 临时目录隔离真实 `.env` | 真实 key 只允许由专项授权进程从 Git 忽略的本地 `.env` 读取 |
| F-003 Persona 与应用边界 | 冻结 persona、SDK-neutral fake provider、应用/HTTP/Godot 自动测试 | 固定 `neon_guide / Nia`；严格 Dialogue v1、公共错误映射、进程内幂等、单在途请求、手动 Retry 和脱敏 audit 通过 | 无数据库、长期记忆、多 NPC、工具调用或持久幂等 |
| F-003 真实 DeepSeek smoke | 受预算限制的真实 adapter 调用与 usage 审核 | HTTP 200；provider 为 `deepseek`；模型为 `deepseek-v4-flash`；返回严格 Dialogue v1，usage 与安全 audit 可核查 | 单次真实模型行为不保证后续外部 provider 可用性 |
| F-003 Persona 真实评估 | 12 项固定身份、语气、相关性、事实/能力边界、注入和语言用例 | 全部通过；rubric 12/12；最后一项复用真实 Godot 场景并验证 `loading → success`、Nia 身份及脱敏 trace | 不保存原始玩家消息、persona prompt 或模型回复；不能代替用户窗口 UAT |
| F-003 Step 5 历史调用与费用 | 按 provider usage 和官方峰值单价计算 Step 5 专项验收保守上界 | Step 5 为 13/15 次真实请求；输入 1770 token、输出 809 token；费用上界 USD 0.00184668 / USD 0.05；零自动 retry | 该统计只覆盖 Step 5；用户 UAT 真实调用次数与新增费用未单独提供，不推算总量 |
| F-003 Step 6 失败优先修复 | synthetic/fake Python 与 Godot 负例、两轮独立复审 | 首轮 16 个 Python 负例和 4 个 Godot 负例先失败；fake loopback 缺失与复审新增 3 个畸形 `choices` 变体亦先失败，修复后全部通过 | 首轮 3 项 P1、6 项 P2 及同类新增 choices P2 均关闭；无真实模型调用 |
| F-003 对话 fake 集成 | 真实 Godot HTTPRequest → loopback FastAPI → FakeProvider | 8 场景通过：成功，503/504/502 后手动恢复，错误/缺失/重复 Content-Type 和 HTTP 201 拒绝；冻结 payload 与 provider 调用次数受检 | 仅 loopback，不读取真实 `.env`、不调用 DeepSeek；headless 结果不能代替用户 UAT |
| F-003 Step 6 独立 QA | 两名 reviewer 从任务卡独立设计 synthetic/fake 负例并审阅 tracked/untracked 范围 | 后端 `P0/P1/P2/P3=0`、197 passed；Godot/API `P0/P1/P2=0`、58 passed；19 个历史阻塞专项及 14 个畸形 SDK 响应复验通过 | 不替代用户真实窗口 UAT、GitHub Linux CI 或后续远程交付 |
| F-003 Step 6 全量门禁 | `uv run --frozen python scripts/quality.py` | pytest 262；lock 45；mypy 35 files；ruff、schema、Godot import/unit、9 个 F-002 integration、8 个 F-003 fake integration、ignore/sensitive 与 `git diff --check` 全部通过 | 该行仅记录 Step 6 本地历史门禁；真实 provider 后续调用须另外授权 |
| F-003 用户 UAT | 用户亲自运行真实 Godot 窗口并提供脱敏验收确认 | `UAT_RESULT=PASS`；真实成功回复、503/504/502 后手动 Retry 恢复、提示注入边界和发送期间按钮禁用均通过；`PORT_8000_STOPPED=YES` | 用户未单独提供 UAT 真实模型调用次数与新增费用；不保存截图、原始玩家消息或模型回复 |
| F-003 Step 7 最终本地交付门禁 | 用户 UAT 后重新运行 fake-only 统一入口和交付专项 | pytest 262；9 个健康 loopback、8 个对话 fake loopback、lock、ruff、mypy、schema、Godot、ignore/sensitive、24 个 Python 文件 format、2 个 workflow 静态测试、Markdown 链接和 diff 检查全部通过 | 本行记录 Windows 本地结果；GitHub Linux 与最终合并见 PR #3 |
| F-003 GitHub 交付与归档 | 精确暂存 56 个文件，push 功能分支、PR 和 GitHub-hosted Linux CI | 功能提交 `41527ecca161cccb4878ad5289f0b29b163e0f17`；PR #3 首个功能 HEAD 的 `Quality` 通过；任务卡与实现计划已在同一 PR 准备归档 | 归档提交会产生新 HEAD；最终 CI、合并状态和 merge SHA 以 GitHub PR #3 为准 |
| F-003 临时资源盘点 | 只读核对 F-003 登记信息、项目外集中临时根与项目忽略项 | 未发现已登记或可明确归属于 F-003 的项目外独立临时目录；`.venv`、`.env`、Godot cache 和共享工具全部保留 | 无删除授权；历史 F-001/F-002 或其他项目资源不纳入 F-003 清理范围 |
| F-004 Step 1 冻结配置 | 失败优先配置/边界测试与 fake-only 统一门禁 | 三元 scope、6 完整回合、128 会话、1800 秒 TTL、8192/64/16/256 预算和 2 秒等待均锁定；配置 142 passed，全量 366 passed | 不新增依赖或数据库；不读取 `.env`/API key |
| F-004 Step 2 有界工作记忆 | 独立 store、完整回合、单调时钟、TTL、LRU、容量和在途保护负例 | 纯内存 store 102 passed；配置+store 244 passed；全量 468 passed；跨 scope、半回合与在途驱逐均 fail-closed | 服务重启/多 worker 不保证记忆保留 |
| F-004 Step 3 预算、provider 与一致性 | provider-neutral DTO、UTF-8 边界、adapter stub、scope 串行、幂等与取消负例 | 联合定向 388 passed，全量 545 passed；唯一 persona system、8192 预算、并发≤2、Retry/replay/取消/晚到不产生伪记忆 | 预算为工程估算，不等于 provider 官方 token 数；本行为 Step 3 fake-only 历史证据 |
| F-004 Step 4 FastAPI fake 集成 | 新增 HTTP 多轮、隔离、6 回合裁剪、422/503/502/504、degraded、replay/conflict 与手动 Retry | HTTP/loopback 专项 17 passed；公开 Dialogue v1/Schema 不变，FakeProvider 历史严格受检 | 只访问测试内 ASGI 或本地 loopback，不代表真实模型评估或用户 UAT |
| F-004 Step 4 Godot 多轮 loopback | 复用真实 Godot 场景与 HTTPRequest、loopback FastAPI 和 FakeProvider | 对话 fake 场景从 8 增至 10；连续三轮、稳定 conversation、新 Send 独立 request_id、失败后冻结 payload 手动 Retry、后续历史与端口释放通过 | 不读取真实 `.env`/API key，不调用 DeepSeek，不修改 Godot 场景/客户端 |
| F-004 Step 5 真实多轮评估 | 专项授权的 FastAPI → DialogueService → DeepSeek；两条进程内合成完整历史触发预算裁剪 | 同 scope 召回、conversation/player 隔离、Nia persona、整回合裁剪、最近 6 回合和 replay 零额外调用全部通过；零 SDK retry | 合成历史只用于验收进程预算 fixture，不是已发生的真实 provider 对话；不替代独立 QA 或用户窗口 UAT |
| F-004 Step 5 真实调用台账 | 每次 provider 返回立即记录脱敏官方 usage，按峰值 cache-miss 单价保守估算 | 实际 8 次调用；后续 7 次为 6326 输入 token、86 输出 token，已记录部分费用上界 USD 0.00289696 | 首个失败请求在记录 usage 前退出，其 token 和费用无法追溯；不伪造 8 次完整总费用；Step 5 真实调用额度已用尽 |
| F-004 Step 6 首轮独立 QA | 后端 scope/TTL/LRU/预算/并发/取消，与 Godot/API 多轮 history oracle、fake-only 范围独立复审 | 历史首轮发现 P1：取消 orphan + 同 ID Retry 双 provider 调用/伪记忆；P2：assistant 污染可通过旧多轮 verifier；P3：历史 UAT 文档歧义 | 首轮后端 405 passed、Godot/API 79 passed 与 43 passed 仍未覆盖该组合；发现均已在后续专项授权中关闭 |
| F-004 Step 6 失败优先修复 | 2 个取消 orphan 同 ID 1/2 waiter Retry 负例，3 个普通多轮与 2 个失败恢复 assistant 污染负例 | 7 个负例先失败后通过；保留原 task 幂等归属、提交前验证当前 task 身份、逐条校验完整 user/assistant 真实成功历史；历史 F-003 UAT 与 F-004 未执行 UAT 已澄清 | synthetic/fake-only；不读取真实 `.env` 或 API key、不调用 DeepSeek、不修改公开契约或 Godot 场景 |
| F-004 Step 6 独立复审 | 两名 reviewer 对修复独立重建并发、历史污染、异常 role/outcome、隐私及 scope 回收负例 | 后端专项 412 passed，1/2/8/32 waiter 均仅一次 provider 调用/完整历史；Godot/API 专项 22 passed、6 个独立边界全部安全拒绝；双方 NO FINDINGS | 不替代后续用户真实窗口 UAT、真实调用精确记账或远程 CI |
| F-004 最终范围与交付门禁 | 任务卡、阶段地图、roadmap、Step 7 用户 UAT、fake-only 修复及本地门禁 | Step 0–7 完成，空历史虚构记忆已修复并经用户真实 Godot 窗口复验；完整统一门禁 pytest 584 passed，9 健康 + 10 对话 loopback 全通过；任务卡和计划在 PR #4 归档 | 最终归档 HEAD 的 GitHub Linux CI 和合并事实以 PR #4 为准；未进入 R-05；Step 5 首次失败请求 usage 缺失持续如实披露 |
| F-004 Step 7 用户 UAT 与双进程准确台账 | Windows Godot 双窗口同 scope 回忆、新 scope 隔离及两轮脱敏 usage 截图 | 真实模型同 scope 回忆通过、新 scope 不泄漏；首轮 4 次/664 输入/196 输出/USD 0.00055088，第二轮 4 次/718 输入/197 输出/USD 0.00057596；合计 8 次/1382 输入/393 输出/USD 0.00112684 | 原 Step 7 调用上限为 4 次，实际 8 次；F-004 总调用为 16 次，高于原 12 次上限；任何新增真实调用必须另行授权 |
| F-004 Step 7 空历史修复 | 6 个中英文回忆、2 个跨 scope、2 个 HTTP 失败优先负例及正常首轮信息/已有历史回归 | 10 个负例先红后绿；无历史追问返回现有 `degraded / local-fallback`，零 provider、零费用、零写入；专项 174 passed，完整 fake-only 统一入口 pytest 584 passed | 修复及最终用户窗口复验均无真实 provider 调用，不修改公开 v1、数据库或 Godot 场景 |
| F-004 已知费用边界 | Step 5 后 7 次可追溯 usage + Step 7 两轮 8 次准确 usage | 可核算部分共 15 次、7708 输入 token、479 输出 token、USD 0.00402380；实际全部请求共 16 次 | Step 5 首次失败请求的 token/费用无法追溯，USD 0.00402380 不能冒充 16 次完整费用 |
| F-004 Step 7 用户最终窗口复验 | 用户亲自在真实 Godot 窗口追问新会话的先前代号；本地 fake 后端启动并退出 | 界面明确回答当前会话没有先前信息、因此不知道；`FAKE_PROVIDER_CALLS=0`，8000 端口已释放；用户 UAT 通过 | 该复验聚焦已修复的确定性空历史路径；真实模型同 scope 能力沿用此前已完成的用户 UAT，不新增真实调用或费用 |
| F-004 功能提交与远程 CI | GitHub PR #4、功能提交及 GitHub-hosted Linux 既定 fake-only quality workflow | 功能提交 `eb8a9cc69a93f004a346e8d27f81b10fa3c89a46`；首个功能 HEAD 的 `quality` 已通过；任务卡与计划在同一 PR 准备归档 | 归档 HEAD 必须再次通过 CI；最终 merge SHA 与合并状态以 GitHub PR #4 为准 |
| F-004 临时资源盘点 | 只读核对 F-004 登记信息、项目外集中临时根与项目忽略项 | 未发现已登记或可明确归属于 F-004 的项目外独立临时目录；`.venv`、`.env`、Godot cache 和共享工具全部保留 | 无删除授权；其他任务或其他项目资源不纳入 F-004 清理范围 |
