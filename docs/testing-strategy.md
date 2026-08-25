# 测试策略与质量门禁

## 测试分层

| 领域 | 自动测试 | 人工/独立验证 |
| --- | --- | --- |
| 领域规则 | NPC scope、关系状态机、好感度映射、token 预算、记忆冲突/遗忘的单元与性质测试 | 审查规则是否符合产品意图 |
| API | schema、400/404/409/422、幂等、超时和 provider 错误映射的集成测试 | FastAPI OpenAPI 与 Godot 契约对照 |
| LLM 适配 | 结构化输出校验、重试/降级、无效响应、内容过滤 | 小样本真实模型基准；不得用 mock 宣称真实能力 |
| 持久化 | SQLite 约束、事务、重启恢复、scope 隔离与迁移 | 数据生命周期和备份审查 |
| Godot | GDScript 可加载、API 客户端错误/加载状态、单场景流程 | 最小场景操作录像/截图、Godot 控制台检查 |
| 安全 | 注入、敏感内容、越权、日志脱敏、限流负向案例 | 人工 red-team 清单 |
| 端到端 | 单 NPC 成功、失败、超时、重试、隔离回归场景 | 试玩者按脚本完成 UAT |

## 任务门禁

每张任务卡从验收与风险选择具体命令，至少记录：命令/步骤、预期、实际、覆盖范围、未覆盖范围与风险。代码任务的最低集合是相关测试、lint/formatter、typecheck、构建（若存在）、差异与敏感信息检查；Agent 任务额外检查 schema、trace、失败兜底和回归 case。

UI 必须经过设计稿确认、冻结参考、同尺寸真实截图、用户视觉确认；自动化测试不能替代视觉验收。实现者不能是唯一验收者；高风险状态机、权限、审计和外部 provider 降级至少增加独立审查。

### 当前统一入口

运行 `uv run --frozen python scripts/quality.py`。入口先执行 ignore/敏感信息预检，再执行 lock freshness、ruff、mypy、schema drift、Godot editor import、GDScript 单测、9 个健康 loopback、10 个对话 fake loopback 和 pytest，最后复查仓库策略。每个子进程禁用 dotenv、移除继承的 provider key 并固定 provider 为 disabled；不需要真实凭证、真实 LLM、外部数据库或业务外部服务，F-005 仅使用 pytest 隔离的标准库 SQLite。

负向测试覆盖：worktree/index 内容分叉、staged/missing `.gitignore`、symlink/异常 mode、大小写与多种配置语法凭证键、精确 placeholder、BOM/非 UTF-8/超大文本、二进制魔数伪装、结构化配置重复键/递归/过深输入 fail-closed、敏感预检顺序、子命令缺失与失败传播、配置环境隔离、未知/多余 schema drift，以及用 Draft 2020-12 validator 在不依赖可选 format assertion 的情况下验证合法与非法 request/response/error fixtures。socket monkeypatch 只证明本地策略 helper 不触网；统一入口的离线边界由命令白名单、无外部服务配置和独立 QA 共同验证，不把该单元测试夸大为操作系统级断网证明。

GitHub Actions 在 `main` push、pull request 和人工触发时先执行 `uv sync --locked --all-groups`，再运行完全相同的质量入口。workflow 不使用 secrets、写权限、服务容器或发布步骤。本地 UAT、等价复现、最终独立审查和 PR #1 的 GitHub-hosted Linux runner 验证均已通过。

### F-002 自动化与 UAT 分工

- API 测试覆盖 200、JSON Content-Type、精确三字段、无额外字段、GET-only、无 socket/database 副作用和启动入口。
- GDScript 单测覆盖五态文案、严格响应解析、非 2xx、空/非法 JSON、缺失/额外/错误字段、timeout、传输失败、单在途请求和 retry。
- `scripts/connectivity_integration.py` 使用真实 HTTPRequest：无监听服务、503、重复 JSON key、非字符串字段、redirect 拒绝、真实 FastAPI、503→retry、非法 JSON→retry、延迟→timeout→retry，共 9 个场景；redirect target 必须零请求，每个 owned process/listener 都必须退出并释放端口。
- 自动化只验证状态机、场景资源和真实 loopback 通信。用户 UAT 仍需在真实窗口观察布局、冻结文案、按钮可操作性及启动/停服后的恢复，不得由 headless 结果替代。
- CI 在 runner bootstrap 下载官方 Godot 包；质量阶段只访问 runner loopback。F-002 的远程 CI 与合并结果由 PR #2 记录。

### F-003 自动化、真实评估与 UAT 分工

- Python 自动测试覆盖 persona loader、provider-neutral application、幂等/并发/取消、DeepSeek SDK adapter stub、HTTP Dialogue v1、公共错误、SDK DEBUG 脱敏、冻结配置、畸形 provider model/usage/choices 和重复 JSON；provider 测试使用 pytest 临时工作目录，质量子进程禁用 dotenv 并移除真实 key。Godot 单测覆盖九态、严格响应、唯一 JSON Content-Type、精确 HTTP 200、晚到回调、单在途和冻结 Retry payload。
- F-003 建立的 `scripts/dialogue_integration.py` 与 `game/tests/run_dialogue_fake_integration.gd` 最初包含 8 个真实 loopback 场景，覆盖 FastAPI + fake provider 成功、503/504/502 后手动 Retry 恢复，以及错误/缺失/重复 Content-Type 和 HTTP 201 拒绝；F-004 在同一入口扩展至 10 个场景，严格检查 fake 调用次数、冻结 payload 和端口释放。
- `game/tests/run_dialogue_integration.gd` 只在显式命令下运行真实对话场景，不接入统一质量入口或 CI；输入只通过验收进程环境传入，输出只含状态、回复字符数、trace/身份布尔值，不打印输入或回复正文。
- 获专项授权的 Step 5 真实测试为 1 smoke + 12 persona 用例，最后一项复用 Godot 端到端；13 次真实调用、rubric 12/12 和费用上界均通过。
- Step 6 首轮独立 QA 发现的 3 项 P1、6 项 P2，以及复审新增的同类畸形 `choices` P2 均已完成失败优先修复；两名独立 reviewer 最终均为 NO FINDINGS。Step 7 用户真实窗口 UAT 已明确通过，覆盖真实成功回复、503/504/502 失败状态、手动 Retry 恢复、提示注入边界和发送期间按钮禁用；自动化、真实 headless 端到端或模型 rubric 不替代该人工验收。

### F-004 fake-only 多轮、真实评估与 UAT 分工

- store/配置单元覆盖三元 scope、6 完整回合、128 sessions、1800 秒 TTL、确定性 LRU、在途保护、容量耗尽和被冻结的 8192/64/16/256/2 秒参数。
- provider/application 单元覆盖 SDK-neutral history DTO、唯一 persona system、UTF-8 中文/emoji/组合字符、整回合裁剪、scope 串行/全局并发、幂等共享、取消和晚到不写。
- FastAPI + FakeProvider 集成覆盖连续多轮、player/conversation 隔离、unknown NPC、6→7 裁剪、422、503、502、504、degraded、成功 replay、409 conflict 和失败后手动 Retry 不产生伪记忆。
- 现有 Godot 场景和客户端不修改；10 个真实本地 loopback 包含原有 8 场景，以及连续三轮同 scope 和第二轮 503 → 手动 Retry → 第三轮。验证稳定 conversation_id、新 Send 独立 request_id、Retry 冻结 payload、完整历史及端口释放。
- 真实 provider 多轮评估仅在单独授权的 Step 5 执行；独立 QA 在 Step 6；真实窗口用户 UAT 及准确调用/token/费用记录仅在另行授权的 Step 7 执行，均不得用 fake 成功替代。
- Step 7 首轮真实窗口 UAT 发现空历史模型虚构既往代号；新增中英文、跨 scope 与 HTTP 负例锁定：没有可用历史且明确追问先前交流时必须返回确定性 `degraded / local-fallback`，不得调用 provider、产生费用或写入记忆。用户随后亲自在真实 Godot 窗口复验该确定性路径并确认 `FAKE_PROVIDER_CALLS=0`；真实模型同 scope 回忆沿用此前已通过的独立用户 UAT。

### F-005 长期事实、golden set 与预算台账分工

- SQLite/领域/application 自动测试覆盖双元 scope、四类低敏感白名单、版本化 schema、参数化查询、30 天 TTL、64/4096 活跃容量、更新 version、正文清空 tombstone、事务 rollback、2 秒锁等待、重启恢复与 request 指纹幂等；所有数据库仅创建在 pytest `tmp_path`。
- 检索/provider 自动测试覆盖精确 key、固定中英文别名、确定性排序、最多 4 条召回、唯一 persona system、不可信 user 事实、2048 长期预算、8192 总预算、256 回复预留以及整条事实/完整回合裁剪。
- 已有真实 Godot 场景通过 loopback FastAPI、隔离 SQLite 与 FakeProvider 验证“记住 → 召回 → 忘记 → 明确不知道”；同 conversation 遗忘后，即使短期历史中存在旧值，也不得重新调用 provider 或复活事实。
- 版本化 72 项 golden set 验证 precision `1.00`、recall `1.00`，scope 泄漏、遗忘/过期召回、旧值复活与空结果虚构均为 `0`。另有跨进程台账和计量 provider 负例覆盖预留、费用/次数上限、unknown fail-closed、子进程与并发竞争、usage 先落账和 metadata-only schema。
- Step 6 失败优先负例额外覆盖默认 FastAPI 装配、跨路径/跨重启 request 冲突、正数 usage、仅本 scope 过期、合法 golden 组成、实际测量 baseline、低敏感中英文 topic 许可词汇及 SQLite 故障 503；更新/遗忘后的 NFKC/casefold 旧值、跨 conversation 历史、在途 provider 和已完成幂等缓存均不得复活旧事实。
- 默认启动链路 FakeProvider 测试必须同时 monkeypatch composition 项目根与 `data/` 到 pytest `tmp_path`，只修改 cwd 不足以隔离正式路径；durable Remember/Forget replay 不得清除有效新值历史或中断合法在途请求。
- 当前全量统一入口 `1095 passed`，mypy 覆盖 57 个文件；后端独立复审 `274 passed / 3 deselected`，Godot/API 独立复审 `360 passed`，两人均 NO FINDINGS；自动化、统一入口与 CI 仍永久 fake-only。Step 5 真实评估为 7 次、1244 输入/106 输出 token、USD 0.000690。Step 7 用户真实窗口 UAT 已使用隔离 SQLite 与计量台账通过 unknown、记住、跨窗口/重启召回、更新、遗忘及最终 unknown，实际 3 次、500 输入/141 输出 token、USD 0.000408；任务累计 10 次/USD 0.001098，pending=0。误创建的正式路径 SQLite 文件已按用户单独明确授权定向删除，默认启动测试和本次 UAT 均未重新创建。

## F-003 已归档首切片验收状态

1. 已实现并自动验证玩家可在固定 Godot 场景发出一条对话；响应包含并展示脱敏 `trace_id`。
2. 已自动验证 API 对非法 NPC、空/超长输入、重复 request、模型超时/无效输出返回可预测错误或降级结果。
3. 固定 Nia persona 真实评审集已通过；F-004 已在 fake-only 自动化中额外验证玩家、NPC 和会话隔离及短期记忆串扰，多 NPC 实现仍不在范围内。
4. 审计记录不保存 API key、完整原始敏感内容或模型内部推理；错误分类、耗时和 token/cost 字段可检查。
5. F-003 的 Godot headless 真实端到端和用户真实窗口 UAT 均已通过；用户确认完整窗口成功、失败状态及手动 Retry 恢复。F-004 用户真实窗口已独立验证真实模型同 scope 回忆和新 scope 隔离，修复后又亲自复验空历史明确“不知道”，`FAKE_PROVIDER_CALLS=0`；不复用 F-003 的 UAT 结论。
