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

运行 `uv run --frozen python scripts/quality.py`。入口先执行 ignore/敏感信息预检，再执行 lock freshness、ruff、mypy、schema drift、Godot editor import、GDScript 单测、真实 loopback connectivity/recovery 和 pytest，最后复查仓库策略；不需要真实凭证、LLM、数据库或业务外部服务。

负向测试覆盖：worktree/index 内容分叉、staged/missing `.gitignore`、symlink/异常 mode、大小写与多种配置语法凭证键、精确 placeholder、BOM/非 UTF-8/超大文本、二进制魔数伪装、结构化配置重复键/递归/过深输入 fail-closed、敏感预检顺序、子命令缺失与失败传播、配置环境隔离、未知/多余 schema drift，以及用 Draft 2020-12 validator 在不依赖可选 format assertion 的情况下验证合法与非法 request/response/error fixtures。socket monkeypatch 只证明本地策略 helper 不触网；统一入口的离线边界由命令白名单、无外部服务配置和独立 QA 共同验证，不把该单元测试夸大为操作系统级断网证明。

GitHub Actions 在 `main` push、pull request 和人工触发时先执行 `uv sync --locked --all-groups`，再运行完全相同的质量入口。workflow 不使用 secrets、写权限、服务容器或发布步骤。本地 UAT、等价复现、最终独立审查和 PR #1 的 GitHub-hosted Linux runner 验证均已通过。

### F-002 自动化与 UAT 分工

- API 测试覆盖 200、JSON Content-Type、精确三字段、无额外字段、GET-only、无 socket/database 副作用和启动入口。
- GDScript 单测覆盖五态文案、严格响应解析、非 2xx、空/非法 JSON、缺失/额外/错误字段、timeout、传输失败、单在途请求和 retry。
- `scripts/connectivity_integration.py` 使用真实 HTTPRequest：无监听服务、503、重复 JSON key、非字符串字段、redirect 拒绝、真实 FastAPI、503→retry、非法 JSON→retry、延迟→timeout→retry，共 9 个场景；redirect target 必须零请求，每个 owned process/listener 都必须退出并释放端口。
- 自动化只验证状态机、场景资源和真实 loopback 通信。Step 6 用户 UAT 仍需在真实窗口观察布局、冻结文案、按钮可操作性及启动/停服后的恢复，不得由 headless 结果替代。
- CI 在 runner bootstrap 下载官方 Godot 包；质量阶段只访问 runner loopback。F-002 远程 CI 尚未运行。

## 首切片验收草案

1. 玩家可在固定 Godot 场景发出一条对话；请求中包含并回传 `trace_id`。
2. API 对非法 NPC、空/超长输入、重复 request、模型超时/无效结构化输出返回可预测错误或降级结果。
3. NPC 回复符合固定 persona 评审集，且 A/B NPC 或玩家 A/B 不发生上下文串扰。
4. 审计记录不保存 API key、完整原始敏感内容或模型内部推理；错误分类、耗时和 token/cost 字段可检查。
5. Godot 显示 loading、success、error，并按人工脚本验证一次完整流程。
