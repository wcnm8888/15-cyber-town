# 架构与当前实现边界

## 分层与单向流

```text
Godot（场景 / 输入 / 动画 / UI）
  -- REST JSON --> FastAPI API（鉴权边界 / schema / 错误映射 / trace_id）
  --> 对话编排应用层（单轮用例、幂等、输出校验、降级、审计）
  --> NPC 领域层（版本化 persona 与 provider-neutral 契约）
  --> 适配层（DeepSeek client、fake provider、日志/指标；未来才可能加入存储）
```

Godot 不直连 LLM 或数据库；领域层不直接依赖 FastAPI、Godot、具体 LLM SDK 或 Qdrant。外部模型返回与工具参数一律作为不可信输入处理。

## F-003 当前模块

| 模块 | 职责 | 不负责 |
| --- | --- | --- |
| `game/` | 最小场景、邻近交互、对话 UI、请求状态 | 角色推理、持久化、好感度规则 |
| `backend/api/` | HTTP schema、错误码、关联 trace_id | 业务策略与 SQL 细节 |
| `backend/application/` | 单轮对话编排、12 秒 deadline、进程内幂等、输出校验与降级 | persona 文本、HTTP、Godot 或具体 SDK |
| `backend/domain/` | 固定 Nia persona、provider-neutral DTO/错误和严格 loader | 网络、ORM、LLM SDK、记忆或关系状态 |
| `backend/infrastructure/llm/` | fake provider 与隔离 DeepSeek adapter、SDK 错误分类和 usage 转换 | 业务决策、持久化或原始 provider 对象外泄 |

当前 API 同时提供 `GET /api/v1/health` 与严格的 `POST /api/v1/dialogue`。Godot 保留 F-002 连接诊断场景，并新增独立低保真对话场景；Godot 只访问 FastAPI，不持有 API key 或直连 provider。F-003 已实现固定 `neon_guide / Nia`、版本化 `nia_v1.json`、应用服务、进程内幂等、fake provider 和 DeepSeek adapter；没有数据库、记忆、关系、多 NPC 或工具调用。

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
- F-003 不创建持久化状态；persona 是版本化只读 JSON，单轮请求不保存聊天历史、关系或记忆。
- 每次 HTTP 尝试生成独立 `trace_id`；客户端 `request_id` 标识逻辑请求。进程内幂等 TTL 10 分钟、最多 256 项，同 ID 同 payload 合并/复用，同 ID 不同 payload 返回冲突。
- 进程重启后幂等缓存丢失并可能再次计费，这是已接受的当前边界；SQLite、持久审计和持久幂等必须由后续独立任务批准。

## 失败与通信

首版 REST 足够。当前诊断场景加载后自动发起一次健康请求，同一时刻只允许一个在途请求；3 秒 timeout 或失败后仅允许用户手动 Retry。严格匹配健康 JSON 才进入 connected；非 2xx、无效/多余/缺失字段及非 timeout 传输失败进入 unavailable；`RESULT_TIMEOUT` 进入 timeout。Windows 4.7.2 下后端未监听的真实行为实测为 timeout，503 fixture 明确覆盖 unavailable。

仅当需要 token 级流式回复、服务器主动推送、多人同时状态广播或高频世界同步时，评估 WebSocket/SSE；不能因“实时”标签提前引入。

F-003 模型调用采用并发上限 2、provider timeout 12 秒、Godot timeout 15 秒、non-thinking、non-stream 和 SDK 零自动 retry。只有用户手动 Retry 可以再次发起逻辑相同的失败请求；内容过滤可返回确定性 local fallback，其他 provider 失败映射为安全公共错误。审计只记录 allowlist 元数据、长度、usage、延迟和费用估算，不记录密钥、原始 prompt、玩家消息、模型回复或 provider body。
