# Agent 能力地图与边界

## 能力地图

| 能力 | Agent 可做 | 确定性层必须做 | 验收方向 |
| --- | --- | --- | --- |
| Persona 对话 | 基于不可覆盖的角色配置生成短回复 | 加载版本化 persona、长度/格式/安全校验 | 角色评审集与越狱负例 |
| 上下文选择 | 候选记忆相关性排序或摘要建议 | token 预算、作用域过滤、冲突规则 | 召回精度、上下文长度 |
| 情绪/互动分类 | 输出受约束的类别和置信信息 | 枚举校验、分数映射、阈值、关系状态机 | 分类一致性与边界测试 |
| 游戏动作 | 提议有限意图 | 白名单、权限、前置条件、事务 | 不允许越权状态修改 |
| 失败处理 | 生成可解释但不虚构的回复 | 超时、重试、熔断、降级和错误码 | 故障注入测试 |

## 隔离模型

- `NpcProfile`：静态、版本化 persona；不同 NPC 绝不共享可变提示状态。
- `ConversationScope`：`player_id + npc_id + conversation_id`；短期消息、关系与记忆检索都必须过滤该 scope。
- `SharedModelClient`：共享连接池、限流、重试和成本统计；不能承载 NPC 记忆或 persona。
- `DialogueOrchestrator`：每次请求创建独立命令对象，写入同一 `trace_id` 的审计事件。

## 安全策略

系统提示、persona、检索记忆、玩家输入和模型输出必须标记来源。玩家文本与记忆均不得获得“指令优先级”；模型不得访问密钥、文件、网络或任意游戏状态。实施阶段新增：输入长度/频率限制、敏感内容策略、prompt-injection case、输出检查、人工复核路径与安全事件脱敏记录。

## 多 Agent 结论

首版不需要多 Agent。每个 NPC 是同一单 NPC 对话能力的独立领域实例，而非多个自主协作者。只有出现可独立并行、明确跨 NPC 协议、调度锁、共享世界事实和评估标准后，才评估 NPC 间互动。

## F-003 当前切片

- 唯一 NPC 是 `neon_guide / Nia`，persona 由版本化 `nia_v1.json` 冻结；她不得声称拥有工具、网络、数据库或长期记忆。
- Godot 只调用 FastAPI；应用层选择 persona、执行 12 秒 deadline、严格校验 provider 结果并维护 10 分钟/256 项进程内幂等。具体 OpenAI SDK 类型只存在于 DeepSeek adapter。
- provider 固定 non-thinking、non-stream、零自动 retry；Godot 失败后只允许玩家手动 Retry，并复用同一 request ID 和冻结 payload。
- 结构化 audit 只允许 trace/request ID、persona/provider/model、结果、延迟、usage、费用估算和字符数，不记录原始 prompt、玩家消息、模型回复、API key 或 provider body。
- Step 5 的 12 项真实 persona 用例与 Godot 端到端已通过；这不等同于独立 QA、用户窗口 UAT，也不授权记忆、多 NPC 或 R-04。
