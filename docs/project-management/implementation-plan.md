# 当前实现计划：F-003 单 NPC 角色化真实对话

状态：`ready_for_git_delivery`。

本计划服务于已批准的 [`F-003` 任务卡](current-task.md)。各 Step 只能在前一 Step 证据通过且取得用户明确授权后执行；F-001、F-002、外部调用和 Git 授权均不得复用。

## Step 地图

| Step | 状态 | 范围 | 主要验证与停止条件 |
| --- | --- | --- | --- |
| Step 0 | `completed` | 落盘批准任务卡与计划；只读复核 Git、契约、工具、官方 provider 资料和依赖方案 | 只修改两份项目管理文档；不建分支、不装依赖、不接触 key、不调用 LLM |
| Step 1 | `completed` | 从最新 `main` 创建 F-003 分支；选择、加入并锁定稳定 `openai` SDK；补安全配置和负向配置测试 | Python 3.12/现有依赖兼容；provider 默认 disabled；无 key、网络调用或业务实现 |
| Step 2 | `completed` | 失败优先实现 persona、provider protocol、fake provider、应用服务、输出校验和进程内幂等 | 单元测试覆盖成功、异常、并发、去重、日志脱敏；不实现 HTTP/Godot/真实 adapter 调用 |
| Step 3 | `completed` | 失败优先实现 `POST /api/v1/dialogue`、依赖注入、422 规范化和公共错误映射 | API 契约/副作用/错误矩阵通过；不修改 Dialogue v1、不调用真实 provider |
| Step 4 | `completed` | 实现独立 Godot 对话场景、HTTPRequest client、冻结 UI 状态、晚到响应和手动 Retry | headless 红绿灯、场景加载、状态/严格解析/并发测试通过；保留 F-002 健康诊断 |
| Step 5 | `completed` | 隔离 DeepSeek adapter、离线负向测试、本地组装、真实 smoke、12 项 persona 评估和 Godot 真实端到端均通过 | 实际 13 次请求，按峰值单价估算 USD 0.00184668；rubric 12/12；真实调用不进入统一 CI |
| Step 6 | `completed / independent_qa_passed` | 失败优先修复 dotenv/SDK 日志/冻结参数/provider 502/幂等/重复 JSON/Godot HTTP，并新增 8 个 fake dialogue loopback | 两名独立 reviewer 均 NO FINDINGS；pytest 262；9 个 health + 8 个 dialogue loopback 全通过 |
| Step 7 | `completed / user_uat_passed` | 用户真实窗口 UAT、最终本地交付审查和必要状态文档收口 | 用户明确 `UAT_RESULT=PASS`；pytest 262；9 个 health + 8 个 dialogue loopback 通过；状态为 `ready_for_git_delivery` |
| Git 交付 | `not_authorized` | 精确提交、push、PR、远程 CI、合并和归档 | 每项另行授权；CI fake-only；不进入 R-04 |

## Step 0 完成证据

- Git 基线：分支 `main`；HEAD、`main`、`origin/main` 均为 `c4efe0744e21fe9a68fa7e46b986ad3ac639e8d8`；Step 0 开始前工作树干净，staged 0。
- 工具：uv 0.6.14、Python 3.12.10、Godot `4.7.2.stable.official.ed1daf0bf`。
- 契约：项目实际使用 `DialogueRequestV1`、`DialogueResponseV1`、`ApiErrorV1`；字段、错误枚举和派生 Schema 不需要为 F-003 修改。
- 代码：存在 health API 与 Godot 健康诊断；不存在 persona、provider protocol/adapter、dialogue route、数据库或 R-03 业务实现。
- 依赖：`pyproject.toml` 当前没有 `openai` 运行依赖；现有 dev group 包含 HTTPX。Step 1 再选择兼容版本并锁定，不在 Step 0 变更依赖。
- 官方核对：2026-08-25 的 DeepSeek 官方资料确认 `deepseek-v4-flash`、OpenAI-compatible API、`https://api.deepseek.com`、非流式 Chat Completions 和 OpenAI Python SDK 方案；Step 5 前必须复核易变事实。
- 外部边界：没有读取或创建 API key，没有调用真实 DeepSeek，没有产生费用。

## Step 1 计划：分支、依赖和安全配置

允许在取得授权后：

1. 只读确认 Step 0 仅有 `current-task.md` 与 `implementation-plan.md` 两份修改，且 `main`/`origin/main` 未漂移。
2. 创建并检出 `feat/f-003-single-npc-real-dialogue`，完整保留 Step 0 文档修改。
3. 核对 OpenAI Python SDK 当前稳定版本、Python 3.12 支持和与现有 FastAPI/Pydantic/HTTPX 的依赖兼容性。
4. 使用 uv 加入并锁定最小 `openai` 运行依赖，不手改锁文件，不安装系统级软件。
5. 扩展现有配置以锁定 non-thinking、temperature、max tokens、provider timeout、并发和幂等参数；保持 provider 默认 disabled。
6. `.env.example` 只保存空占位和安全说明，不创建/读取 `.env` 或 API key。
7. 补配置负向测试：enabled 无 key 拒绝、disabled 不需 key、secret repr/validation 不泄漏、范围和默认值严格。
8. 运行 lock、现有统一质量入口、ignore、sensitive 和 `git diff --check`。

Step 1 不创建 persona、provider protocol/adapter、对话 API、Godot 对话 UI或真实模型调用。依赖无法兼容、配置需要修改 Dialogue v1、Git 基线漂移或敏感信息边界失败时立即停止。

## Step 1 完成证据

- 分支 `feat/f-003-single-npc-real-dialogue` 从 `main`/`origin/main` 的 `c4efe0744e21fe9a68fa7e46b986ad3ac639e8d8` 创建，Step 0 文档修改完整保留。
- 官方 PyPI 核对 `openai 3.3.1` 支持 Python 3.12；运行依赖锁定为 `openai>=3.3.1,<4`，uv lock 共 45 个包，本地 import 版本为 3.3.1。
- 新配置锁定批准默认值与安全范围：DeepSeek model/base URL、temperature、max tokens、timeout、零自动 retry、并发、幂等 TTL/容量、non-thinking 和 non-stream。
- 红灯为 22 failed / 8 passed；另一次环境字符串解析红灯证明 `Literal` 方案不兼容 `.env`。完成受约束类型和 fail-closed validator 后，配置定向测试 31 passed，ruff/mypy 定向通过。
- 全量统一门禁：lock 45、ruff、mypy 18 files、schema、Godot import/unit、9 integration、pytest 156、ignore/sensitive 全部通过。
- 项目根不存在 `.env`；未读取或创建 key，未创建 SDK client，未调用真实 provider，未实现 persona、provider、API、Godot UI或 R-04。

## Step 2 计划：领域、fake provider 与应用服务

失败测试先覆盖：persona 缺失/漂移、未知 NPC、fake 成功/timeout/unavailable/content filter/无效输出、同 ID 并发去重、同 ID 不同 payload 冲突、TTL/容量、输出边界和日志脱敏。

实现范围：

- `nia_v1.json` 与严格 persona loader；
- 不含 SDK 类型的 provider protocol、请求/结果 DTO 和分类异常；
- 确定性 fake provider；
- 单轮 dialogue use case；
- 10 分钟/256 项进程内幂等锁与缓存；
- provider 结果校验、`completed`/`degraded` 和公共应用错误；
- 只记录 allowlist 字段的结构化日志。

Step 2 不实现 HTTP route、Godot、DeepSeek 网络 adapter 或真实调用。若 persona 需要动态存储、数据库或新的公共契约字段，停止并报告。

## Step 2 完成证据

- 红灯：persona/application 测试因目标 package 不存在而收集失败；隐私复审另以 traceback 泄漏原始 provider cause 的 2 个失败用例证明修复必要性。
- Persona：`nia_v1.json` 的完整 prompt、版本和 SHA-256 被测试冻结；严格 loader 拒绝路径穿越、额外字段、空字段和重复 JSON member。
- Provider boundary：SDK-neutral protocol/DTO/异常与离线 FakeProvider 已建立；application/domain 源码扫描和自动测试证明没有 `openai` import。
- Application：单轮编排、12 秒 deadline、严格 provider 输出校验、content-filter fallback、安全错误、allowlist audit、并发 semaphore 和进程内 idempotency 已实现。
- Idempotency：在途相同请求合并，成功 replay 复用且 trace 独立；不同 payload conflict；失败不缓存以支持手动恢复；TTL 到期重新调用；容量不驱逐在途任务。
- 隐私修复：provider 原始异常不再作为可打印 cause 传播；玩家原文、模型回复、persona prompt 和异常详情均未进入普通日志或 traceback。
- 定向为 41 passed，ruff/format/mypy 通过；全量为 lock 45、ruff、mypy 29 files、schema、Godot import/unit、9 integration、pytest 197、ignore/sensitive 全部通过。
- 未修改 API、Dialogue v1/Schema、Godot、依赖或配置；未创建真实 adapter、读取 key、调用 LLM、提交、推送或进入 R-04。

## Step 3 计划：FastAPI 对话边界

失败测试先覆盖 HTTP 200/400/404/409/422/502/503/504/500、精确 v1 body、无额外字段、错误方法、无效请求不调用 provider、FastAPI 默认 422 不泄漏，以及 application factory 可注入 fake provider。

实现 `POST /api/v1/dialogue` 薄路由、应用服务注入、服务端 `trace_id`、公共异常处理和 provider-disabled 映射。路由不组装 persona、不导入 SDK、不访问数据库。Step 3 的全部自动化仍使用 fake provider。

## Step 3 完成证据

- 红灯为 22 failed：`create_app` 不接受 `dialogue_service`，所有新 HTTP 契约测试先失败。
- `POST /api/v1/dialogue` 只负责严格请求解析、调用注入的 application use case、生成逐尝试 trace 和映射公共结果；默认 provider-disabled 应用返回安全 503。
- FastAPI 422 被归一化为无字段详情的 `ApiErrorV1`；严格 UUID 使用原始 JSON 字节和既有 `DialogueRequestV1.model_validate_json`，未变更契约或 Schema。
- 200 completed/degraded 与 400/404/409/422/502/503/504/500 映射、无额外字段、错误方法、无效请求零调用、错误脱敏、缓存 replay 新 trace 和薄路由边界均有自动测试。
- 定向 Dialogue API 22 passed，API/health/application 联合 68 passed；全量统一门禁为 lock 45、ruff、mypy 31 files、schema、Godot import/unit、9 integration、pytest 219、ignore/sensitive 全部通过；`git diff --check` 通过。
- 未修改 Dialogue v1/Schema、Godot、依赖或配置；未创建真实 adapter、读取 key、调用 LLM、提交、推送或进入 R-04。

## Step 4 计划：Godot 对话场景

先证明对话脚本/场景缺失导致 headless 测试失败，再实现：

- 独立 `dialogue.tscn`；
- 输入 1–1000、字符计数、Send、reply、Retry、诊断 trace；
- loading/success/timeout/unavailable/invalid-response/unsafe/validation/retrying 状态；
- 15 秒 timeout、单在途、请求 generation、晚到响应丢弃；
- 新 Send 生成 request ID，手动 Retry 复用冻结 payload；
- 对 Dialogue v1 success/error 的严格 GDScript 解析。

使用 Godot 4.7.2 绝对路径运行 headless unit、import、脚本解析和场景加载；真实联网与 DeepSeek 留给 Step 5。现有健康诊断场景不得删除或退化。

## Step 4 完成证据

- 红灯：已接入原有 Godot 门禁的 Dialogue 测试在 4 个目标资源不存在时失败，明确列出 state/client/UI/scene 路径。
- 新增独立 `dialogue.tscn` 和 state/client/UI 脚本；F-002 `backend_status.tscn` 仍为默认 main scene，现有健康客户端、状态机和 9 个 loopback 全部保留。
- 场景实现固定 Nia 标题、多行输入与 1–1000 字符计数、冻结九态文案、Send/Retry、验证后回复及可选安全 trace。
- HTTP 客户端固定本地 Dialogue v1 URL、POST、JSON、15 秒 timeout、禁止 redirect 和单在途；新 Send 生成 UUID v4，Retry 复用相同 request/conversation 和逐字节相同 payload，编辑后作废旧上下文。
- 状态模型严格校验 success/error 的字段集合、类型、重复 key、UUID、关联 ID/NPC、长度与 HTTP/error/retry 对应；timeout、unavailable、502 invalid_response 和旧 generation 回调负例均已覆盖。
- 场景实际加入 headless SceneTree 验证输入计数、Send 禁用、timeout、Retry、成功回复和 trace 渲染；Godot import、脚本解析与独立场景加载均通过。
- 全量门禁：lock 45、ruff、mypy 31 files、schema、Godot dialogue/connectivity unit、既有 9 integration、pytest 219、ignore/sensitive 全部通过；未读取 key、联网调用 provider、提交、推送或进入 R-04。

## Step 5 计划：真实 DeepSeek 验收

进入前必须取得明确授权，且用户仅通过未跟踪本地环境或进程环境提供 key。先重新核对官方模型、API、价格和 SDK 行为，再启用 adapter：

- `deepseek-v4-flash`、non-thinking、non-stream、temperature 0.6、max_tokens 256；
- SDK 自动 retry 关闭，provider timeout 12 秒；
- provider 响应、finish reason、usage 和异常严格映射；
- 不记录原始输入、prompt、回复、reasoning 或 provider body。

评估上限：1 smoke + 12 固定用例 + 最多 2 次复验，总计不超过 15 请求或 USD 0.05。任何一项 rubric 关键指标失败、费用/调用上限达到、余额/认证/网络异常、模型或价格漂移时停止；不得把 fake 结果当作真实能力证据。

## Step 5 完成证据

- 已获用户专项授权，官方资料复核确认 `deepseek-v4-flash`、`https://api.deepseek.com` 和已批准价格；发现 thinking 当前默认开启，因此 adapter 显式发送 `extra_body={"thinking":{"type":"disabled"}}`。
- 失败优先红灯为缺失 `cyber_town.api.composition` 的 pytest 收集错误；实现后 provider、HTTP、health、application 联合回归 92 passed，定向 ruff、format 和 mypy 通过。
- 隔离 adapter 固定 non-stream、12 秒 timeout、零 SDK retry 和严格 token usage，分类并脱敏认证/限流/连接/status/timeout 错误；SDK 类型不进入 application/domain。
- 启动 composition 默认 disabled、不构造 client；启用后组装冻结 persona、approved adapter 和现有对话服务，fake SDK HTTP 回归通过且没有真实网络请求。
- Adapter 定向 24 passed；统一质量门禁通过：lock 45、ruff、mypy 34 files、schema、Godot dialogue/connectivity unit、9 个 loopback、pytest 243、ignore/sensitive 全部通过；Step 5 修改 Python 文件的 format 检查通过。
- 用户提供的本地 `.env` 已受 Git 忽略，Settings 仅读取受专项授权的非空 key；provider 默认仍为 disabled，仅真实验收进程显式启用 DeepSeek，没有显示、记录或提交任何密钥。
- 首次 SDK 初始化受继承的 SOCKS `ALL_PROXY` 与缺失 `socksio` 阻断，发生在远程调用前；仅验收子进程移除 `ALL_PROXY`，保留 HTTP/HTTPS 代理，未修改系统、锁定依赖或 `.env`。
- 真实本地 `.env` 暴露既有离线策略测试未隔离配置源，首次全量结果为 242 passed / 1 failed；仅对该测试增加 pytest 临时工作目录隔离，定向复验通过，确保离线测试不读取真实 key。
- 1 次真实 smoke 返回严格 Dialogue v1、正确 provider/model 和 usage；12 项固定 persona 用例覆盖身份、中英文、语气、相关性、未知事实、提示注入、凭证/system prompt 探测及工具/记忆/数据库边界，rubric 12/12。
- 第 12 项 persona 用例复用真实 Godot 对话场景，通过 FastAPI 调用真实 DeepSeek 并观察 `loading → success`、Nia 身份、回复控件和脱敏 trace；显式 Godot runner 不加入 CI，不增加额外真实请求。
- Step 5 专项验收真实请求共 13/15，零 retry；输入 1770 token、输出 809 token，按官方峰值单价保守估算 USD 0.00184668 / USD 0.05；截至当时失败复验预算剩余 2 次，未使用。该统计不包含后续用户 UAT。
- audit 和验收输出不包含 key、原始 prompt、玩家消息、模型回复或 provider body；截至 Step 5 结束时独立 QA、用户 UAT 和 Git 交付尚未执行。

## Step 6 计划：独立 QA

独立审查者从任务卡设计负例，至少复验：Godot 不直连 provider、SDK 类型隔离、API key/原文日志、无效 provider 输出、HTTP 映射、同 ID 并发/重试计费、重启幂等限制、timeout 晚到状态、persona 注入和 CI fake-only。运行全量门禁并审阅完整 tracked/untracked diff；发现 P1/P2 时停留在 Step 6，修复需用户授权。

## Step 6 首轮独立 QA 结论：不通过

- P1：自动化 `Settings` 与既有 F-002 loopback 子进程尝试读取真实项目 `.env`，违反 fake-only/no-key 边界；拦截在文件打开前完成，reviewer 未读取任何真实凭证。
- P1：OpenAI SDK 在 DEBUG logging 下泄漏 system prompt 与玩家消息；synthetic、无网络复现确认。
- P1：批准的 temperature、max_tokens、provider timeout、幂等 TTL/容量未冻结，合法范围内漂移突破成本、响应时间与资源约束。
- P2：provider 响应 model 漂移返回 HTTP 200；无效/缺失 usage 返回 HTTP 503 而非约定 502；取消唯一等待者后幂等容量无法释放。
- P2：Dialogue API 接受重复 JSON member；Godot 接受错误 Content-Type/缺失 Content-Type/HTTP 201；F-003 缺少 Godot → FastAPI fake dialogue loopback 自动化。
- QA 合计 3 项 P1、6 项 P2。安全定向验证通过：主审查 pytest 90、后端 reviewer pytest 118、Godot reviewer pytest 24、Godot unit、lock、ruff、mypy、schema、ignore/sensitive 和 `git diff --check`。
- 原样统一质量入口会触发 `.env` 读取 P1，因此本轮未重新运行；Step 5 的 243 passed 仅作历史基线，不能用于宣称 Step 6 通过。
- 首轮当时保持 `step_6_blocked / awaiting_user_fix_authorization`；用户随后单独授权在 Step 6 内修复并重新执行独立 QA。

## Step 6 修复与最终独立 QA：通过

- 首轮 16 个 Python 负例、4 个 Godot HTTP 负例和 fake integration 门禁缺失负例先失败；后端复审额外发现畸形 SDK `choices` mapping/tuple 导致错误 500/200，对应 3 个 HTTP 负例亦先失败。
- 自动化 Settings 在 dotenv source 创建前禁用 `.env`；统一门禁和 F-002 loopback 子进程移除 provider key、固定 provider disabled；SDK DEBUG 记录被屏蔽；6 个批准运行参数固定。
- DeepSeek adapter 严格验证 model、usage 和 list 类型 `choices`，所有无效 provider 响应返回 502；取消唯一等待者后的已完成/失败 task 可回收幂等容量；Dialogue API 拒绝任意重复 JSON member。
- Godot 响应头从实际 HTTPRequest 回调传入状态机；只接受唯一 JSON Content-Type 与 HTTP 200，保留 502/503/504 手动恢复和冻结 payload。
- 新增 `scripts/dialogue_integration.py` 与 `game/tests/run_dialogue_fake_integration.gd`，通过真实 FastAPI/Godot loopback 覆盖 8 个 fake-only 场景并接入统一质量入口/既有 CI；没有引入真实 provider、key、外部调用或额外依赖。
- 后端独立 QA：P0/P1/P2/P3 均 0，隔离定向 197 passed、阻塞专项 19 passed、14 类畸形 SDK 响应均 502；Godot/API 独立 QA：P0/P1/P2 均 0，隔离定向 58 passed，Godot headless 通过。
- 完整门禁：pytest 262 passed、lock 45、mypy 35 source files、ruff、schema、Godot import/unit、9 个 F-002 integration、8 个 F-003 fake integration、ignore/sensitive 和 `git diff --check` 全部通过；仅同步当前阶段必要事实。

## Step 7 用户 UAT 与本地交付审查：通过

- 用户亲自完成真实窗口 UAT，明确返回 `UAT_RESULT=PASS`、`PORT_8000_STOPPED=YES`，并确认各失败场景手动 Retry 恢复、提示注入边界通过和发送期间按钮禁用。
- 用户 UAT 的额外真实模型调用次数与费用未单独提供；Step 5 的 13 次请求与 USD 0.00184668 仅属于其历史专项验收，不推算整体调用总量。Codex 最终审查零真实 provider 调用。
- 最终统一门禁通过：pytest 262、lock 45、mypy 35、ruff/schema、Godot import/unit、9 个健康 loopback、8 个对话 fake loopback、ignore 与 sensitive；24 个 Python 文件 format、2 个 workflow 静态测试、Markdown 相对链接和 `git diff --check` 通过。
- 用户 UAT、真实 provider 评估、独立 QA 和最终本地门禁全部通过，状态收口为 `ready_for_git_delivery`；8000/8001 均已释放，Git 交付和 R-04 尚未授权。

## 全局停止条件

- 未获当前 Step、真实外部调用、费用或 Git 授权；
- API key、原始 prompt/message/reply 或 provider body 出现在日志、证据、截图、测试或 Git；
- 需要修改 Dialogue v1、引入数据库/记忆/多 NPC/Agent 框架/流式输出或进入 R-04；
- Godot 绕过 FastAPI，或领域/应用层依赖具体 SDK；
- 模型、价格、依赖、Git 或文件范围出现无法解释的漂移；
- 任一必需门禁、真实评估、独立 QA 或 UAT 失败；
- 存在未解决 P1/P2。

## 下一批准动作

等待用户明确授权 F-003 Git 交付；授权前不执行 add、commit、push、PR、远程 CI、合并或归档，不新增真实模型调用，也不进入 R-04。
