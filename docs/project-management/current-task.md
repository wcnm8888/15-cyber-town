# 当前任务：F-002 Godot—FastAPI 最小连通

状态：`approved / step_6_complete / ready_for_git_delivery`。

来源：[`roadmap.md`](roadmap.md) 的 `R-02`。用户已于 2026-08-24 批准本任务卡及默认决策；Step 5 的全部修复与独立 QA、Step 6 用户 UAT 和最终本地交付审查均已完成。尚未授权提交、推送、PR、远程 CI、合并或归档。

## 用户目标与价值

作为 Cyber Town 开发者，启动本地 FastAPI 服务和最小 Godot 场景后，可以直接从游戏窗口判断后端连接状态；连接成功、超时、服务不可用和手动重试都有明确、可恢复的反馈。

本任务只验证 Godot 与 FastAPI 的本地通信边界，为 R-03 提供基础，不实现 NPC 智能或真实对话。

## 已批准默认决策

- Godot：`4.7.2-stable` Standard，Windows x86_64，仅本地桌面目标。
- 健康检查：`GET /api/v1/health`。
- 本地地址：`127.0.0.1:8000`。
- Godot 请求 timeout：3 秒。
- 场景加载时自动检查一次；失败后只允许手动 retry，不做自动重试或退避。
- 原生 Godot 客户端不启用 CORS。
- 自动测试验证 API 契约、错误映射、场景加载和回归；人工 Godot UAT 验证真实窗口、文案和恢复体验。
- 本任务是低保真工程诊断场景，以本任务卡的单屏布局和状态文案作为视觉契约，不要求正式 Figma 设计稿。
- Godot 不可用且未获安装授权时必须停止，不得只完成 FastAPI 并宣称任务完成。

## 范围

1. 最小 FastAPI 应用和只读健康检查端点。
2. 最小 Godot 项目和单场景。
3. Godot 使用 `HTTPRequest` 调用本地健康检查。
4. 显示 `connecting`、`connected`、`timeout`、`unavailable` 和 `retry` 状态。
5. 固定开发端口、timeout、错误映射和本地启动顺序。
6. 后端测试、必要的 Godot/本地集成测试和人工 Godot UAT。
7. 按事实同步 README、架构、技术栈、测试策略、ADR 和项目管理文档。

## 非目标

- 不实现对话 API，不用 `DialogueRequestV1` 或 `DialogueResponseV1` 发起真实 NPC 对话。
- 不接入 DeepSeek 或其他 LLM。
- 不创建 SQLite、Qdrant、记忆、好感度或 NPC 状态。
- 不实现 persona、Agent 编排、流式输出、多 NPC、WebSocket 或 SSE。
- 不制作正式像素素材、完整 HUD 或完整游戏 UI。
- 不部署公网服务，不绑定 `0.0.0.0`，不访问生产环境。
- 不开始 R-03。

## 前置条件与 Step 0 工具事实

- 工作树在 Step 0 开始前干净。
- 当前检出分支仍为已归档的 `feat/f-001-engineering-contract-baseline`，HEAD 为 `29153f632bee2e6966b2484e52ded33e7ad8224e`；不得在该分支实现 F-002。
- `main` 与本地 `origin/main` 均为 `de6d66e376d9610f660de0b48f4983e653460cc8`。
- `origin` 指向私有仓库 `wcnm8888/15-cyber-town`。
- 项目 `.venv` 为 Python 3.12.10，uv 为 0.6.14。
- Step 1 已从 Godot 官方 `godotengine/godot-builds` 的 `4.7.2-stable` 非预发布资产取得 Windows x86_64 Standard 压缩包，官方与本地 SHA-256 均为 `731980f9608d61333e5baf54a2ef17210acc7a538446c0cb9969f002aca1e953`。
- Godot 保留在 `E:\Agent.tools\godot\4.7.2\`，console executable 为 `Godot_v4.7.2-stable_win64_console.exe`；普通和 `--headless` 版本检查均为 `4.7.2.stable.official.ed1daf0bf`。未修改系统 PATH，压缩包按授权保留。
- Step 1 已从最新 `main` 创建并检出 `feat/f-002-godot-fastapi-connectivity`，起点为 `de6d66e376d9610f660de0b48f4983e653460cc8`；Step 0 文档修改完整保留。
- `pyproject.toml`/`uv.lock` 已锁定 FastAPI 0.141.1、Uvicorn 0.52.4 和开发依赖 HTTPX 0.28.1；锁文件共解析 38 个包。
- Step 2 已创建最小 FastAPI 健康路由；Step 3 已创建最小 Godot 项目、诊断场景、`HTTPRequest` 客户端、五态 UI 和无第三方依赖的 headless 测试；Step 4 已完成真实连通、失败恢复和统一门禁接入。

## FastAPI 与 Godot 职责边界

| FastAPI | Godot |
| --- | --- |
| 暴露固定健康检查契约 | 发起单次 HTTP 请求并显示状态 |
| 只监听本地 loopback | 不直连 LLM、数据库或外部服务 |
| 不维护客户端 retry 状态 | 管理手动 retry 和单请求并发 |
| 不调用数据库、LLM 或其他网络 | 将传输、HTTP 和 JSON 结果映射为有限状态 |

## 健康检查契约

请求：

```http
GET /api/v1/health
Accept: application/json
```

- 无 request body、query、鉴权或持久化副作用。
- 不调用 LLM、数据库或外部网络。

成功响应：

```json
{
  "status": "ok",
  "service": "cyber-town-backend",
  "api_version": "v1"
}
```

- HTTP 200，`Content-Type: application/json`。
- 三个字段均为必填固定字符串。
- 不返回时间戳、主机路径、环境变量、Git 信息或敏感配置。

Godot 错误映射：

| 条件 | UI 状态 |
| --- | --- |
| 初始请求在途 | `connecting` |
| 用户触发的重试在途 | `retry` |
| `HTTPRequest` timeout | `timeout` |
| 连接错误或其他非成功传输结果 | `unavailable` |
| HTTP 非 2xx | `unavailable` |
| 空 body、非法 JSON、字段缺失或固定值不匹配 | `unavailable` |
| HTTP 200 且响应严格匹配 | `connected` |

原始响应正文、异常堆栈和内部错误不得直接显示到 Godot UI。

## 端口、timeout 与 retry

- 服务默认读取现有 `APP_HOST=127.0.0.1` 与 `APP_PORT=8000`。
- Godot 默认 URL：`http://127.0.0.1:8000/api/v1/health`。
- timeout：3 秒。
- 同一时刻只允许一个请求；请求在途时 Retry 禁用。
- `timeout`/`unavailable` 显示 Retry；点击后进入 `retry`，完成后进入新的最终状态。
- 不做自动重试、指数退避、无限循环或后台轮询。

## UI 与交互状态

单个低保真 `Control` 场景，仅含标题、状态文本和 Retry 按钮，不使用正式素材。

| 状态 | 冻结文案 | Retry |
| --- | --- | --- |
| `connecting` | `Connecting to backend…` | 禁用 |
| `connected` | `Backend connected` | 隐藏或显示 `Check again` |
| `timeout` | `Connection timed out` | 启用 |
| `unavailable` | `Backend unavailable` | 启用 |
| `retry` | `Retrying connection…` | 禁用 |

窗口缩放时状态文本和按钮不得被裁切。empty、权限拒绝和表单提交状态不适用于本诊断场景。

## 验收标准

1. 按 README 启动后端后，`GET /api/v1/health` 返回 HTTP 200 和精确响应契约。
2. 后端运行时打开 Godot 场景，UI 从 `connecting` 进入 `connected`。
3. 后端未运行时打开场景，UI 按 Godot 实际传输结果进入明确失败状态：`RESULT_TIMEOUT` 显示 `timeout`，其他传输失败显示 `unavailable`；两者都不得崩溃且必须显示 Retry。Windows Godot 4.7.2 的锁定预期为 `timeout`。
4. 测试专用 loopback fixture 延迟超过 3 秒时，UI 进入 `timeout`。
5. 从 `timeout`/`unavailable` 恢复服务并点击 Retry 后，UI 显示 `retry`，最终进入 `connected`。
6. 非 2xx、非法 JSON 或不匹配响应映射为 `unavailable`，不显示原始正文。
7. 请求在途时不能产生第二个并发请求。
8. Python 统一质量门禁和获批准的 Godot 门禁全部通过。
9. 用户按 UAT 脚本在真实 Godot 窗口观察成功、失败和恢复。
10. 完整 diff 不包含对话、LLM、数据库、NPC 或 R-03 实现。

## 测试矩阵

| 风险/行为 | 层级 | 最低用例 | 失败证明 | 责任 |
| --- | --- | --- | --- | --- |
| 健康契约漂移 | API | 状态码、Content-Type、精确 JSON | 修改字段时失败 | 实现者 |
| 健康端点产生副作用 | API/审查 | 无持久化、LLM、外部请求 | 加入副作用时失败 | 独立 QA |
| 错误 HTTP 方法 | API | 非 GET 不成功 | 错误开放方法时失败 | 实现者 |
| Godot 状态映射 | GDScript | 成功、timeout、连接失败、非 2xx、非法 JSON | 调换映射时失败 | 实现者 |
| 重复请求 | GDScript | 在途时 Retry 禁用 | 允许第二请求时失败 | 独立 QA |
| 场景可加载 | Godot headless | 导入、脚本解析、主场景加载 | 资源或脚本错误时失败 | CI/实现者 |
| 真实本地连通 | 集成 | FastAPI 与 Godot 本地请求 | host/port/path 错误时失败 | 独立 QA |
| timeout 恢复 | 集成/UAT | 延迟 fixture → timeout → retry → connected | 未超时或无法恢复时失败 | 独立 QA/用户 |
| 真实窗口反馈 | 人工 UAT | 五种状态文案和按钮行为 | 文案不可见、卡死或错态 | 用户 |

## 文件影响范围

允许按 Step 修改或新增：

- `pyproject.toml`、`uv.lock`；
- `.gitignore`，以及仅在本地配置说明确需校正时修改 `.env.example`；
- `backend/src/cyber_town/api/**`；
- `backend/tests/**` 中的 F-002 定向测试；
- `game/project.godot`、`game/scenes/**`、`game/scripts/**`、`game/tests/**`；
- 仅为接入已批准 Godot 门禁而修改 `scripts/quality.py`、`backend/src/cyber_town/quality.py` 和 `.github/workflows/quality.yml`；
- 根 `README.md` 与受事实变化触发的当前权威文档。

明确不修改：

- Dialogue v1 字段和语义；如发现兼容阻塞，暂停并另行审批。
- LLM、数据库、记忆、关系、persona、NPC 领域模块和 R-03 文件。
- 同级项目、系统配置、全局 PATH、生产配置。

## 文档、Git、CI 与归档边界

- 实现分支必须从最新 `main` 创建，建议名 `feat/f-002-godot-fastapi-connectivity`。
- 任务卡批准不自动授权 Step 1、安装、分支、commit、push、PR、merge、远程 CI 或归档。
- 精确暂存，不使用 `git add -A`；F-001 授权不得复用。
- PR 以 `main` 为 base；任一必需门禁、UAT 或独立 QA 失败即停止。
- 默认 squash merge；未明确授权时不删除远程分支。
- 完成后归档至 `docs/archive/task-cards/F-002-godot-fastapi-connectivity.md`，重置 current task，并将 R-02 压缩为完成摘要。
- 不自动起草或进入 R-03。

## 风险、回滚与停止条件

主要风险：Godot 工具缺失、Windows/CI 行为差异、HTTP 与传输错误混淆、重复请求或晚到响应覆盖新状态、健康端点范围膨胀，以及低保真 UI 例外被误扩展为正式 UI。

回滚：F-002 应保持在独立分支且无数据迁移；代码可按任务提交回退。便携 Godot 工具如需移除，仍须另获删除授权，不能自动清理。

出现以下情况必须停止：

- Godot 不可调用且用户未提供路径或授权便携版本；
- Git 基线、工作树或文件范围出现未解释漂移；
- 需要修改 Dialogue v1、引入 LLM/数据库或进入 R-03；
- 已批准健康契约、timeout、retry、CORS 或低保真 UI 边界需要改变；
- Godot 自动化不可复现且没有获批准的替代门禁；
- P1/P2、UAT、CI 或独立 QA 失败。

## 完成定义

- [x] 验收标准全部通过；
- [x] API、Godot 状态、timeout、unavailable 和 retry 负例齐全；
- [x] FastAPI 与 Godot 真实本地连通；
- [x] 独立 QA 和用户 Godot UAT 通过；
- [x] 统一质量门禁与本地 CI 静态契约检查通过；远程 CI 留待 Git 交付；
- [x] 完整 diff 无范围外实现或敏感信息；
- [x] README、架构、测试、ADR 和项目管理文档一致；
- [ ] Git/PR/合并证据完整，F-002 已归档；
- [x] 未实现或进入 R-03。

## Step 5 独立 QA 结论

Step 5 已执行但未通过，发现 4 项可复现 P2：

1. Godot `JSON.parse()` 对冲突重复 key 采用 last-wins，非严格原始响应可误进入 `connected`。
2. `HTTPRequest` 默认跟随 redirect；8000 的 302 可跳到其他端口并以最终 200 进入 `connected`，未锁定 loopback origin。
3. `python -m cyber_town.api` 接受 `APP_HOST=0.0.0.0`，违反后端只绑定 loopback 的已批准边界。
4. 任务卡验收标准要求停服进入 `unavailable`，但 Windows Godot 4.7.2 实测为 `RESULT_TIMEOUT → timeout`；集成 oracle 接受两者，因此无法按当前任务卡给出唯一 PASS。

前三项需要实现与负向测试修复；第四项需要用户明确批准平台细化，或另行授权实现区分机制。在修复/裁决并完成独立复验前不得进入 Step 6。

独立 QA 的统一门禁仍通过：lock 38 packages、ruff、mypy 18 source files、schema、Godot import/unit/6 个真实 loopback 场景、pytest 132 passed、ignore/sensitive 均通过；故意失败传播和端口释放也通过。完整审阅 18 tracked 修改与 18 untracked 文件，staged 0，无缓存、敏感信息、Dialogue/LLM/数据库/NPC/R-03 越界。

用户随后授权在 Step 5 内修复前三项 P2，并采纳平台结果裁决：停服按 `HTTPRequest` 实际 result 映射，timeout 与 unavailable 均为合格的明确失败反馈。第一次修复后复验确认原四项均已修复/裁决，但又发现健康字段非字符串可触发 runtime error；该问题之后取得追加授权并完成下一段所述修复。

追加授权后的修复已完成：比较固定值前验证实际字段为 `TYPE_STRING`；Dictionary、Array、null、number、bool 类型矩阵全部映射 unavailable；真实嵌套对象 loopback 从原 runtime error/卡死转为 unavailable。第二次独立 QA 已通过，未发现剩余 P0/P1/P2/P3。

独立 QA 额外以真实 Godot HTTPRequest 重放 22 个响应变体，覆盖三个字段的五类非字符串值、40 层嵌套、escaped key/value、重复 member、字段顺序和空白；所有无效响应均进入 unavailable 且 Retry 可用，合法变体进入 connected。历史 duplicate、redirect、host 与停服 oracle 均通过；全量为 pytest 134 passed、9 integration 及全部既定门禁通过。

Step 5 判定通过；其后已完成 Step 6 用户 UAT 与最终本地交付审查。远程 Linux CI、提交、推送、PR、归档和 R-03 均未执行。

## Step 6 UAT 与最终审查结论

- `UAT_RESULT=PASS`。用户确认“环境与全量门禁、Connected、Timeout 与手动 Retry、Unavailable 与恢复”四组真实窗口检查均通过；截图明确显示后端 200/connected 和 503/unavailable/Retry，瞬时 timeout/retry/recovery 由用户完成确认。
- UAT 后端已按用户返回的 `PORT_8000_STOPPED=YES` 停止；自动复核确认 8000/8001 端口均已释放。
- 最终统一质量入口通过：lock 38 packages、ruff、mypy 18 source files、schema、Godot import/unit、9 个真实 loopback 集成场景、pytest 134 passed、ignore/sensitive preflight/final。
- Markdown 相对链接、CI workflow YAML 与静态契约、`git diff --check` 和完整 36 文件范围审查通过；未发现真实凭证、运行时数据、Godot cache、兄弟项目改动或 R-03 实现。
- 当前分支为 `feat/f-002-godot-fastapi-connectivity`；HEAD、main 与 origin/main 均为 `de6d66e376d9610f660de0b48f4983e653460cc8`；staged 0，18 tracked 修改、18 untracked。
- 当前状态为 `ready_for_git_delivery`。未提交、未推送、未创建 PR、未运行远程 CI、未合并或归档，不进入 R-03。

## Step 4 已完成事实

F-002 / Step 4 已完成真实本地连通与失败恢复。统一入口现运行 Godot editor import、GDScript 单测及 6 个真实 loopback 场景：停服→timeout、503→unavailable、真实 FastAPI→connected，以及 503/非法 JSON/延迟后的手动 retry→connected。测试工具只管理自己创建的进程和 listener，结束时验证 8000 端口释放，未增加生产故障路由。

Windows Godot 4.7.2 对无监听 `127.0.0.1:8000` 实测返回 `RESULT_TIMEOUT`，因此按锁定规则显示 timeout；503 明确覆盖 unavailable。这一任务卡验收文字与平台结果的细化需由 Step 5 独立 QA 和 Step 6 用户 UAT复核，不改变已锁定的 `RESULT_TIMEOUT → timeout` 映射。

本地全量门禁为 lock 38 packages、ruff、mypy 18 source files、schema、Godot import/unit/integration、pytest 132 passed、ignore 和 sensitive preflight/final 全部通过。README、架构、技术栈、测试策略、ADR、CI 与状态文档已同步。当前没有 Dialogue、LLM、数据库、NPC、正式素材或 R-03 实现；未提交、推送、创建 PR 或触发远程 CI。
