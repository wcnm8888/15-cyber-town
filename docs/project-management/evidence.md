# 启动阶段证据索引

| 验证项 | 方法 | 结果 | 未覆盖范围 |
| --- | --- | --- | --- |
| 目标路径安全性 | 检查 `E:\\Agent\\comprehensive-cases`、目标目录与同级旅行助手 | 目标目录原不存在；已新建独立兄弟目录；旅行助手未修改 | 未对旅行助手内容做无关读取 |
| Git 事实 | `git -C E:\\Agent\\comprehensive-cases rev-parse --show-toplevel` | 父目录不是 Git 仓库；新项目未初始化 Git | 后续仓库初始化、远程与 CI 未授权且未执行 |
| 参考文章与源码结构 | 阅读 HelloAgents 第十五章及其 GitHub 目录 | 文章/源码采用 Godot 项目 + FastAPI backend；包含 SimpleAgent、记忆、好感度、日志 | 未下载、复制或运行文章源码 |
| 技术时效性 | 查阅 Godot、FastAPI、DeepSeek、Qdrant 官方文档 | 见 `docs/tech-stack.md` 的带链接审查结论 | 未安装依赖、未调用 API、未启动服务 |
| 文档安全 | 人工检查本次新增的 `.env.example` 与 `.gitignore` | 无真实凭证；运行期数据、日志和 `.env` 被忽略 | 后续提交前仍需敏感信息扫描 |
| roadmap 人工门禁 | 用户在 2026-08-24 明确回复“确认 roadmap，然后按照优先级起草任务卡” | roadmap 已批准；按 P0 选择 `R-01`，起草 `F-001` | 该门禁当时不包含 `F-001` 实现授权；后续审批见下一行 |
| F-001 审批门禁 | 用户在 2026-08-24 明确批准任务卡并允许进入 Step 0 | `F-001` 已批准；仅执行 Step 0 | Step 1 未获授权 |
| Step 0 工具核对 | 只读执行版本/路径检查；不输出 Git 身份值 | Git 2.49.0、uv 0.6.14 可用；稳定 Python 路径缺失；仅 3.11.0rc2 可启动 | 未下载解释器、未安装依赖、未初始化 Git |
| Step 0 技术锁定 | 对照任务卡固定可替换且可验证的工程边界 | Python 3.12 + uv + root pyproject/uv.lock + Hatchling + backend/src + Pydantic v2 + 派生 schema + Python 质量入口 | 需在 Step 1 通过真实环境和失败测试验证 |
| Step 1 Python 工具链 | 经用户授权，使用项目内 install/cache 目录执行 `uv python install`、lock 和 sync | CPython 3.12.10 安装成功；19 个锁定包可离线 audit/sync；`.tools/.cache/.venv` 被忽略 | 依赖漏洞与跨平台 CI 留待后续门禁 |
| Step 1 Git 基线 | `git init -b main`、检查 staged 范围、提交规划基线、创建功能分支 | baseline `877746d`；当前 `feat/f-001-engineering-contract-baseline`；remote 0 | 功能改动尚未提交或推送 |
| Step 1 配置红绿 | 先运行缺少 `cyber_town.config` 的测试，再添加最小实现 | 红：ModuleNotFoundError；绿：5 passed | 只覆盖配置基线，不代表 API/LLM 可用 |
| Step 1 定向门禁 | `pytest backend/tests/test_config.py`、ruff、mypy、locked offline sync | 全部通过；一次 mypy 测试签名问题已改为类型安全的 `model_validate` 后通过 | schema、统一质量入口和 CI 尚未实现 |
| Step 2 审批门禁 | 用户明确允许只实现 v1 Pydantic 对话契约、失败测试和派生 JSON Schema | Step 2 获授权并严格按范围执行 | Step 3 未获授权 |
| Step 2 契约红绿 | 先运行契约/schema 测试，再实现 contracts 包和导出器 | 红：2 个 ModuleNotFoundError；绿：Step 2 定向测试 25 passed | 不代表 API 路由或客户端兼容已完成 |
| Step 2 schema | 生成三个 v1 schema，执行导出器 `--check` 并核对关键字段 | Draft 2020-12；`additionalProperties=false`；request 必填字段完整；message max 1000；无 drift | 跨语言/Godot 消费验证留给 R-02 |
| Step 2 全量门禁 | 全量 pytest、ruff、mypy、diff check | 30 passed；ruff/mypy/diff 全通过；一次 synthetic 中文标点 lint 问题已用等价英文 fixture 修正 | 统一门禁脚本留给 Step 3 |
| Step 3 审批门禁 | 用户明确允许只实现统一质量入口、schema/ignore/敏感信息检查及其负向测试 | Step 3 获授权并严格按范围执行 | Step 4 CI 未获授权 |
| Step 3 质量红绿 | 先添加质量测试，再实现可导入质量模块和根脚本入口 | 红：`ModuleNotFoundError: No module named 'scripts'`；绿：定向测试 7 passed | 初次实现暴露 Windows stdin 回车差异，改用逐路径 Git 查询后通过 |
| Step 3 安全负例 | 临时 Git 仓库缺失 ignore 规则、动态构造 synthetic token、空/placeholder 凭证、socket monkeypatch | 缺失规则和 token 均被检出；诊断不含 token 值；placeholder 被允许；本地 helper 不触网 | socket monkeypatch 不覆盖子进程；统一入口边界在 Step 5 由命令白名单和独立 QA 补强 |
| Step 3 统一门禁 | `uv run --frozen python scripts/quality.py` | ruff passed；mypy 12 source files；schema 无 drift；pytest 37 passed；ignore 与敏感信息检查 passed | CI、跨平台 runner 与独立 QA 留给 Step 4/5 |
| Step 4 审批门禁 | 用户明确允许只创建无 secrets、无外部服务的 CI workflow，并同步 README、架构、测试和 ADR | Step 4 获授权并严格按范围执行 | Step 5 独立 QA 未获授权 |
| Step 4 CI 安全契约 | 静态断言 workflow 的权限、凭证持久化、action ref、命令及 forbidden patterns | `contents: read`；`persist-credentials: false`；两个 action 均固定 40 位 commit；无 secrets 引用、write 权限、service、`pull_request_target` 或网络客户端命令 | 未安装 actionlint；YAML 结构按官方示例人工对照，远程 runner 尚未运行 |
| Step 4 本地 CI 复现 | `uv sync --frozen --all-groups` 后运行统一质量入口 | 19 个锁定包 audit；ruff、mypy 12 source files、schema、pytest 37 passed、ignore 与敏感信息检查全部通过 | GitHub runner/Linux 差异留待取得 remote/push 授权后验证 |
| Step 4 文档链接 | 扫描 16 个 Markdown 文件中的相对链接并按源文件目录解析 | 全部存在；README、architecture、tech stack、testing strategy、ADR 和状态文档已同步 | 未对公开外链做可用性探测 |
| Step 5 首轮独立 QA | 独立审查者从任务卡设计黑盒负例，覆盖 13 个 tracked 修改和 21 个 untracked 文件 | harness 12 pass / 4 fail；全量现有门禁当时 37 passed | 发现现有绿色门禁未覆盖四个真实绕过，Step 5 未通过 |
| Step 5 首轮失败 | Draft 2020-12 空白输入、`git add -f`、小写 key、placeholder 子串及专项安全/可复现性审查 | 复现 schema/Pydantic 语义差异、tracked ignore、secret scan fail-open、安全检查顺序和 lock/build 缺口 | 全部进入本轮修复与回归测试 |
| Step 5 首轮修复门禁 | 更新唯一契约源并重导 schema；收紧 scanner/index；加入 jsonschema、lock、失败传播与环境隔离测试 | 当时 lock/ruff/mypy/schema passed；pytest 58 passed；安全预检与复检 passed；25 个锁定包 | 后续独立复验发现 Windows Git index mode `120000` symlink 绕过 |
| Step 5 独立复验与最终门禁 | 独立 QA 覆盖全部 13 个 tracked 修改与 21 个 untracked 文件，重放原始负例并追加 mode `120000` index-only/普通占位文件场景 | symlink 原复现修复后通过；统一入口 pytest 60 passed，ruff/mypy/schema/lock/ignore/sensitive 全通过；diff check 通过 | 未运行远程 CI；Step 6、提交与 push 未获授权且未执行 |
| Step 6 用户 UAT | 用户按预先提供的 README/UAT 命令在独立 E 盘环境执行并返回截图 | `UAT_RESULT=PASS`；Python 3.12.10；executable 为 `E:\Agent\.uat\15-cyber-town-f001-step6-20260824-191608\Scripts\python.exe`；当时 pytest 60 passed，统一质量入口通过；人工异常“无” | UAT 后续修复使锁文件由 25 增至 27 个包；最终状态由自动门禁和独立审查复验，未要求用户重复人工 UAT |
| Step 6 P1/P2 修复 | 按用户授权修复契约/schema 接受集、worktree/index 与 ignore 策略、配置扫描解析、失败传播和 index 扫描性能；补齐相应负例 | canonical UUID/原始长度一致；dotenv/JSON/YAML/TOML、BOM、二进制伪装、重复键/递归/过深、staged blob/ignore、全局 excludes、缺失工具均有回归；index 使用单一 batch 进程 | 轻量扫描不替代未来专用 secret scanner；不再扩展额外安全检查 |
| Step 6 最终本地门禁 | `uv run --frozen python scripts/quality.py`、Markdown 相对链接、CI 静态安全、`git diff --check`、完整 tracked/untracked diff 审查 | lock 27 packages；ruff passed；mypy 12 source files；schema 无 drift；pytest 121 passed；ignore/sensitive preflight/final passed；独立审查无剩余阻塞 | 无 remote，未运行远程 Linux runner；未 stage、提交、push、PR 或归档 |
| Step 6 Git 事实 | 只读核对 branch、HEAD、main、remote、staged/tracked/untracked 范围 | branch `feat/f-001-engineering-contract-baseline`；HEAD=main=`877746d2ec7c9a1fd08495a4a22ca206d3961439`；remote 0；staged 0；13 tracked 修改、21 untracked | 工作树有意保持未提交；Git 交付动作需另行授权 |
| F-001 本地 Git 交付 | 用户明确授权仅暂存已审阅的34个 F-001 文件并创建一个本地提交；提交前重跑既定门禁 | 提交信息 `feat: establish engineering and contract baseline`；提交后状态为 `committed_locally_awaiting_remote_delivery` | 无 remote；未 push、PR、远程 CI 或归档；提交 SHA 以本地 Git 历史为准 |
| F-001 远程 Git 交付 | 用户授权创建仓库、配置 `origin`、推送分支、创建 PR 并等待 CI；创建私有仓库 `wcnm8888/15-cyber-town`，推送 `main` 与功能分支并创建 PR #1 | 初始远程功能提交 `6c3afe7` 的 run `32728679852` 通过；状态提交 `1dce3ac` 的 run `32728961700` 通过 | 最终 PR HEAD 的 CI 与合并状态以 GitHub 为准；未进入 R-02 |
| F-001 最终归档准备 | 用户授权 PR 合并与最终归档；在同一 PR 中迁移任务卡和实现计划，重置 current-task/implementation-plan，压缩 roadmap/progress/evidence 并校正 README、architecture、testing、tech stack 与 ADR 当前事实 | 归档路径 `docs/archive/task-cards/`；当前状态为 `no_active_task`；归档提交必须触发并通过新的 PR CI 后才允许合并 | 合并结果和 merge SHA 由 GitHub 记录；不为抄写 SHA 创建递归状态提交，不进入 R-02 |
| F-002 Step 1 工具与依赖 | 从最新 main 创建功能分支；核对 Godot 官方资产 SHA-256、Windows/headless 版本；uv 锁定 FastAPI/Uvicorn/HTTPX | Godot 4.7.2 official；FastAPI 0.141.1、Uvicorn 0.52.4、HTTPX 0.28.1；lock 38 packages | 未安装系统软件、未修改 PATH；远程 CI 未运行 |
| F-002 Step 2 健康 API | 失败优先 API 测试、ASGI 集成与启动入口检查 | 9 个健康 API 定向测试通过；精确 GET-only JSON、无外部副作用；全量当时 130 passed | 不包含对话、LLM、数据库或生产服务 |
| F-002 Step 3 Godot 状态机 | 缺失资源红灯；Godot 4.7.2 headless unit、editor import/parse/scene load | 五态文案、严格 JSON、错误映射、单在途和 retry 自动测试通过 | 该 Step 未执行真实网络或窗口 UAT |
| F-002 Step 4 真实连通与恢复 | `scripts/connectivity_integration.py` 启动 owned FastAPI/loopback fixtures，真实 Godot HTTPRequest 执行 6 个场景 | 停服→timeout、503→unavailable、FastAPI→connected、503/非法 JSON/延迟→retry→connected 全通过；端口最终释放 | Windows 停服返回 timeout；真实窗口体验和跨平台远程 runner 留给 Step 6/交付 |
| F-002 Step 4 统一门禁 | `uv run --frozen python scripts/quality.py` | lock 38 packages；ruff；mypy 18 files；schema；Godot import/unit/integration；pytest 132 passed；ignore/sensitive preflight/final 全通过 | 尚未执行独立 QA、用户 UAT、远程 CI、提交或 PR |
| F-002 Step 4 CI 与文档 | 静态测试官方 Godot URL/SHA、read-only/no-secret/no-service 边界；同步权威文档并检查相对链接、YAML、diff 和完整文件范围 | CI 契约测试 2 passed；Markdown 相对链接、workflow YAML、`git diff --check`、Godot cache ignore 和范围审查通过；18 tracked 修改、18 untracked、staged 0 | workflow 尚未在 F-002 远程分支运行；独立 QA 与用户 UAT 未执行 |
| F-002 Step 5 独立全量复验 | 独立 QA 重跑统一入口、API 负例、故意失败传播、端口清理、CI 静态检查及 36 文件完整 diff | lock 38；ruff/mypy/schema/Godot 门禁通过；pytest 132 passed；API 方法/CORS/OpenAPI、ignore/sensitive、diff 与范围通过 | 远程 Linux runner和真实窗口 UAT 未执行 |
| F-002 Step 5 P2：严格 JSON | 真实 loopback 返回冲突重复 `status` key，并运行 Godot connected 场景 | Godot 4.7.2 last-wins 后退出 0，误进入 connected；可稳定复现 | 需拒绝重复 member，补 unit 与 real-loopback 负例 |
| F-002 Step 5 P2：redirect | 8000 返回 302 至 8001，目标返回合法健康响应 | Godot 跟随 redirect 并误进入 connected；两个 listener 均已释放 | 需禁用 redirect，并验证目标端口未被访问 |
| F-002 Step 5 P2：bind | clean environment 下 monkeypatch `uvicorn.run`，设置 `APP_HOST=0.0.0.0` | 启动入口原样接受 public bind，违反 loopback 边界 | 需拒绝非 loopback host并补负例 |
| F-002 Step 5 P2：验收 oracle | 对照任务卡验收 #3、Windows 真实停服结果和 integration expected sequence | 任务卡要求 unavailable；实测为 timeout；测试允许 timeout/unavailable，无法给唯一验收 PASS | 需用户批准平台细化或授权区分机制；Step 6 被阻断 |
| F-002 Step 5 P2 修复红灯 | 新增非 loopback、重复 key、redirect target 负例后先运行定向测试 | API 2 fail；GDScript duplicate 1 fail；真实 duplicate 场景进入 connected 并退出 1 | 证明负例先于修复且原问题可复现 |
| F-002 Step 5 P2 修复绿灯 | 强制 loopback bind、禁用 redirect、核对原始顶层 JSON member 数；运行 API/Godot/真实集成定向测试 | 健康 API 11 passed；GDScript unit passed；8 个 loopback 场景 passed；redirect target 零请求 | 尚待统一门禁与独立 QA 复验 |
| F-002 Step 5 停服裁决 | 用户授权明确裁决；对照冻结 result 映射与 Windows 实测 | `RESULT_TIMEOUT → timeout`，其他传输失败 → unavailable；两者均为合格失败反馈并显示 Retry | 真实窗口体验仍由 Step 6 UAT 验证 |
| F-002 Step 5 原四项独立重放 | 独立 QA 重放重复 key 变体、redirect target/external-style、IPv4/IPv6 host 与停服 oracle | 原四项均通过；8000/8001 释放；任务卡、ADR 与测试 oracle 一致 | 复验继续发现下一行的新 P2 |
| F-002 Step 5 新 P2：非字符串字段 | 真实 loopback 返回 `service` 为含字符串冒号的嵌套 object，并运行 Godot 场景 | GDScript 在 Dictionary 与 String 的 `!=` 处 runtime error，场景退出 1并达到 deadline，未进入 unavailable | 需类型检查、类型矩阵和真实 loopback 回归；Step 6 被阻断 |
| F-002 Step 5 修复后独立全量 | 独立 QA 运行统一入口、故意失败、端口、Markdown、CI、sensitive 和完整 diff | pytest 134 passed；8 integration；ruff/mypy/schema/lock/ignore/sensitive/diff 均通过；18 tracked + 18 untracked，staged 0 | 现有绿色门禁尚未覆盖非字符串字段 P2；远程 CI/UAT 未执行 |
| F-002 Step 5 非字符串类型红灯 | GDScript 以 Dictionary、Array、null、number、bool 替换固定字段；真实 loopback 返回嵌套 object | Dictionary/Array/number/bool 触发 runtime error；unit 退出 1；真实场景卡住并退出 1 | 证明测试先于追加修复 |
| F-002 Step 5 非字符串类型绿灯 | 比较前验证 `TYPE_STRING`，重跑类型矩阵、真实嵌套对象和统一入口 | 五类均进入 unavailable；9 integration；pytest 134；其余统一门禁通过 | 该时点等待独立复验；最终结果见下一行 |
| F-002 Step 5 第二次独立复验 | 真实 Godot 重放 22 个类型/嵌套/escaped/duplicate/合法变体，抽查全部历史 P2，并运行全量门禁与完整 diff | NO FINDINGS；P0/P1/P2/P3 均无；9 integration、pytest 134 和全部门禁通过；18 tracked + 18 untracked、staged 0 | 远程 Linux runner 与真实窗口 UAT 留待后续授权阶段 |
| F-002 Step 6 用户 UAT | 用户按已提供脚本完成环境/全量门禁、connected、timeout/手动 Retry、unavailable/恢复四组真实窗口检查并返回截图；结束后返回 `PORT_8000_STOPPED=YES` | `UAT_RESULT=PASS`；截图明确显示 200/connected 与 503/unavailable/Retry，其余瞬时状态由用户完成确认；8000/8001 最终无 listener | 截图未逐帧冻结每个瞬时状态；Windows 桌面 UAT 不替代后续 GitHub Linux CI |
| F-002 Step 6 最终本地交付审查 | 统一质量入口、Markdown 相对链接、workflow YAML/静态契约、`git diff --check`、端口和完整 tracked/untracked 范围复核 | lock 38；ruff；mypy 18 files；schema；Godot import/unit；9 integration；pytest 134；ignore/sensitive 全通过；18 tracked + 18 untracked、staged 0；状态为 `ready_for_git_delivery` | 未提交、push、PR、远程 CI、合并或归档；未进入 R-03 |
