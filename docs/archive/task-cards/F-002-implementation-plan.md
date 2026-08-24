# 已归档实现计划：F-002 Godot—FastAPI 最小连通

状态：`completed / archive_prepared_in_PR_2`。

本计划服务于已归档的 [`F-002` 任务卡](F-002-godot-fastapi-connectivity.md)。各 Step 均按前一 Step 证据和用户明确授权执行；未复用 F-001 授权，也未进入 R-03。

## Step 地图

| Step | 状态 | 范围 | 验证与停止条件 |
| --- | --- | --- | --- |
| Step 0 | `completed` | 落盘批准任务卡；只读复核 Git、Python、uv、Godot、现有依赖与文件；锁定工具获取方案 | 不安装、不建分支、不写业务代码；Godot 缺失记录为 Step 1 前置条件 |
| Step 1 | `completed` | 从最新 `main` 创建 F-002 分支；准备 Godot 4.7.2 便携工具；加入并锁定 FastAPI/Uvicorn/API 测试依赖 | 官方 SHA-256、版本、headless、lock、ignore 和既定质量入口通过 |
| Step 2 | `completed` | 实现最小 FastAPI 应用、健康响应模型和 `GET /api/v1/health` | 红灯、定向 9 passed、全量 130 passed；ruff、mypy、lock、schema/ignore/sensitive 通过 |
| Step 3 | `completed` | 创建最小 Godot 项目、单场景、`HTTPRequest` 客户端和五态 UI | 缺失资源红灯；headless 测试、editor 导入、脚本解析和场景加载通过 |
| Step 4 | `completed` | 完成本地 FastAPI—Godot 连通、timeout fixture、失败恢复、README/架构/测试/ADR 与必要 CI 同步 | 6 个真实 loopback 场景、132 pytest、完整统一门禁通过 |
| Step 5 | `completed` | 独立 QA、P2 修复、两轮独立复验、全量门禁和完整 diff 审查 | 第二次复验 NO FINDINGS；等待 Step 6 授权 |
| Step 6 | `completed` | 提供用户 UAT 脚本；用户完成真实 Godot UAT；执行最终本地交付审查 | UAT PASS、全量门禁、Git/diff/文档一致性均通过，已标记 `ready_for_git_delivery` |
| Git 交付 | `not_authorized` | 经另行授权后精确提交、push、PR、CI、合并和归档 | 服从 Git 唯一交付规范；不删除远程分支、不发布、不进入 R-03 |

## Step 0 证据

- 当前检出：`feat/f-001-engineering-contract-baseline`，HEAD `29153f632bee2e6966b2484e52ded33e7ad8224e`。
- `main` 与本地 `origin/main`：`de6d66e376d9610f660de0b48f4983e653460cc8`。
- Step 0 开始前工作树干净，remote 为现有私有 `origin`。
- Python：项目 `.venv` 3.12.10；uv：0.6.14。
- Godot：PATH 中无 `godot`/`godot4`/console 命令；约定便携路径不存在。
- FastAPI、Uvicorn、HTTPX 尚未进入 `pyproject.toml`/`uv.lock`；FastAPI 和 Godot 实现文件不存在。
- 官方归档确认 Godot 4.7.2-stable 提供 Windows x86_64 Standard 构建；本 Step 未下载或安装。

## Step 1 证据

- 新分支 `feat/f-002-godot-fastapi-connectivity` 从 `main` 的 `de6d66e376d9610f660de0b48f4983e653460cc8` 创建，Step 0 文档修改完整保留。
- Godot 官方资产：`Godot_v4.7.2-stable_win64.exe.zip`，发布不是 draft 或 prerelease；官方和本地 SHA-256 一致，为 `731980f9608d61333e5baf54a2ef17210acc7a538446c0cb9969f002aca1e953`。
- 工具路径：`E:\Agent.tools\godot\4.7.2\`；普通和 headless 版本均为 `4.7.2.stable.official.ed1daf0bf`。系统 PATH 未修改，未安装 .NET 版或 export templates。
- Python 运行依赖：FastAPI 0.141.1、Uvicorn 0.52.4；开发依赖：HTTPX 0.28.1；uv lock 共解析 38 个包。
- `uv sync --locked --all-groups` 完成 38 包审计；统一质量入口的 lock、ruff、mypy、schema、pytest 121 passed、ignore 和 sensitive preflight/final 全部通过。
- 未创建 FastAPI 应用、健康路由、Godot 项目、场景或 GDScript。

## Step 2 证据

- 红灯：新增健康 API 测试后，pytest 收集因 `ModuleNotFoundError: No module named 'cyber_town.api'` 失败，证明测试先于实现。
- 兼容性：未采用已显示弃用警告的 `fastapi.testclient`，改用已锁定 HTTPX 的 `ASGITransport`，没有新增或扩大依赖。
- 实现：新增 `cyber_town.api` application factory、严格固定的 `HealthResponseV1`、`GET /api/v1/health` 和读取现有 `Settings` 的 `python -m cyber_town.api` 启动入口。
- 契约：HTTP 200、JSON Content-Type、精确三个字段、GET-only、无 body/query/dependency；socket/database smoke 负例和启动参数测试均通过。
- 绿灯：定向 pytest 9 passed，定向 ruff 和严格 mypy 通过。
- 全量：统一质量入口解析 38 包；ruff、mypy 16 source files、schema、pytest 130 passed、ignore 和 sensitive preflight/final 全部通过；`git diff --check` 通过。
- 范围：未修改 `config.py`，未创建 Godot 项目、场景或 GDScript，未实现 Dialogue、LLM、数据库、NPC 或 R-03。

## Step 3 证据

- 红灯：仅创建 `game/project.godot` 和完整测试入口后，headless 测试退出码 1，逐项报告状态脚本、客户端脚本、UI 脚本和主场景缺失。
- 实现：新增纯状态映射、单在途 `HTTPRequest` 客户端、低保真 `Control` 场景、五态文案与 Retry 行为；URL、3 秒 timeout 和严格响应字段保持任务卡锁定值。
- 自动测试：合成回调覆盖五态文案/按钮策略、成功、timeout、传输失败、非 2xx、空/非法 JSON、缺失/额外/错误字段、重复请求和 retry 恢复；未启动真实网络请求。
- Godot 门禁：4.7.2 headless 定向测试输出 `Godot connectivity tests passed`；editor headless 导入、GDScript 解析、项目初始化和场景加载退出码 0。
- 产物：`game/.godot/` 被现有 ignore 规则排除；Godot 生成的 `.gd.uid` 是脚本资源身份文件，随对应脚本保留，不属于导入缓存或正式素材。
- Python 门禁：lock 38 包、ruff、mypy 16 source files、schema、pytest 130 passed、ignore 和 sensitive preflight/final 全部通过；`git diff --check` 通过。
- 范围：后端健康实现、`pyproject.toml`、`uv.lock`、README、architecture、tech stack、testing strategy、ADR 和 CI workflow 在本 Step 均未修改。

## Step 4 证据

- 新增无第三方依赖的 Godot integration runner 和 Python loopback harness；只启动 owned FastAPI/fixture 进程，不杀未知 listener，不落运行日志或测试数据。
- 真实场景通过：停服→timeout、503→unavailable、FastAPI→connected、503/非法 JSON/延迟→手动 retry→connected；所有场景后端口均释放。
- 统一入口接入 Godot import、unit 和 integration；本地全量为 pytest 132 passed，ruff、mypy 18 files、schema、lock 38 packages、ignore 和 sensitive 全通过。
- CI 使用官方 Godot 4.7.2 Linux Standard 资产和发布 SHA-256，保持 `contents: read`、无 secrets、无 services、无发布。
- 完整文档按已验证事实同步；Windows 无监听端口实测映射为 timeout，留给 Step 5/6 复核，不修改锁定状态规则。
- Step 4 未执行用户 UAT、提交、推送、PR、远程 CI 或归档，未进入 R-03。

## Step 5 独立 QA 证据

- P2：冲突重复 JSON key 被 Godot last-wins 解析后误判为 connected。
- P2：HTTP 302 可跟随至另一端口并以最终合法响应误判为 connected。
- P2：启动入口接受 `APP_HOST=0.0.0.0`，未强制 loopback。
- P2：停服验收要求 unavailable，但 Windows 实测与冻结映射为 timeout，当前测试 oracle 放宽为二选一。
- 全量既定门禁仍为绿色，故意失败传播、listener 清理、API 方法/CORS/OpenAPI、CI 静态边界和 36 文件完整 diff 审查均通过。
- Step 5 未修改实现、未提交、未推送、未进入 Step 6 或 R-03；等待用户授权前三项修复并裁决第四项。

## Step 5 修复证据

- 负向测试先行红灯：2 个非 loopback 启动测试失败，重复 key GDScript 单测失败，真实 duplicate 场景误进入 connected。
- 修复：启动入口只接受 loopback IP；`HTTPRequest.max_redirects=0`；严格响应在解析后同时核对原始顶层 member 数，拒绝重复 key。
- 新增真实场景：duplicate response 必须 unavailable；302 必须 unavailable 且 redirect target 请求数为 0。集成矩阵现为 8 个场景。
- 定向绿灯：健康 API 11 passed、GDScript unit passed、8 个真实 loopback 场景 passed；等待统一门禁和独立 QA 复验。
- 停服验收已获用户裁决：按引擎实际 result 映射，`RESULT_TIMEOUT → timeout`，其他传输失败 → unavailable；两者均显示 Retry。

## Step 5 独立复验结论

- 原重复 member、redirect、非 loopback bind 与停服 oracle 四项均通过重放。
- 新 P2：健康字段实际值为 Dictionary/Array 等非字符串时，`payload[key] != EXPECTED_HEALTH[key]` 触发 GDScript runtime error，未映射为 unavailable。
- 其余重复 key、escaped key、空白/顺序、字符串冒号、redirect external-style、IPv4/IPv6 loopback 边界均通过。
- 独立全量门禁仍通过：pytest 134 passed、8 integration、ruff/mypy/schema/lock/ignore/sensitive 均为绿色；该绿色门禁尚未覆盖新类型矩阵。
- 等待用户追加授权修复新 P2、补类型矩阵与真实 loopback 负例，再执行一次独立复验。

## Step 5 追加修复证据

- 红灯：Dictionary、Array、number、bool 均触发 GDScript 运算符 runtime error；真实嵌套对象场景卡在 connecting 并退出 1。null 同时纳入 fail-closed 矩阵。
- 修复：固定值比较前强制实际字段 `TYPE_STRING`，然后再执行字符串比较。
- 绿灯：Dictionary、Array、null、number、bool 全部进入 unavailable；真实嵌套对象进入 unavailable；GDScript unit 与 9 个真实 loopback 场景通过。
- 全量本地门禁：pytest 134 passed，ruff、mypy 18 files、schema、lock 38、Godot import/unit/integration、ignore/sensitive 全部通过。
- 追加修复完成时先停留在 Step 5，随后已完成下节所述独立复验。

## Step 5 最终独立复验

- 结论：NO FINDINGS；P0/P1/P2/P3 均无。
- 22 个真实 HTTPRequest 响应变体通过；非字符串、嵌套、escaped、重复 member 均 fail-closed，合法重排/转义保持 connected。
- 历史 duplicate、redirect、non-loopback bind 与停服 oracle 全部通过重放。
- 全量：lock 38、ruff、mypy 18 files、schema、Godot import/unit、9 integration、pytest 134、ignore/sensitive 全通过。
- 18 tracked 修改 + 18 untracked、staged 0；diff、Markdown、CI 静态、缓存 ignore、敏感信息和范围审查通过。
- Step 5 完成；下一动作只能是经用户授权进入 Step 6 用户 UAT，不自动执行。

## Step 6 最终交付审查

- 用户确认四组真实窗口 UAT 均通过：环境与全量门禁、connected、timeout 与手动 Retry、unavailable 与恢复；截图明确记录了连接成功、503 unavailable 与 Retry，用户对未逐帧冻结的瞬时状态给出完成确认。
- UAT 监听结束后用户返回 `PORT_8000_STOPPED=YES`；最终检查确认 8000/8001 均无 listener。
- 最终统一入口通过：lock 38、ruff、mypy 18 files、schema、Godot import/unit、9 integration、pytest 134、ignore/sensitive 全部通过。
- Markdown 相对链接、workflow YAML/静态契约、`git diff --check` 与完整 tracked/untracked 范围审查通过；无凭证、运行时数据、Godot cache、兄弟项目或 R-03 实现。
- Git 事实：分支 `feat/f-002-godot-fastapi-connectivity`，HEAD/main/origin-main 均为 `de6d66e376d9610f660de0b48f4983e653460cc8`；staged 0，18 tracked 修改、18 untracked。
- Step 6 完成并标记 `ready_for_git_delivery`；其后用户授权端到端 Git 交付，功能提交和 PR #2 已创建，本计划随同一 PR 归档，最终 CI 与合并事实以 GitHub 为准。

## 全局停止条件

- Godot 获取来源、版本、校验或路径无法确认；
- 需要系统级安装、管理员权限、修改 PATH 或删除现有工具；
- Git、锁文件或文件范围出现未解释漂移；
- 需要改变已批准的 API/UI/timeout/retry/CORS 决策；
- 需要实现 Dialogue、LLM、数据库、NPC 或 R-03；
- 任一当前 Step 必需门禁失败且原因未解决。
