# F-001 Implementation Plan

状态：`Step 0 completed / blocked before Step 1`。本计划隶属于已批准任务卡 [`current-task.md`](current-task.md)，不得扩展 R-02/R-03。

## Step 0 — 工具与决策锁定

状态：`completed_with_blocker`。

- 已检查：项目/Git 事实、Git/Python/uv/pip/venv 可用性、Git 提交身份是否已配置（仅布尔值）。
- 已锁定：Python 3.12、uv、根 `pyproject.toml`/`uv.lock`、Hatchling、`backend/src/cyber_town`、Pydantic v2 strict 契约、派生 JSON Schema、`scripts/quality.py` 统一门禁、Git 初始化顺序。
- 证据：Git 2.49.0、uv 0.6.14 可用；Python 3.12 注册路径无效；唯一可启动 Python 为 3.11.0rc2。
- 阻塞：需要授权由 `uv` 下载 Python 3.12 到项目内 `.tools/python`，下载缓存放在 `.cache/uv`；不使用 RC 解释器继续。`uv 0.6.14` 已核实支持 `--install-dir` 与 `--cache-dir`。

## Step 1 — Git 与 Python 工程基线

状态：`pending_authorization`。

1. 先将 `.tools/` 与 `.cache/` 加入 `.gitignore`；经授权后执行 `uv python install 3.12 --install-dir <项目>\.tools\python --cache-dir <项目>\.cache\uv`，再以同一 install-dir 让 `uv sync` 创建项目 `.venv` 并验证稳定 Python 3.12。
2. 在项目绝对路径执行 `git init -b main`；检查忽略规则和拟暂存清单后提交规划基线。
3. 创建 `feat/f-001-engineering-contract-baseline`，确认分支与干净基线。
4. 用 `apply_patch` 创建 `.python-version`、根 `pyproject.toml`、`.editorconfig`、`backend/src/cyber_town/__init__.py`、安全配置模块与首批失败测试。
5. 生成并锁定 `uv.lock`；不接网络服务、不读取真实 `.env`。

验证：Python 必须是稳定 3.12；`uv sync --locked --all-groups` 可重复；配置负例先失败后通过；Git diff 仅限白名单。

## Step 2 — v1 契约

状态：`pending`。

1. 先写合法/非法 fixtures 与 schema drift 失败测试。
2. 实现 `backend/src/cyber_town/contracts/v1.py` strict models。
3. 实现确定性 schema 导出，并写入 `contracts/v1/`。
4. 验证重复导出无 diff、未知字段/非法边界被拒绝。

## Step 3 — 质量与安全门禁

状态：`pending`。

1. 配置 ruff、mypy、pytest。
2. 实现 `scripts/quality.py`，统一执行代码、测试、schema、ignore 和敏感信息检查。
3. 做配置泄密与无外部访问负例；记录红绿证据摘要。

## Step 4 — CI 与文档同步

状态：`pending`。

1. 创建无 secrets、无外部服务的 `.github/workflows/quality.yml`。
2. 更新 README、architecture、tech stack、testing strategy 和必要 ADR。
3. 在本地复现 CI 命令并检查文档链接。

## Step 5 — 独立 QA 与全量门禁

状态：`pending`。

独立审查者从任务卡设计契约边界、配置泄密、忽略规则和文档事实负例；运行全量门禁，审阅完整 diff 与未覆盖范围。

## Step 6 — UAT 与 Git 交付门禁

状态：`pending`。

用户按 README 验证干净安装和统一质量命令。无远程写入授权时停在 `ready_for_git_delivery`；不得配置 remote、push 或创建 PR。

## 停止条件

- 稳定 Python 无法获得或安装需扩大系统权限；
- 单 Step 连续 3 次同因失败；
- 需要真实 LLM、数据库、Godot、外部服务或修改任务边界；
- 发现敏感信息、未授权删除/覆盖或兄弟项目影响；
- 需要进入下一 Step 但未获当前阶段授权。
