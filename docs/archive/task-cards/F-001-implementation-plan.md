# F-001 Implementation Plan

状态：`completed / archived with F-001`。对应归档任务卡为 [`F-001-engineering-contract-baseline.md`](F-001-engineering-contract-baseline.md)；本计划随 PR #1 合并进入 `main`。

## Step 0 — 工具与决策锁定

状态：`completed`。

- 已检查：项目/Git 事实、Git/Python/uv/pip/venv 可用性、Git 提交身份是否已配置（仅布尔值）。
- 已锁定：Python 3.12、uv、根 `pyproject.toml`/`uv.lock`、Hatchling、`backend/src/cyber_town`、Pydantic v2 strict 契约、派生 JSON Schema、`scripts/quality.py` 统一门禁、Git 初始化顺序。
- 证据：Git 2.49.0、uv 0.6.14 可用；Python 3.12 注册路径无效；唯一可启动 Python 为 3.11.0rc2。
- 原阻塞已解除：用户已授权，`uv` 已将 CPython 3.12.10 下载到项目内 `.tools/python`，缓存位于 `.cache/uv`。

## Step 1 — Git 与 Python 工程基线

状态：`completed`。

1. 先将 `.tools/` 与 `.cache/` 加入 `.gitignore`；经授权后执行 `uv python install 3.12 --install-dir <项目>\.tools\python --cache-dir <项目>\.cache\uv`，再以同一 install-dir 让 `uv sync` 创建项目 `.venv` 并验证稳定 Python 3.12。
2. 在项目绝对路径执行 `git init -b main`；检查忽略规则和拟暂存清单后提交规划基线。
3. 创建 `feat/f-001-engineering-contract-baseline`，确认分支与干净基线。
4. 用 `apply_patch` 创建 `.python-version`、根 `pyproject.toml`、`.editorconfig`、`backend/src/cyber_town/__init__.py`、安全配置模块与首批失败测试。
5. 生成并锁定 `uv.lock`；不接网络服务、不读取真实 `.env`。

验证：Python 必须是稳定 3.12；`uv sync --locked --all-groups` 可重复；配置负例先失败后通过；Git diff 仅限白名单。

完成证据：Python 3.12.10；baseline commit `877746d`；当前功能分支正确且无 remote；配置测试先因缺少模块失败，最小实现后 5 passed；ruff/mypy/离线 locked sync 通过。

## Step 2 — v1 契约

状态：`completed`。

1. 先写合法/非法 fixtures 与 schema drift 失败测试。
2. 实现 `backend/src/cyber_town/contracts/v1.py` strict models。
3. 实现确定性 schema 导出，并写入 `contracts/v1/`。
4. 验证重复导出无 diff、未知字段/非法边界被拒绝。

完成证据：测试先因 `cyber_town.contracts` 不存在而失败；实现后 Step 2 定向测试 25 passed，全量 30 passed；三个 schema 与唯一代码源一致，`--check` 无 drift；ruff/mypy 通过。

## Step 3 — 质量与安全门禁

状态：`completed`。

1. 配置 ruff、mypy、pytest。
2. 实现 `scripts/quality.py`，统一执行代码、测试、schema、ignore 和敏感信息检查。
3. 做配置泄密与无外部访问负例；记录红绿证据摘要。

完成证据：测试先因质量模块不存在而失败；实现后 Step 3 定向测试 7 passed。统一入口使用当前锁定解释器且不经过 shell，依次完成 ruff、mypy、schema drift、pytest、Git ignore 策略和敏感信息检查；全量 37 passed，12 个源文件类型检查通过。敏感信息结果只包含路径、行号和规则，不保存或回显匹配值。

## Step 4 — CI 与文档同步

状态：`completed`。

1. 创建无 secrets、无外部服务的 `.github/workflows/quality.yml`。
2. 更新 README、architecture、tech stack、testing strategy 和必要 ADR。
3. 在本地复现 CI 命令并检查文档链接。

完成证据：创建 `.github/workflows/quality.yml`，仅授予 `contents: read`，关闭 checkout 凭证持久化，不引用 secrets、服务容器或发布步骤；action 固定完整 commit，uv/Python/依赖分别由 workflow、`.python-version` 和 `uv.lock` 固定。本地复现 sync 与统一质量入口通过，Markdown 相对链接检查通过。当前无 remote，未产生远程 runner 证据。

## Step 5 — 独立 QA 与全量门禁

状态：`completed`。

独立审查者从任务卡设计契约边界、配置泄密、忽略规则和文档事实负例；运行全量门禁，审阅完整 diff 与未覆盖范围。

首轮证据：独立 harness 12 pass / 4 fail；发现 schema 空白语义不一致、tracked ignore 绕过、大小写凭证绕过和 placeholder 子串绕过。专项审查另发现非 UTF-8 fail-open、安全检查顺序、lock/build 可复现性、schema extra drift、环境隔离与失败传播证据缺口。

修复与复验证据：所有发现已加入自动回归；Hatchling 精确固定，CI 改为 `uv sync --locked`，统一入口加入 lock check 和双重安全策略检查。全新独立 QA 复验发现 Windows Git index mode `120000` 绕过后，已补充 index-only 与普通占位文件回归测试并按原复现确认修复；Step 5 当时全量 pytest 60 passed，ruff/mypy/schema/lock/ignore/sensitive 全通过。

## Step 6 — UAT 与 Git 交付门禁

状态：`completed / archive prepared in PR #1`。

用户按 README 在 `E:\Agent\.uat\15-cyber-town-f001-step6-20260824-191608` 验证 Python 3.12.10、独立环境路径、pytest 与统一质量命令，结果 PASS。随后在授权范围内修复最终审查发现的 P1/P2，并将契约一致性、worktree/index、ignore、结构化配置、失败传播与性能负例纳入回归。最终统一入口 pytest 121 passed，ruff/mypy/schema/lock/ignore/sensitive 全通过，独立测试/可维护性/性能审查无剩余阻塞。

本地交付提交、私有远程仓库、`origin`、远程 `main`/功能分支、PR #1 和 GitHub Actions `Quality` 已完成。任务卡与本计划已准备归档并随 PR #1 合并进入 `main`；合并事实以 GitHub 为准。未进入 R-02。

## 停止条件

- 稳定 Python 无法获得或安装需扩大系统权限；
- 单 Step 连续 3 次同因失败；
- 需要真实 LLM、数据库、Godot、外部服务或修改任务边界；
- 发现敏感信息、未授权删除/覆盖或兄弟项目影响；
- 需要进入下一 Step 但未获当前阶段授权。
