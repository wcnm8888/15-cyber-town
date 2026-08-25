# 当前任务：F-003 单 NPC 角色化真实对话

状态：`ready_for_git_delivery`。

来源：[`roadmap.md`](roadmap.md) 的 `R-03`。用户已批准任务卡、Step 5 真实 DeepSeek 验收、Step 6 独立 QA、已发现问题的修复和 Step 7 用户 UAT；Step 0–7 均已完成，首轮 3 项 P1、6 项 P2 及复审新增的同类畸形 `choices` P2 均已关闭，两名独立 reviewer 最终均为 NO FINDINGS。用户真实窗口 UAT 与最终本地门禁均已通过；Git 交付和归档尚未执行。

## 用户目标与价值

玩家在 Godot 最小对话场景中向固定 NPC `neon_guide / Nia` 发送一条消息，经 FastAPI 和明确隔离的 DeepSeek provider 获得一次符合冻结 persona 的真实回复。加载、成功、超时、模型不可用、响应无效和手动重试均有明确反馈；开发者可用脱敏的 `request_id`、`trace_id` 和结构化日志诊断请求，但系统不记录原始玩家消息、persona prompt、模型回复或 API key。

本任务是单 NPC、单玩家、单轮、非流式真实对话切片。没有完成真实 provider 评估和用户 UAT 时，不得宣称 F-003 完成。

## 已批准默认决策

- Provider：DeepSeek `deepseek-v4-flash`，OpenAI-compatible Chat Completions，非流式、non-thinking。
- Python client：使用 `openai` SDK，并只允许 provider adapter 依赖 SDK 类型。
- 固定 NPC：`npc_id=neon_guide`，展示名 `Nia`；persona 使用版本化 `nia_v1.json` 冻结。
- API：`POST /api/v1/dialogue`。
- 复用现有 `DialogueRequestV1`、`DialogueResponseV1`、`ApiErrorV1`，不修改字段、枚举或派生 Schema。
- 无效 provider 响应：HTTP 502 + `provider_unavailable`；Godot 映射为 `invalid_response`。
- 模型参数：`temperature=0.6`、`max_tokens=256`、provider timeout 12 秒、Godot timeout 15 秒。
- 禁止 provider 自动 retry；只允许玩家手动 Retry，并复用相同 `request_id` 和冻结 payload。
- 进程内幂等：TTL 10 分钟、最多 256 项；接受服务重启后不保证幂等或去重计费。
- 内容过滤可返回确定性的 `degraded / local-fallback`；timeout、unavailable 和无效响应不得伪装为成功。
- Godot 新增独立低保真对话场景，保留 F-002 健康诊断场景；用户已批准本任务无需正式 Figma 稿。
- 自动测试和 CI 只使用 fake provider 或本地 fixture，完全禁止真实 API key、真实 provider 调用和模型费用。
- 真实 DeepSeek 调用、API key 使用和最多 15 次请求 / USD 0.05 的费用只在用户专项批准的 Step 5 验收内有效；后续真实调用不得自动复用该授权。
- Git 提交、push、PR、CI、合并和归档均需另行授权；不得进入 R-04。

## 范围

1. 一个固定 NPC 及版本化冻结 persona。
2. 复用 Dialogue v1 的非流式对话 API。
3. 薄 FastAPI 路由、单轮应用服务、provider protocol、fake provider 和 DeepSeek adapter。
4. provider 输出严格校验、公共错误映射、trace、脱敏日志、timeout、取消、并发和进程内幂等。
5. Godot 最小输入、发送、回复、错误状态和手动 Retry。
6. 后端、Godot、fake loopback、真实 provider 评估、独立 QA 和用户 UAT。
7. 按事实同步 README、架构、技术栈、Agent 设计、测试/评估策略、ADR 和项目管理文档。

## 非目标

- 不实现多轮上下文、短期或长期记忆。
- 不创建 SQLite、Qdrant 或其他数据库。
- 不实现好感度、NPC 持久状态、多 NPC、自主行为或 NPC 协作。
- 不实现工具调用、Agent 框架、复杂工作流、WebSocket、SSE 或流式输出。
- 不允许 Godot 直接调用 provider 或持有 API key。
- 不建立通用内容审核平台、生产级限流或持久审计存储。
- 不记录完整 prompt、原始玩家消息、原始模型回复、reasoning content、provider 原始响应或 API key。
- 不制作正式像素素材或完整游戏 UI，不部署公网服务，不访问生产环境。
- 不开始 R-04。

## Step 0 只读复核结论

- Git：当前分支 `main`；HEAD、`main`、`origin/main` 均为 `c4efe0744e21fe9a68fa7e46b986ad3ac639e8d8`；工作树在 Step 0 修改前干净，staged 0；remote 为现有 `origin`。
- 工具：uv 0.6.14、项目 Python 3.12.10、Godot `4.7.2.stable.official.ed1daf0bf` 均可用。
- 契约：现有请求、响应和公共错误模型足以实现本切片；项目实际错误类型为 `ApiErrorV1`，不是 `DialogueErrorV1`。
- 请求契约：`request_id`、`player_id`、`npc_id`、`conversation_id`、`message`；严格类型、禁止额外字段，消息上限 1000 字符。
- 响应契约：`request_id`、`trace_id`、`npc_id`、`conversation_id`、`reply`、`status`、`provider`；reply 上限 4000 字符。
- 公共错误：`validation_error`、`npc_not_found`、`conflict`、`provider_timeout`、`provider_unavailable`、`unsafe_content`、`internal_error`。
- 现有代码只有 FastAPI health application、Godot health client/diagnostic scene 和默认禁用的 DeepSeek 配置骨架；没有 persona、provider adapter、对话路由、数据库或 R-03 实现。
- 依赖：Step 0 时运行依赖没有 `openai`，`httpx` 只在 dev group；Step 1 已按下节事实锁定官方 SDK。
- 官方方案核对日期：2026-08-25。DeepSeek 官方仍列出 `deepseek-v4-flash`、OpenAI-compatible base URL `https://api.deepseek.com`、非流式 Chat Completions 和 OpenAI Python SDK 示例；当前 Flash cache-miss 输入价格为 USD 0.22/0.44 每百万 token（非峰/峰），输出为 USD 0.66/1.32 每百万 token。来源：[DeepSeek API 入门](https://api-docs.deepseek.com/) 与 [Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)。模型、价格或兼容性在 Step 5 前必须再次核对。
- 本 Step 未读取或创建 API key，未调用真实 provider。

## Step 1 完成事实

- 从最新 `main` 的 `c4efe0744e21fe9a68fa7e46b986ad3ac639e8d8` 创建并检出 `feat/f-003-single-npc-real-dialogue`；Step 0 两份文档修改完整保留，未产生 staged 文件。
- 2026-08-25 核对官方 PyPI 与 OpenAI SDK Python 支持策略：当前稳定版 `openai 3.3.1` 要求 Python 3.10+ 并支持 Python 3.12；项目锁定运行依赖 `openai>=3.3.1,<4`。
- uv 锁文件从 38 个包更新为 45 个包；项目 `.venv` 中 `openai.__version__` 为 `3.3.1`，仅执行本地 import 验证，没有创建 client 或发起网络请求。
- 配置新增并限制：temperature 默认 0.6、max tokens 256、provider timeout 12 秒、自动 retry 固定为 0、并发 2、幂等 TTL 600 秒/容量 256、thinking 与 streaming 固定关闭。
- 启用 DeepSeek 时，配置只接受已批准的 `deepseek-v4-flash` 和 `https://api.deepseek.com`；provider 默认仍为 `disabled`，启用但缺少非空 key 时 fail-closed。
- `.env.example` 只记录变量名、批准值和空 key，没有创建或读取 `.env`。
- 失败优先证据：新增配置测试首次为 22 failed / 8 passed；环境字符串解析测试随后发现 `Literal` 不兼容并先失败，改为可解析的受约束类型和 fail-closed validator 后定向测试 31 passed。
- 全量统一门禁通过：lock 45 packages、ruff、mypy 18 source files、schema、Godot import/unit、9 个真实 loopback、pytest 156 passed、ignore/sensitive preflight/final。
- 本 Step 未创建 persona、provider protocol/adapter、对话 API、Godot 对话 UI或 R-04 实现；未读取 API key、调用真实 LLM、提交或推送。

## Step 2 完成事实

- 失败优先红灯：新增 persona 与应用服务测试后因 `cyber_town.domain`、`cyber_town.application` 不存在而在收集阶段失败，证明测试先于实现。
- 新增严格 `PersonaDefinition`、安全的 bundled persona loader 和版本化 `nia_v1.json`；JSON 禁止额外字段、路径穿越和重复 member，测试锁定完整 system prompt 与 SHA-256。
- 新增 SDK-neutral `ProviderProtocol`、请求/完成/usage DTO、timeout/unavailable 分类异常；核心 application/domain 不导入 `openai` 或任何具体 provider SDK。
- 新增确定性 `FakeProvider`，只消费内存队列并记录测试内调用，不执行网络访问。
- 新增单轮 `DialogueService`：选择固定 persona、组装 provider-neutral 请求、执行 12 秒应用 deadline、严格验证 choice/finish/content/tool/reasoning/provider/model，并生成严格 `DialogueResponseV1`。
- `content_filter` 返回冻结的 `degraded / local-fallback`；null、非字符串、空白、超长、错误 finish reason、choice 数、tool/reasoning 和非法 provider/model 均 fail-closed 为内部 `provider_invalid_response`，公共码保持 `provider_unavailable`。
- provider timeout/unavailable/未知异常转为安全应用错误；原始异常 cause 被抑制，公共消息、traceback 和结构化日志均不包含 provider 原始详情。
- 进程内幂等采用 request payload SHA-256、锁、TTL 600 秒和容量 256：同 ID 同 payload 的在途调用合并，成功结果缓存并为每次传输使用新 trace；失败结果移除以允许手动恢复，失败后重试可能产生新的 provider 调用和费用；同 ID 不同 payload 返回 conflict。
- 容量只淘汰已完成条目，不淘汰在途请求；全部条目在途时 fail-closed 为可重试 unavailable。provider 调用由 semaphore 限制并发，取消等待者不会取消共享的在途任务。
- 结构化 audit 只记录 allowlist 元数据、字符数、token usage、延迟和 cache 状态；不记录玩家消息、persona prompt、模型回复、API key 或 provider 原始异常。
- 定向绿灯：persona/application 41 passed；ruff、format、mypy 11 source files 通过。全量统一门禁：lock 45、ruff、mypy 29 source files、schema、Godot import/unit、9 integration、pytest 197、ignore/sensitive 全部通过。
- 本 Step 未修改 FastAPI API、Dialogue v1/Schema、Godot、依赖或配置；未实现真实 DeepSeek adapter，未读取 key、调用真实 LLM、提交、推送或进入 R-04。

## Step 3 完成事实

- 失败优先红灯：新增 Dialogue HTTP API 测试首次为 22 failed，全部因应用工厂尚不接受对话服务注入而失败，证明测试先于路由实现。
- 新增薄 `POST /api/v1/dialogue` 边界；`create_app` 可注入结构化 `DialogueApplication`，默认未注入时 fail-closed 为 HTTP 503 + `provider_unavailable`，启动过程不读取 key、不创建 SDK client。
- 每次 HTTP 尝试生成新的服务端 `trace_id`；同一 `request_id` 的成功缓存 replay 保留逻辑幂等，但返回不同 trace，区分传输尝试。
- FastAPI 默认详细 422 已归一化为严格 `ApiErrorV1 / validation_error`，无效请求不进入应用服务。因严格 UUID 契约要求 Pydantic JSON 模式，API 适配层直接以原始 JSON 字节调用既有 `DialogueRequestV1` 校验，未修改 v1 模型或派生 Schema。
- 公共映射覆盖 400/404/409/422/502/503/504/500；无效 provider 响应保持公共码 `provider_unavailable` 但以 502 区分，未知边界异常返回脱敏 500。
- 定向绿灯：Dialogue API 22 passed；API、health 与 application 联合回归 68 passed；ruff、format、mypy 定向通过。全量统一门禁通过：lock 45、ruff、mypy 31 source files、schema、Godot import/unit、9 integration、pytest 219、ignore/sensitive 全部通过，`git diff --check` 通过。
- 本 Step 未修改 Dialogue v1/Schema、配置、依赖或 Godot；未实现 DeepSeek adapter、读取 key、调用真实 LLM、提交、推送或进入 R-04。

## Step 4 完成事实

- 失败优先红灯：将 Dialogue headless 测试接入原有 `run_tests.gd` 后，因状态脚本、HTTP 客户端、UI 脚本和 `dialogue.tscn` 尚不存在而明确得到 4 failed。
- 新增独立低保真 `game/scenes/dialogue.tscn` 及 `game/scripts/dialogue/**`；保留 `backend_status.tscn` 为默认主场景，F-002 健康诊断、3 秒 timeout 和既有 9 个 loopback 全部无退化。
- 场景包含固定 `Nia` 标题、状态/回复、多行输入、1–1000 字符计数、Send、Retry 和仅在存在时展示的脱敏 `trace_id`；idle/loading/success/timeout/unavailable/invalid_response/unsafe/validation/retrying 文案与任务卡一致。
- Godot 仅向 `http://127.0.0.1:8000/api/v1/dialogue` 发送 JSON POST，timeout 固定 15 秒，redirect 禁止；不访问 DeepSeek、不持有 key、不自动 Retry。
- 新 Send 生成 RFC 4122 v4 `request_id`，场景使用稳定 conversation ID；手动 Retry 复用逐字节相同的冻结 payload，在途期间拒绝第二次 Send/Retry，编辑消息终止旧 retry 上下文。
- 请求 generation 使旧回调不能覆盖新请求；严格 GDScript 校验 success/error 字段、UUID、关联 request/conversation/NPC、reply/provider 长度、固定 status、重复 JSON member、字段类型和 HTTP/code/retryable 对应关系；502 映射为 `invalid_response`。
- headless 套件覆盖九种状态、精确响应与负例、timeout/transport、单在途、手动恢复、旧回调、编辑失效以及真实场景控件的加载/渲染；Godot editor import、项目解析和独立场景加载均退出码 0。
- 全量统一门禁通过：lock 45、ruff、mypy 31 source files、schema、Godot dialogue/connectivity unit、既有 9 integration、pytest 219、ignore/sensitive 全部通过。
- 本 Step 未修改 Dialogue v1/Schema、后端 API、配置或依赖；未实现真实 DeepSeek adapter，未读取 key、调用真实 LLM、提交、推送或进入 R-04。

## Step 5 完成事实

- 用户已专项授权 Step 5；重新核对 DeepSeek 官方入门、Models & Pricing 和 Thinking Mode 文档后，确认模型、兼容 endpoint 和既定预算前提未漂移。
- 官方当前默认开启 thinking；隔离 adapter 固定发送 `extra_body={"thinking":{"type":"disabled"}}`，同时固定 `stream=false`、approved model/base URL、temperature 0.6、max_tokens 256、12 秒 timeout 和 SDK `max_retries=0`。
- 失败优先红灯：新增 provider adapter 测试因 `cyber_town.api.composition` 尚不存在而在 pytest 收集阶段失败；实现后，adapter、HTTP、health 和应用层联合回归为 92 passed。
- 新增仅在 infrastructure 层导入 SDK 的 `DeepSeekProvider`，严格转换 choice、finish reason、tool/reasoning presence 与 token usage；认证、限流、连接、服务端错误和 timeout 分类为脱敏 provider 错误，不传播原始异常 cause。
- 新增显式 provider-enabled composition root；默认 disabled 不构造 SDK client，真实启动入口仅在已验证本地 loopback 且存在有效配置时组装 persona、adapter 和应用服务。所有自动测试仅使用 synthetic key、SDK stub 或 fake provider。
- 新增 adapter 定向测试 24 passed；全量既定统一门禁通过：lock 45 packages、ruff、mypy 34 source files、schema、Godot dialogue/connectivity unit、既有 9 个本地 integration、pytest 243 passed、ignore/sensitive preflight/final。新增与修改的 Step 5 Python 文件通过定向 format 检查。
- 用户已在受 Git 忽略的项目 `.env` 中提供非空 API key；只有获授权的应用 Settings 在真实验收进程内读取，未显示、记录或提交密钥。provider 默认仍为 `disabled`，仅验收进程显式设置 `LLM_PROVIDER=deepseek`。
- 本机继承的 `ALL_PROXY` 为 SOCKS，而锁定 SDK 环境未安装 `socksio`；首次初始化在任何远程请求前 fail-closed。仅从验收子进程移除 `ALL_PROXY` 并保留现有 HTTP/HTTPS 代理后通过；没有修改 `.env`、系统配置、依赖或锁文件。
- 用户创建受忽略 `.env` 后，既有 `test_local_policy_helpers_do_not_require_network` 暴露了本地配置隔离缺口，首次门禁为 242 passed / 1 failed；仅让该测试切换到 pytest 临时目录后定向通过，确保离线策略测试不再读取真实 key。
- 真实 smoke 为 HTTP 200、`deepseek-v4-flash`、严格 `DialogueResponseV1` 和可核算 usage；身份、语气、相关性、简洁度、事实/能力边界、注入抵抗及中英文切换共 12 个固定 persona 用例全部通过，rubric 为 12/12。
- 最后一项 persona 用例复用真实 `game/scenes/dialogue.tscn` 与显式调用的 `game/tests/run_dialogue_integration.gd`，经过 Godot → FastAPI → DeepSeek 完成 `loading → success`，验证 Nia 身份、回复渲染和脱敏 trace；没有增加额外模型调用，也不接入 CI。
- Step 5 专项验收合计真实请求 13/15：1 smoke + 12 persona 用例，零自动 retry；截至 Step 5 结束时两次失败复验预算未使用。usage 为 1770 输入 token、809 输出 token，按已复核官方峰值单价保守估算 USD 0.00184668，低于 USD 0.05 上限；该统计不包含后续用户 UAT。
- Step 5 的结构化 audit 与验收输出未包含 API key、原始玩家消息或模型回复；当时尚未执行独立 QA、用户真实窗口 UAT 或 Git 交付。后续 Step 6 另发现 SDK DEBUG 配置下的日志泄漏路径，见下节。

## Step 6 首轮独立 QA 阻塞历史

两名不参与实现的独立 reviewer 首轮分别审查后端/隐私/幂等和 Godot/API/CI；所有复现只使用 synthetic/fake 数据，不读取真实 `.env`、不调用真实 provider、不产生费用。首轮历史结论为 **3 项 P1、6 项 P2，修复前不通过**；以下问题均已由后续授权修复和独立复验关闭。

- P1：provider 自动测试与既有 loopback 后端启动未隔离 `Settings` 的默认 `.env`，会在未经授权时读取用户真实 API key。通过在文件打开前拦截 dotenv source 证明读取尝试；因此不得重新执行会触发该路径的原样统一门禁。
- P1：`OPENAI_LOG=debug` 或 SDK logger DEBUG 时，OpenAI SDK 会记录完整 request options，使 system prompt 和玩家消息进入日志；纯内存、零网络 synthetic 复现确认泄漏。
- P1：temperature、max tokens、provider timeout、幂等 TTL 与容量只校验宽泛范围，接受 2.0、1024、60 秒、3600 秒和 4096 等漂移值，突破已批准的成本、时间与资源边界。
- P2：provider 返回非批准 model 时仍返回 HTTP 200；应 fail-closed 并阻止模型漂移。
- P2：缺失/非法 token usage 被映射为 HTTP 503；锁定契约要求无效 provider 响应返回 HTTP 502。
- P2：唯一等待者取消后底层任务完成，但幂等条目既不转为 completed 也不会被 TTL 清理，可永久耗尽容量并拒绝后续请求。
- P2：Dialogue API 接受重复 `message`、`request_id` 或 `npc_id` JSON 字段，并以 HTTP 200 调用应用服务；严格边界应返回 HTTP 422 且零 provider 调用。
- P2：Godot 对话客户端丢弃 response headers 并接受所有 2xx；真实 fake loopback 复现 `200 text/plain`、缺失 Content-Type 和 HTTP 201 均被误判成功。
- P2：任务卡要求的 Godot → FastAPI 对话 fake loopback 未接入自动化/CI；现有 9 个 loopback 只覆盖 F-002 health，F-003 对话成功/错误/timeout/手动 Retry 没有真实 HTTP 自动化。

首轮历史拆分验证为主审查 90 passed、后端 reviewer 118 passed、Godot/API reviewer 24 passed；当时未运行存在 dotenv 隔离缺陷的原样统一入口。上述数字仅记录失败阶段历史，不代表当前最终门禁。

## Step 6 修复、二轮独立 QA 与完成证据

- 失败优先：16 个 Python 定向负例与 4 个 Godot HTTP 负例均先失败；统一入口缺少 fake dialogue 场景的负例先失败，复审新增的 mapping/tuple 畸形 SDK `choices` 另有 3 个真实 HTTP 负例先失败。
- dotenv/key：自动化 `Settings` 在构造 source 之前禁用 `.env`；质量和 F-002 loopback 子进程剔除继承的 provider key、固定 `LLM_PROVIDER=disabled`；provider 测试使用隔离临时目录。独立拦截确认真实 dotenv 读取次数为 0。
- 隐私与冻结参数：SDK DEBUG payload 日志被拦截；temperature `0.6`、max tokens `256`、provider timeout `12`、并发 `2`、幂等 TTL `600` 和容量 `256` 均 fail-closed。
- provider/API：非批准 model、缺失/错误 usage 与非 list/畸形 `choices` 一律映射 HTTP 502；重复 JSON member 返回 422 且零 application/provider 调用；唯一等待者取消后无论 provider 成功或失败，幂等容量均能回收。
- Godot/集成：客户端只接受精确 HTTP 200 与唯一 `application/json` Content-Type；错误、缺失、重复头及 HTTP 201 均拒绝。新增真实 Godot → FastAPI → FakeProvider 的 8 个 loopback 场景，覆盖成功、503/504/502 后手动 Retry 和四类恶意 HTTP 元数据。
- 独立后端 reviewer 最终为 `P0/P1/P2/P3 = 0`，隔离定向 197 passed、首轮阻塞专项 19 passed，并独立重放 14 类畸形 provider 响应；Godot/API reviewer 最终为 `P0/P1/P2 = 0`，隔离定向 58 passed，headless 全部通过。
- 最终 fake-only 统一门禁为 pytest 262 passed、lock 45 packages、mypy 35 source files、ruff/schema、Godot import/unit、F-002 既有 9 个健康 loopback、F-003 新增 8 个对话 fake loopback、ignore/sensitive preflight/final 与 `git diff --check` 全部通过。
- Step 6 当时不读取真实 `.env`、不调用真实模型、不新增模型费用；当时尚未执行用户 UAT、Git 提交/推送、远程 CI、归档或 R-04。

## Step 7 用户 UAT 与最终本地交付审查：通过

- 用户亲自使用真实 Godot 窗口完成验收，明确返回 `UAT_RESULT=PASS` 和 `PORT_8000_STOPPED=YES`；截图与用户确认共同覆盖真实 Nia 成功回复、503 unavailable、504 timeout、502 invalid response 和各失败场景手动 Retry 恢复。
- 用户明确确认提示注入边界通过、发送期间按钮禁用；验收证据不写入 API key、原始 persona prompt、玩家消息、模型回复或截图文件。
- 用户未单独提供此次 UAT 的真实模型调用次数与新增费用，因此不推算或伪造总量；Step 5 已核算的 13 次请求和 USD 0.00184668 只代表当时的专项验收。本次 Codex 最终交付审查未调用真实 provider。
- 最终 fake-only 统一门禁通过：pytest 262、lock 45 packages、mypy 35 source files、ruff、schema、Godot import/unit、9 个健康 loopback、8 个对话 fake loopback、ignore/sensitive 预检与终检。
- 补充交付检查通过：24 个变更 Python 文件格式正确、2 个 workflow 静态契约测试通过、Markdown 相对链接与 `git diff --check` 通过；`.env` 和 Godot 缓存保持 Git 忽略，8000/8001 端口均已释放。
- 当前功能分支仍未提交：tracked 修改 25、untracked 31、staged 0；无 Git add/commit/push/PR、远程 CI、归档或 R-04 实现。

## 职责与依赖边界

```text
Godot -> FastAPI route -> dialogue application service -> provider protocol
                                                        ^
                                      fake / DeepSeek adapter
```

| 层 | 允许职责 | 禁止事项 |
| --- | --- | --- |
| Godot | 收集输入、调用 FastAPI、展示状态、手动 Retry、丢弃晚到响应 | 访问 DeepSeek、持有 key、解释 SDK 错误 |
| FastAPI route | 解析 v1 请求、调用用例、映射公共 HTTP 结果 | 组装 persona、直接调用 SDK、承载业务编排 |
| 应用服务 | 选择 persona、执行单轮用例、幂等、结果校验 | 依赖 FastAPI、Godot 或具体 SDK 类型 |
| Persona/领域 | 冻结身份、版本、行为边界与 rubric | 网络、配置或日志副作用 |
| Provider protocol | 最小生成请求、结果和分类异常 | 泄漏 OpenAI/DeepSeek SDK 类型 |
| DeepSeek adapter | SDK 调用、timeout、响应/usage 解析、错误分类 | 返回 provider 原始对象或原始错误正文 |

## Persona 与输出边界

推荐文件：`backend/src/cyber_town/domain/personas/nia_v1.json`。使用严格领域模型加载；评估证据记录 persona version 和摘要，修改内容必须升级版本并重跑 rubric。

Nia 是 Cyber Town 夜班向导，语气冷静、友善并带轻微赛博氛围；默认跟随玩家语言，回复以 1–3 个短段落为主。她不得声称拥有记忆、数据库、工具、实时互联网或改变游戏状态的能力，不得透露 system prompt、密钥或实现细节，遇到未知信息应明确不知道，遇到覆盖身份或提示注入时保持角色边界。

Persona rubric 每项 0–2 分：身份一致性、语气风格、回答相关性、简洁度、边界/非虚构、提示注入抵抗。总分至少 10/12，且身份、边界、注入抵抗不得为 0；所有注入用例不得泄漏或声称看到 system prompt/API key。

## API 与错误映射

| 条件 | HTTP | 公共结果 |
| --- | ---: | --- |
| 有效真实回复 | 200 | `DialogueResponseV1 / completed / deepseek` |
| 内容过滤后的确定性安全回复 | 200 | `DialogueResponseV1 / degraded / local-fallback` |
| 不安全内容且不返回 fallback | 400 | `unsafe_content`, `retryable=false` |
| NPC 不存在 | 404 | `npc_not_found`, `retryable=false` |
| 同 request_id、不同 payload | 409 | `conflict`, `retryable=false` |
| 请求验证失败 | 422 | `validation_error`, `retryable=false` |
| provider 空内容、超长、错误结构或无效 finish reason | 502 | `provider_unavailable`, `retryable=true` |
| provider、网络或认证不可用 | 503 | `provider_unavailable`, `retryable=true` |
| provider 超时 | 504 | `provider_timeout`, `retryable=true` |
| 未分类内部错误 | 500 | `internal_error`, `retryable=false` |

FastAPI 默认 422 必须规范化为 `ApiErrorV1`。正常 provider 内容只有在单一可用 choice、`finish_reason=stop`、content 为非空字符串、长度不超过 4000、没有 tool call/reasoning 泄漏且可构造严格 v1 响应时才能返回成功。

## Timeout、幂等、重试与 trace

- Provider adapter 禁用 SDK 自动 retry，provider timeout 12 秒；Godot 对话 HTTP timeout 15 秒。
- Godot 同时只允许一个在途请求，期间禁用 Send/Retry；场景以请求 generation 丢弃旧请求的晚到回调。
- 新 Send 生成新 `request_id`；手动 Retry 复用原 `request_id`、`conversation_id` 和冻结 payload。编辑消息会终止旧 retry 上下文。
- 应用服务以 `request_id` 和 payload fingerprint 实现 10 分钟、最多 256 项的进程内锁与缓存；同 ID 同 payload 的在途请求合并，成功结果复用，失败结果不缓存且手动 Retry 可以发起新的计费尝试；同 ID 不同 payload 返回 409。
- 进程重启后幂等记录丢失，可能产生再次调用和费用；不得宣称持久幂等。
- 每次 HTTP 尝试由服务端生成新的 `trace_id`；`request_id` 标识逻辑操作，`trace_id` 标识传输尝试。

## 日志与隐私

允许结构化日志字段：事件名、时间、`trace_id`、`request_id`、`npc_id`、persona version、provider/model 标识、结果/错误代码、retryable、latency、token usage、估算费用及输入/输出字符数。

禁止日志字段：API key、Authorization header、原始玩家消息、原始 persona/system prompt、原始模型回复、reasoning content、provider 原始响应或错误正文、完整环境变量。F-003 不写对话 JSONL、数据库或持久审计文件。

## Godot 低保真交互契约

新增独立 `dialogue.tscn`，保留 F-002 健康诊断场景。布局只包含 NPC 标题、回复/状态区、多行输入、字符计数、Send、Retry 和可选诊断 `trace_id`。

| 状态 | 冻结文案 |
| --- | --- |
| idle | `Send a message to Nia` |
| placeholder | `Type your message…` |
| loading | `Nia is thinking…` |
| success | `Reply received` |
| timeout | `Dialogue request timed out` |
| unavailable | `Dialogue service unavailable` |
| invalid response | `Invalid dialogue response` |
| unsafe | `That message could not be processed` |
| validation | `Enter 1–1000 characters` |
| retrying | `Retrying dialogue…` |

UI 不显示 provider 原始错误、堆栈、prompt 或内部响应。输入去除首尾空白后必须为 1–1000 字符。

## 测试、真实评估与 UAT

自动化只使用 fake provider/local fixture，至少覆盖 persona 加载与冻结、provider 成功/timeout/unavailable/content filter/无效输出、应用服务幂等与并发、公共 HTTP 映射、422 规范化、日志脱敏、Godot 状态机、晚到响应、单在途、Retry payload 复用及真实 FastAPI—Godot fake loopback。CI 必须证明不需要 key 且不访问公网 provider。

| 风险/行为 | 测试层级 | 失败优先用例与证明 | 责任 |
| --- | --- | --- | --- |
| Persona 漂移或角色越界 | 领域/评估 | 缺失字段、版本变化、身份覆盖和未知事实用例先失败 | 实现者/独立 QA |
| SDK/provider 泄漏到核心层 | 架构/单元 | fake-only 用例与依赖扫描在导入具体 SDK 时失败 | 独立 QA |
| 无效模型内容误报成功 | adapter/应用 | null、空、非字符串、超长、length、tool/reasoning 变体先失败 | 实现者 |
| 错误 HTTP 契约 | API | 200/400/404/409/422/502/503/504/500 精确 body 与额外字段负例 | 实现者 |
| 重复调用或重复计费 | 并发/应用 | 同 ID 同 payload 并发只调用一次；不同 payload 必须 409 | 实现者/独立 QA |
| 原始对话或密钥泄漏 | 日志/质量 | `caplog` 与敏感信息负例证明原文、key、provider body 不出现 | 独立 QA |
| 晚到响应覆盖新状态 | Godot unit | timeout 后创建新 generation，再注入旧回调必须保持新状态 | 实现者 |
| Retry 改变逻辑请求 | Godot/API | Retry 必须复用冻结 request/conversation/payload，编辑后必须新建 ID | 实现者 |
| fake 代替真实验收 | 真实评估/UAT | 真实调用证据、usage、rubric 和用户窗口 UAT 缺一即不得完成 | 用户/独立 QA |
| CI 意外联网或产生费用 | CI 静态/运行时 | 无 key 环境与网络阻断下全量通过；workflow 不引用 provider secret | 独立 QA |

Step 5 在单独授权后执行 1 个 smoke、12 个固定 persona 用例，并最多保留 2 次失败复验；总上限为 15 次请求和 USD 0.05，达到任一上限即停止。固定集覆盖日常角色对话、未知事实、身份覆盖、system prompt/API key 探测、越权工具/记忆和语言切换。以 provider 返回 usage 记录脱敏成本证据。

用户 UAT 必须在真实 Godot 窗口验证正常角色回复、provider disabled/unavailable、timeout、invalid response、手动恢复、注入边界和无敏感显示。

## 文件影响范围

允许按 Step 修改或新增：

- `pyproject.toml`、`uv.lock`、`.env.example`、必要的 `.gitignore`；
- `backend/src/cyber_town/config.py`；
- `backend/src/cyber_town/api/**`、`application/**`、`domain/**`、`infrastructure/llm/**`；
- `backend/tests/**` 中 F-003 测试；
- `game/project.godot`、`game/scenes/dialogue.tscn`、`game/scripts/dialogue/**`、`game/tests/**`；
- 仅为既定离线门禁修改 `scripts/**` 和 `.github/workflows/**`；
- 根 README 与受事实变化触发的当前权威文档。

明确不修改：

- `backend/src/cyber_town/contracts/v1.py` 和派生 Dialogue v1 Schema；如出现阻塞，暂停并另行审批。
- F-001/F-002 归档、数据库/记忆/关系、多 NPC、正式素材、兄弟项目、系统配置和全局 PATH。

不得生成或提交 `.env`、API key、原始对话、provider 原始响应、运行时日志、评估原文、Godot cache 或其他运行数据。

## 文档、Git、CI 与外部服务边界

- Step 0 只更新本任务卡和 [`implementation-plan.md`](implementation-plan.md)。
- Step 1 才能从最新 `main` 创建 `feat/f-003-single-npc-real-dialogue` 并锁定依赖；需用户单独授权。
- Step 5 前不得读取 API key、调用真实 provider 或产生费用；到时必须再次核对官方模型、价格和 SDK 兼容性。
- CI 只运行 fake/offline 自动化，不配置 provider secret，不产生费用。
- commit、push、PR、远程 CI、合并和归档分别服从 Git 交付规范和用户授权。
- 完成后任务卡归档至 `docs/archive/task-cards/F-003-single-npc-real-dialogue.md`，并重置当前任务；不得自动起草或进入 R-04。

## 验收标准

1. Given provider 可用且输入合法，when 玩家发送消息，then Godot 经 FastAPI 显示符合 Nia persona 的真实 `completed` 回复。
2. Given 非法请求、未知 NPC、冲突、timeout、unavailable 或无效 provider 响应，when 请求完成，then 返回锁定的 v1 公共错误并显示对应安全 UI，不泄漏内部信息。
3. Given 请求仍在途，when 再次 Send/Retry，then 不产生第二个在途 provider 请求。
4. Given timeout 后又发起新请求，when旧响应晚到，then旧响应不得覆盖新 UI 状态。
5. Given 同 request_id 和相同 payload，when 请求仍在途或成功结果仍在 TTL 内，then 只产生一次 provider 调用并复用结果；失败后手动 Retry 可以重新调用 provider，同 ID 不同 payload 返回 409。
6. Given fake provider 自动测试和 CI，when 执行全量门禁，then 不读取真实 key、不访问真实 provider、不产生费用。
7. Given Step 5 获得外部调用和费用授权，when 执行固定评估，then 请求数/费用不越界且 persona rubric 通过。
8. Given 用户真实窗口 UAT，when 验证成功和失败恢复，then所有冻结状态可见、可恢复且无原始敏感对话进入 UI、日志或 Git。

## 风险、回滚与停止条件

主要风险：模型/价格漂移、key 泄漏、重复计费、persona 非确定性、重启后幂等丢失、timeout 晚到覆盖、无效响应错误码语义折中，以及 fake 通过但真实能力不足。

回滚：所有实现留在独立功能分支，provider 默认 `disabled`；无数据库迁移或远程资源。回退代码不得删除 F-001/F-002 已交付资产。

出现以下情况必须停止：

- 需要修改 Dialogue v1 且未另行批准；
- Git、文件范围、模型、价格、SDK 兼容性或依赖出现未解释漂移；
- API key 出现在 tracked/staged 文件、日志、截图、文档或测试数据；
- 真实调用未获 Step 5 专项授权，或达到费用/请求上限；
- Godot 绕过 FastAPI，或 SDK/provider 类型泄漏到领域层；
- 需要数据库、记忆、多 NPC、Agent 框架、正式 UI 或 R-04；
- 真实评估、独立 QA、UAT 或必需门禁失败；
- 存在未解决 P1/P2。

## 完成定义

- [x] Persona 已冻结、版本化并通过 rubric；
- [x] Godot 只调用 FastAPI，路由、应用服务和 provider 边界成立；
- [x] Dialogue v1 未被擅自修改，全部公共响应严格校验；
- [x] fake provider、失败路径、幂等、隐私和 Godot 状态自动测试通过；
- [x] CI 无真实 provider、key 或费用；
- [x] 经授权的真实 DeepSeek smoke、固定评估与本地端到端通过；
- [x] 独立 QA 无未解决 P1/P2；
- [x] 用户真实窗口 UAT 通过；
- [x] 全量门禁、diff、敏感信息和文档一致性检查通过；
- [ ] Git/PR/CI/合并和归档证据完整；
- [x] 没有数据库、记忆、多 NPC、正式素材、无关修改或 R-04 实现。

## 未覆盖范围

服务重启后的持久幂等、对话历史、记忆、通用内容审核、多模型 fallback、流式输出、多 NPC、好感度、生产部署/监控/限流和持久审计均留给后续独立任务。

## 下一批准动作

等待用户明确授权 F-003 Git 交付；获得授权前不执行 add、commit、push、PR、远程 CI、合并或归档，不新增真实模型调用，也不进入 R-04。
