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

目录仅是规划，尚未创建代码目录或业务文件。

## 状态与一致性

- 主键范围：`player_id`、`npc_id`、`conversation_id`；关系按 `(player_id, npc_id)`，记忆按同一命名空间隔离。
- SQLite 是结构化真相来源：NPC 配置版本、会话元数据、关系数值、记忆元数据、审计索引与幂等请求记录。
- 每次对话先生成 `trace_id` 和客户端请求幂等键；在一个事务内保存可持久事实。模型失败不得部分更新关系或记忆。
- 内存只可作短暂缓存/锁；重启后不得丢失已确认的领域事实。

## 失败与通信

首版 REST 足够：单次输入—回复、NPC 查询和健康检查均是请求/响应。Godot 的 `HTTPRequest` 支持回调、取消和明确 timeout；每个并发请求使用独立实例/队列。后端为网络 I/O 使用 async client；同步 SQLite 操作不得阻塞事件循环。

仅当需要 token 级流式回复、服务器主动推送、多人同时状态广播或高频世界同步时，评估 WebSocket/SSE；不能因“实时”标签提前引入。

模型调用采用受限并发、总超时、有限重试（仅瞬时失败）、熔断/退避和用户可理解的降级回复。降级事件必须可审计，但不记录原始敏感正文。
