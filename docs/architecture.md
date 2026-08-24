# 架构（候选，待任务卡逐项确认）

## 分层与单向流

```text
Godot（场景 / 输入 / 动画 / UI）
  -- REST JSON --> FastAPI API（鉴权边界 / schema / 错误映射 / trace_id）
  --> 对话编排应用层（上下文预算、重试、降级、审计）
  --> NPC 领域层（persona、会话、关系、记忆策略、状态机）
  --> 适配层（LLM client、SQLite repository、可选 vector store、日志/指标）
```

Godot 不直连 LLM 或数据库；领域层不直接依赖 FastAPI、Godot、具体 LLM SDK 或 Qdrant。外部模型返回与工具参数一律作为不可信输入处理。

## 首个切片的候选模块

| 模块 | 职责 | 不负责 |
| --- | --- | --- |
| `game/` | 最小场景、邻近交互、对话 UI、请求状态 | 角色推理、持久化、好感度规则 |
| `backend/api/` | HTTP schema、错误码、关联 trace_id | 业务策略与 SQL 细节 |
| `backend/application/` | 单轮对话编排、超时、重试、降级 | persona 文本与存储实现 |
| `backend/domain/` | NPC/会话/关系/记忆的纯模型与规则 | 网络、ORM、LLM SDK |
| `backend/infrastructure/` | provider、SQLite、日志、指标实现 | 业务决策 |

当前已创建 `backend/src/cyber_town` 的配置、v1 契约基础设施和最小 `api` 包。API 只提供 `GET /api/v1/health`，精确返回固定的 service/status/api_version；`game/` 只包含一个 `Control` 诊断场景、`HTTPRequest` 客户端、有限状态映射和无第三方依赖测试。对话路由、应用/领域编排、LLM 和存储实现仍不存在。

## 工程门禁边界

```text
开发者 / GitHub Actions
  --> uv sync --locked --all-groups
  --> scripts/quality.py
      --> Git ignore / 敏感信息预检
      --> lock freshness --> ruff --> mypy --> schema drift
      --> Godot import/unit --> loopback connectivity/recovery --> pytest
      --> Git ignore / 敏感信息复检
```

本地与 CI 复用同一入口。安全预检在其他工具前执行，同时检查 worktree 与 stage-0 Git index；扫描结果只输出路径、行号和规则。集成 harness 只占用 `127.0.0.1:8000`：启动真实 FastAPI 验证 connected，并以测试专用 loopback fixture 验证 503、非法 JSON、延迟、手动 retry 和端口回收，不向生产 API 增加故障路由。CI 仅有 `contents: read`，不读取 secrets、不启动 service container、不调用业务外部系统；bootstrap 从公开发行源下载经 SHA-256 固定的 Godot 4.7.2 Linux 包。F-002 的远程 CI 与合并事实由 PR #2 记录。

## 状态与一致性

- 主键范围：`player_id`、`npc_id`、`conversation_id`；关系按 `(player_id, npc_id)`，记忆按同一命名空间隔离。
- SQLite 是结构化真相来源：NPC 配置版本、会话元数据、关系数值、记忆元数据、审计索引与幂等请求记录。
- 每次对话先生成 `trace_id` 和客户端请求幂等键；在一个事务内保存可持久事实。模型失败不得部分更新关系或记忆。
- 内存只可作短暂缓存/锁；重启后不得丢失已确认的领域事实。

## 失败与通信

首版 REST 足够。当前诊断场景加载后自动发起一次健康请求，同一时刻只允许一个在途请求；3 秒 timeout 或失败后仅允许用户手动 Retry。严格匹配健康 JSON 才进入 connected；非 2xx、无效/多余/缺失字段及非 timeout 传输失败进入 unavailable；`RESULT_TIMEOUT` 进入 timeout。Windows 4.7.2 下后端未监听的真实行为实测为 timeout，503 fixture 明确覆盖 unavailable。

仅当需要 token 级流式回复、服务器主动推送、多人同时状态广播或高频世界同步时，评估 WebSocket/SSE；不能因“实时”标签提前引入。

模型调用采用受限并发、总超时、有限重试（仅瞬时失败）、熔断/退避和用户可理解的降级回复。降级事件必须可审计，但不记录原始敏感正文。
