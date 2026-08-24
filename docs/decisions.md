# 决策记录（ADR）

## ADR-001：项目为 L 级，采用 SDD 与唯一 docs 体系

- 状态：已锁定（用户输入，2026-08-24）。
- 决策：项目使用 `docs/` 作为唯一长期权威，不创建 `memory-bank/`；roadmap 与任务卡流程由用户审批。
- 后果：本启动轮只写规格、架构和候选路线，不写业务代码或任务卡。

## ADR-002：先单 NPC 端到端，再扩展记忆与多 NPC

- 状态：已锁定（用户输入，2026-08-24）。
- 决策：首个价值闭环仅涵盖一个 NPC 的真实对话、可审计后端轨迹与验证。
- 后果：批量生成、自治 NPC 协作、Qdrant、WebSocket 和正式美术资源不进入首切片。

## ADR-003：默认候选架构为 Godot + FastAPI + SQLite + Provider Adapter

- 状态：建议，待 roadmap/任务卡确认。
- 选择：Godot 管交互；FastAPI 管服务编排；SQLite 管结构化事实；LLM 置于可替换 provider adapter 后。
- 备选：HelloAgents 作为学习对照；向量库和 WebSocket 只按明确需求升级。
- 后果：首实现需先定义领域契约、错误语义、迁移与测试，不得从游戏端直接调用模型。

## ADR-004：LLM 不直接决定或写入持久化游戏状态

- 状态：已锁定（用户输入，2026-08-24）。
- 决策：模型仅生成文本或受 schema 约束的建议分类；好感度、权限和状态转移由确定性规则验证后事务写入。
- 后果：需要校验器、审计字段和无效输出降级；好感度不依赖纯提示词评分。

## ADR-005：roadmap 获批并按 R-01 启动任务卡流程

- 状态：已锁定（用户输入，2026-08-24）。
- 决策：用户确认现有 roadmap，并授权按推荐优先级起草任务卡；首张任务卡为 `F-001 工程与契约基线`。
- 后果：当前只评审 `F-001`，任务卡获明确批准前不进入 Step 0、不初始化 Git、不写代码；R-02 及后续任务不自动开始。

## ADR-006：F-001 工具链、布局与契约源

- 状态：已锁定（F-001 / Step 0，2026-08-24）。
- 决策：使用稳定 Python 3.12 和现有 `uv`；根 `pyproject.toml`/`uv.lock` 管理 `backend/src/cyber_town` 包，Hatchling 构建；Pydantic v2 strict models 是 v1 契约唯一源，JSON Schema 为派生产物；统一质量入口为跨平台 Python 脚本。
- 理由：避免默认 `python` 的 3.11 RC、避免手写 schema 双重权威，并让本地/CI 使用相同锁文件和质量命令。
- 后果：用户已授权并完成项目内 CPython 3.12.10 安装；`.tools/python`、`.cache/uv` 和 `.venv` 均受忽略规则保护。Step 1 当时已初始化 Git/main、提交规划基线并创建功能分支；后续远程交付通过私有仓库和 PR #1 完成。

## ADR-007：v1 对话契约严格性与长度边界

- 状态：已锁定（F-001 / Step 2，2026-08-24）。
- 决策：所有外部契约使用 Pydantic strict mode 和 `extra=forbid`；ID 长度 1–64，玩家消息 1–1000，NPC 回复 1–4000，provider ID 1–64，公开错误消息 1–500；UUID、状态和错误码均使用强类型。
- Schema：Pydantic models 是唯一权威；`contracts/v1` 中三个 Draft 2020-12 JSON Schema 由排序、UTF-8、LF 导出器生成，禁止手工维护冲突字段。
- 后果：客户端传入未知字段、非法枚举、无效 UUID、类型强制转换或越界字符串会被拒绝；Godot 兼容性与 HTTP 映射在后续任务验证。

## ADR-008：本地质量入口与安全扫描边界

- 状态：已锁定（F-001 / Step 3，2026-08-24）。
- 决策：`uv run --frozen python scripts/quality.py` 是统一离线入口；它先执行 ignore/敏感信息预检，再以参数数组启动 lock freshness、ruff、mypy、schema drift 和 pytest，最后复查仓库策略，不经过 shell。
- 安全边界：敏感信息发现只保存路径、行号和规则名，不保存或回显匹配值；空值和完整匹配的明确 placeholder 可用于 `.env.example`。已被强制跟踪的 ignore 文件、无法按 UTF-8 读取或超过扫描上限的未知文本均 fail-closed；已知二进制按魔数识别，并继续扫描其中可解码的文本片段。
- 后果：本地与后续 CI 可复用同一命令且无需 API key、网络或外部服务；该轻量检查不替代 Step 5 的独立 QA 或未来专用 secret scanner。

## ADR-009：最小 CI 的权限与供应链边界

- 状态：已锁定（F-001 / Step 4，2026-08-24）。
- 决策：GitHub Actions 仅在 `main` push、pull request 或人工触发时执行锁定环境同步和统一质量入口；顶层权限固定为 `contents: read`，checkout 设置 `persist-credentials: false`，不引用 secrets、不启动服务容器、不发布产物。
- 供应链：`actions/checkout` 与 `astral-sh/setup-uv` 固定到官方文档所列完整 commit；uv 固定为本地已验证的 `0.6.14`，Python 固定为 `.python-version` 中的 `3.12.10`，运行/开发依赖由 `uv.lock` 固定，Hatchling 构建后端在 `pyproject.toml` 精确固定。CI 使用 `uv sync --locked` 拒绝陈旧锁文件。runner bootstrap 仍需访问公开 action/Python/包发行源，这不被描述为“完全离线”。
- 后果：CI 没有仓库写入、部署或业务系统访问能力，本地与 CI 命令保持一致；Step 4 当时只记录本地等价复现结果，后续已由 PR #1 的 GitHub-hosted Linux runner 验证通过。

## ADR-010：独立 QA 后的契约与安全门禁收紧

- 状态：已锁定（F-001 / Step 5，2026-08-24）。
- 契约：所有经过 trim 的非空字符串同时导出 `pattern: \S`，使 Draft 2020-12 schema 与 Pydantic 对纯空白输入的判断一致；派生 schema 由 `jsonschema` 直接验证，且 drift 检查拒绝多余文件。
- 安全：凭证键匹配大小写不敏感；placeholder 只允许空值或精确值；Git index 中已跟踪的 ignore 文件、mode `120000` symlink、非 UTF-8/超大未知文本和工作树 symlink 均使门禁失败。敏感扫描前置并在工具执行后复查。
- 后果：首轮独立 QA、专项安全审查及独立复验发现均有自动回归用例；Step 5 已通过独立复验。

## ADR-011：Step 6 契约一致性与交付扫描收口

- 状态：已锁定（F-001 / Step 6，2026-08-24）。
- 契约：外部 UUID 采用 canonical 36 字符形状，schema 同时导出 `pattern` 与固定长度，使默认 Draft 2020-12 validator 和 Pydantic 接受集一致；所有 trim 字段在 trim 前执行与 schema 相同的原始长度预算。
- 交付扫描：worktree 与 stage-0 index 分别扫描；index blobs 使用单一 `git cat-file --batch` 进程；仓库与 staged `.gitignore` 分别按仓库受控规则验证，不受全局 excludes 或 `.git/info/exclude` 污染。dotenv、JSON、YAML、TOML 使用语义解析器，重复键、递归/过深结构和解析失败均 fail-closed。
- 后果：用户 UAT 与最终本地门禁通过后，任务曾停在 `ready_for_git_delivery`；后续用户另行授权本地提交、远程仓库、push、PR、CI、合并与归档。F-001 通过 PR #1 收口，且不自动进入 R-02。
