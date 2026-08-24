# 任务卡：F-001 工程与契约基线

- 来源：roadmap `R-01`。
- 状态：`approved / local commit completed / committed_locally_awaiting_remote_delivery`。
- 分支计划：`feat/f-001-engineering-contract-baseline`，目标分支 `main`。
- 当前限制：本地提交已完成；未获新授权前不得 amend、推送、配置 remote、创建 PR、归档 F-001 或进入 R-02。

## 当前 Step 事实（2026-08-24）

- 用户已明确批准本任务卡并允许执行 Step 0。
- Git：`2.49.0.windows.1`，可用；全局提交身份已配置（未读取或记录具体值）。
- `uv`：`0.6.14`，可用。
- 原有 Python Launcher 注册的 3.10、3.12、3.13 路径失效；默认解释器仍是 `Python 3.11.0rc2`，项目不使用它。
- 用户授权后，`uv` 已在项目 `.tools/python` 安装 CPython 3.12.10，并在 `.venv` 建立锁定环境。
- 决策已锁定：Python 3.12、uv、根 `pyproject.toml`/`uv.lock`、Hatchling、`backend/src` 布局、Pydantic v2 契约唯一源、派生 JSON Schema、跨平台 Python 质量入口。
- Git 已初始化：`main` 规划基线提交 `877746d`；当前分支 `feat/f-001-engineering-contract-baseline`；无 remote。
- Step 1 已创建根 `pyproject.toml`、`uv.lock`、`.python-version`、编辑器/行尾规则、Python 包骨架、安全配置模块和 5 个配置测试。
- Step 2 已创建 strict `DialogueRequestV1`、`DialogueResponseV1`、`ApiErrorV1`、稳定枚举、确定性 schema 导出/漂移检查和三个 Draft 2020-12 schema。
- Step 3 已创建 `scripts/quality.py` 薄入口、可测试的离线质量模块、Git ignore 与敏感信息检查和 7 个质量/安全测试。
- Step 4 已创建只读、无 secrets、无服务容器的 GitHub Actions workflow，并同步 README、架构、技术、测试和 ADR。
- Step 5 首轮独立 QA 为 12 pass / 4 fail；失败及专项审查发现已修复。全新独立复验又发现 Windows Git index mode `120000` 绕过，修复后由同一独立 QA 按原复现复验通过。
- Step 6 用户 UAT 在独立 E 盘环境通过；后续 P1/P2 修复、负向测试和独立交付审查均在授权范围内完成。
- 当前门禁：统一命令通过；pytest 121 passed、schema/lock drift passed、ruff passed、mypy 对 12 个源文件通过，安全预检与复检通过；锁文件解析 27 个包。
- 当前交付状态：`committed_locally_awaiting_remote_delivery`。无 remote，未推送、创建 PR 或运行远程 CI。

## 用户目标

作为后续开发者，我希望从一个结构明确、配置安全、契约可机器校验且有统一质量命令的本地工程开始，以便后续 Godot、FastAPI 和 Agent 功能可以在同一边界下迭代，而不需要反复猜测目录、字段和验证方式。

## 业务价值

完成后，开发者能够在干净本地环境中安装锁定的开发依赖、运行统一质量门禁、验证未来对话 API 的版本化 request/response/error schema，并确认仓库没有真实密钥或运行时数据。该切片提供后续 `R-02/R-03` 可依赖的工程合同，但不冒充玩家对话功能。

## 范围

1. 初始化本地 Git 仓库、`main` 与本任务功能分支；远程、push 和 PR 仍需单独授权。
2. 建立 Python 后端 `src`/tests 工程骨架、`pyproject.toml` 与锁文件；使用项目内 Python 3.12，不静默安装系统软件。
3. 定义版本化的 `DialogueRequest`、`DialogueResponse`、`ApiError`、标识符、trace 与 provider 状态契约，并能导出稳定 JSON Schema。
4. 建立环境配置校验：默认 local/test 可无真实 key；启用真实 provider 时空 key 必须失败；日志/错误不得包含凭证。
5. 建立 ruff、mypy、pytest、schema snapshot/契约测试和统一的本地质量入口；准备最小 CI workflow，但不推送。
6. 更新当前架构、技术、测试与开发入口文档，使事实、命令和 Git 状态一致。

## 非目标

- 不创建 FastAPI 业务路由或启动服务器；健康检查和 Godot 连通属于 `R-02`。
- 不创建 Godot 项目、场景、GDScript 或 UI。
- 不接 DeepSeek/其他真实 LLM，不发送网络请求，不评估模型质量。
- 不创建 SQLite schema、Qdrant、记忆、好感度、NPC persona 或对话编排。
- 不下载参考文章源码，不制作素材，不部署，不配置远程仓库，不 push/创建 PR。
- 不把 placeholder/mock 的通过写成真实 Agent 能力完成。

## 前置条件

- 当前项目：`E:\Agent\comprehensive-cases\15-cyber-town`；当前位于本地功能分支，无 remote。
- 当前权威文档：项目 `AGENTS.md`、`docs/README.md`、product brief、architecture、tech stack、testing strategy、decisions 与 approved roadmap。
- 依赖任务：项目启动规划已完成；无代码依赖。
- 环境边界：仅 `local/test/synthetic`；无 production-like/production，禁止真实外部系统。
- 工具边界：先只读检查 Git、Python 及候选包管理器；缺失或版本不满足时停止并报告，不未经确认安装系统级工具。

## 输入与输出

- 输入：已批准架构边界、`R-01` 范围、空凭证 `.env.example`、本机可用开发工具事实。
- 输出：可安装/可校验的后端工程基线、唯一契约源及 JSON Schema、测试和质量配置、本地 CI 配置、更新后的开发文档。
- 关键状态变化：目录从“纯文档、无 Git”变为“本地 Git 工程 + `F-001` 分支 + 可运行门禁”；仍无可运行 API、游戏或真实 Agent。

## 契约草案

### `DialogueRequestV1`

- `request_id`: UUID，客户端生成，用于幂等。
- `player_id`: 非空受限字符串；首版契约预留多玩家，不实现账户系统。
- `npc_id`: 非空受限字符串。
- `conversation_id`: UUID。
- `message`: 去除首尾空白后 1–1000 字符。

### `DialogueResponseV1`

- `request_id`、`trace_id`、`npc_id`、`conversation_id`。
- `reply`: 非空受限字符串。
- `status`: `completed | degraded`。
- `provider`: 公开、安全的 provider 标识；不得返回内部凭证或完整异常。

### `ApiErrorV1`

- `trace_id`、稳定 `code`、安全 `message`、`retryable`。
- 预留错误：`validation_error`、`npc_not_found`、`conflict`、`provider_timeout`、`provider_unavailable`、`unsafe_content`、`internal_error`。
- HTTP 映射仅形成契约文档/测试数据；路由实现留到 `R-02/R-03`。

上述字段名、枚举和上限已在 Step 0 锁定为 v1；若需改变用户可见语义，先更新本任务卡并重新批准。

## 数据影响

- 读取：仅项目文档、环境变量名和本机工具版本；不读取真实 `.env` 内容。
- 新增/修改：代码与 schema 文件、开发配置、锁文件、测试、CI YAML 和当前文档；不创建运行时数据库。
- 唯一性/事务/幂等：仅定义 `request_id` 唯一与幂等语义，不实现持久化或事务。
- 回滚/恢复：通过功能分支和提交回退；不得使用破坏性 reset/clean。若尚未提交，按文件清单人工审阅处理，不删除用户文件。

## 权限与安全边界

- 允许角色：本地开发者和 CI runner；无最终用户账户或管理后台。
- 数据范围：synthetic contract fixtures，不使用真实玩家对话或个人信息。
- 必须拒绝：真实 provider 模式缺少 key、把 `.env` 纳入 Git、schema 接受未知高风险字段、日志或异常回显密钥。
- 不得出现在日志/证据：API key、token、Cookie、连接串、真实对话、系统提示全文和未经脱敏的环境值。
- CI 只运行静态检查与测试，不访问外部服务，不使用 secrets。

## UI 与交互状态

- 本任务无玩家 UI、页面或视觉改动；loading、empty、error、permission denied、disabled、submitting、success 均不适用。
- 开发者交互只有 CLI：成功返回退出码 0；配置/schema/测试失败返回非 0 和不含敏感信息的错误摘要。
- UI 设计与视觉验收契约：不适用，不创建 Figma 设计稿或视觉证据。

## 验收标准

1. Given 一份干净 checkout 和满足版本要求的已安装 Python，when 按 README 执行锁定依赖安装与统一质量命令，then ruff、mypy、pytest 和 schema 检查全部成功，且无需真实 API key 或外部服务。
2. Given 合法的 request/response/error fixtures，when 执行 schema 验证，then v1 契约通过且导出的 schema 可重复生成、无非预期 diff。
3. Given 空消息、超长消息、非法 UUID、未知字段或非法 status，when 验证契约，then 明确失败并定位到稳定字段，不被静默修正为有效请求。
4. Given 默认 local/test 配置，when 加载配置，then 不要求真实 LLM key；Given 显式启用真实 provider 且 key 为空，then 配置在启动边界失败且错误不泄露环境值。
5. Given `.env`、SQLite、日志、Godot 缓存和测试报告候选文件，when 执行忽略/敏感信息检查，then 它们不会被 Git 跟踪；`.env.example` 保留且没有真实值。
6. Given 当前项目文档和 Git 事实，when 完成本任务文档漂移检查，then README、docs map、architecture、tech stack、testing、roadmap、current-task、progress 与 evidence 对任务状态和运行能力表述一致。
7. Given 没有用户对远程写入的授权，when 本地门禁完成，then 停止在 `ready_for_git_delivery`，不配置 remote、不 push、不创建 PR。

## 测试矩阵

| 风险/行为 | 层级 | 测试用例 | 失败证明 | 责任角色 |
| --- | --- | --- | --- | --- |
| 契约漂移 | 单元/schema snapshot | v1 schema 重复导出无 diff | 人为改变字段名时 snapshot 失败 | 实现者 + 独立审查者 |
| 输入边界 | 单元/参数化 | 空白、1000/1001 字符、非法 UUID、未知字段 | 每个非法 fixture 必须失败 | 实现者 |
| 配置泄密 | 单元/日志捕获 | real provider 无 key、异常文本扫描 | 若环境值出现在输出则失败 | 实现者 + 安全审查 |
| 本地默认可用 | 集成 | 无 key 运行全部门禁 | 若测试触网或索要 key 则失败 | 独立 QA |
| 忽略规则 | Git/脚本 | 检查 `.env`、db、logs、`.godot` | 任一候选被追踪即失败 | 实现者 |
| Python 质量 | CI/本地 | ruff、mypy、pytest | 注入 lint/type/test 错误时非 0 | CI + 独立 QA |
| 文档事实 | 文档检查 | 链接、命令、能力声明、状态一致 | 无效链接或宣称 API 可运行即失败 | 独立审查者 |

## 文件影响范围

允许创建或修改：

- 根目录：`.gitignore`、`.env.example`、`.editorconfig`、`README.md`、`pyproject.toml`、锁文件、必要的统一质量入口。
- `backend/src/cyber_town/`：仅配置、契约模型和包元数据；不得创建业务路由、LLM/存储实现。
- `backend/tests/`：契约、配置和安全基线测试及 synthetic fixtures。
- `contracts/`：由唯一代码契约导出的版本化 JSON Schema；不得手工维护冲突字段。
- `.github/workflows/`：无 secrets、无外部调用的质量 CI 配置。
- `docs/`：README、architecture、tech stack、testing strategy、decisions、当前任务/进度/证据与必要的开发说明。

明确不修改：

- `E:\Agent\comprehensive-cases\13-intelligent-travel-assistant` 及其他兄弟目录。
- Godot 场景、GDScript、正式素材、数据库/向量数据、真实 `.env`、系统配置和外部服务。
- `R-02` 之后的 API 路由、NPC、Agent、记忆、关系和多 Agent 功能。

## Step 地图

1. `F-001 / Step 0 — 工具与决策锁定`：只读核对 Git/Python/包管理器；锁定 Python、包布局、契约唯一源、质量命令和 Git 初始化方案；缺口即停止。
2. `F-001 / Step 1 — Git 与 Python 工程基线`：初始化 `main`、创建功能分支，建立包配置、锁文件与安全配置加载边界。
3. `F-001 / Step 2 — v1 契约`：先写失败测试，再实现 Pydantic 契约与可重复 schema 导出。
4. `F-001 / Step 3 — 质量与安全门禁`：配置 ruff/mypy/pytest、敏感信息与 Git ignore 检查、统一本地入口。
5. `F-001 / Step 4 — CI 与文档同步`：准备无外部依赖的 CI，校正 README/架构/测试/ADR。
6. `F-001 / Step 5 — 独立 QA 与全量门禁`：从任务卡而非实现细节设计负例，运行全量检查并审阅 diff。
7. `F-001 / Step 6 — UAT 与 Git 交付门禁`：用户验证干净安装/命令；如获远程授权则准备提交/PR/CI，否则停在 `ready_for_git_delivery`。

每一步只在上一步证据成立后进行；任务卡获批后另建/更新 `implementation-plan.md` 细化为小步，不在本草案中执行。

## 文档更新契约

- 当前任务入口：本文件。
- 必须检查/更新：根 README、`docs/README.md`、architecture、tech stack、testing strategy、decisions、roadmap、progress、evidence；只有事实变化时更新。
- 当前任务执行计划：任务卡批准并进入 Step 0 后才创建 `docs/project-management/implementation-plan.md`，同时登记到文档地图。
- 不应更新：product brief、agent/memory/evaluation 设计，除非实施发现真实冲突并先请求范围确认。
- 归档位置：`docs/archive/task-cards/F-001-engineering-contract-baseline.md`，仅在测试、UAT、Git/CI 和文档收口全部完成后迁入。
- 一致性检查：文件清单、Git branch/status/diff、README 命令、roadmap/current-task/progress/evidence 与真实测试输出逐项对照。

## 风险与回滚

- 主要风险：工程骨架空泛、契约过早僵化、字段与后续 Godot 不匹配、依赖选择不可复现、CI 与本地不一致、任务越界实现 API。
- 控制：v1 契约最小化、unknown fields 拒绝、schema snapshot、锁文件、synthetic fixtures、目录白名单和独立 QA。
- 未覆盖：真实 Godot JSON 兼容、网络错误、LLM 行为和 SQLite 事务；分别留给 R-02/R-03 及后续任务。
- 回滚：仅通过功能分支的可审查提交撤销；不使用 `git reset --hard`、clean 或批量删除。
- 人工确认：系统级依赖安装、远程仓库、push、PR、CI 外部权限以及任何删除/覆盖操作。

## 上下文与预算

- 预计读取：12–20 个规则、配置、源码和测试文件；每 Step 只读取相关子集。
- 预计执行轮次：4–7 个 Step 收口轮次，不包含用户审批与 Git 外部授权等待。
- Token 记录：在 progress 只记录 Step、证据、阻塞和下一动作，不保存完整 Prompt/日志。
- 暂停阈值：单 Step 连续 3 次同因失败、需修改任务边界、需接真实外部系统、出现未授权系统安装/删除、或契约需影响 R-02/R-03 产品语义时停止重切/请求确认。

## 完成定义

- [x] 任务卡已获用户批准，且实现未超出允许文件范围。
- [x] 契约、配置、安全和文档验收标准全部通过，负向/边界测试有红绿证据。
- [x] ruff、mypy、pytest、schema、忽略规则和敏感信息检查通过。
- [x] 独立 QA 与用户 UAT 完成；无真实外部请求或真实凭证。
- [x] CI 配置不依赖 secrets，已在本地等价环境验证；远程未授权，状态明确停在 `ready_for_git_delivery`。
- [x] Git diff 无无关文件；提交、PR、CI 证据按实际授权明确记录为未执行。
- [x] README、docs map、architecture、testing、decisions、roadmap、current-task、progress、evidence 与 Git/代码事实一致。
- [ ] 任务完成后按项目规则归档，current-task 重置为“无活动任务”；不自动开始 R-02。
- [x] 没有修改旅行助手、没有敏感信息、没有业务 API/Godot/LLM/数据库实现。

## 审批结论

Step 6 用户 UAT、本地最终门禁、P1/P2 修复、独立交付审查和本地提交已完成，当前为 `committed_locally_awaiting_remote_delivery`。F-001 尚未归档；不得自行 amend、推送、配置 remote、创建 PR 或进入 R-02。
