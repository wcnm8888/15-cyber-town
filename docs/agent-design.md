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
- `ConversationScope`：`player_id + npc_id + conversation_id`；短期完整回合必须严格过滤该三元 scope。
- `LongTermMemoryScope`：`player_id + npc_id`；只有显式批准的低敏感结构化事实允许跨 conversation 检索，来源 conversation/request/trace 不替代所有权隔离。
- `SharedModelClient`：共享连接池、限流、重试和成本统计；不能承载 NPC 记忆或 persona。
- `DialogueOrchestrator`：每次请求创建独立命令对象，写入同一 `trace_id` 的审计事件。

## 安全策略

系统提示、persona、检索记忆、玩家输入和模型输出必须标记来源。玩家文本与记忆均不得获得“指令优先级”；模型不得访问密钥、文件、网络或任意游戏状态。实施阶段新增：输入长度/频率限制、敏感内容策略、prompt-injection case、输出检查、人工复核路径与安全事件脱敏记录。

## 多 Agent 结论

首版不需要多 Agent。每个 NPC 是同一单 NPC 对话能力的独立领域实例，而非多个自主协作者。只有出现可独立并行、明确跨 NPC 协议、调度锁、共享世界事实和评估标准后，才评估 NPC 间互动。

## F-003 已归档 persona 基线

- 唯一 NPC 是 `neon_guide / Nia`，persona 由版本化 `nia_v1.json` 冻结；她不得声称直接访问工具、网络或数据库。F-005 只允许根据已经验证并明确注入的低敏感结构化事实回答，不得编造未注入的长期记忆。
- Godot 只调用 FastAPI；应用层选择 persona、执行 12 秒 deadline、严格校验 provider 结果并维护 10 分钟/256 项进程内幂等。具体 OpenAI SDK 类型只存在于 DeepSeek adapter。
- provider 固定 non-thinking、non-stream、零自动 retry；Godot 失败后只允许玩家手动 Retry，并复用同一 request ID 和冻结 payload。
- 结构化 audit 只允许 trace/request ID、persona/provider/model、结果、延迟、usage、费用估算和字符数，不记录原始 prompt、玩家消息、模型回复、API key 或 provider body。
- F-003 历史 Step 5 的 12 项真实 persona 用例与 Godot 端到端已通过；F-005 的真实评估、独立 QA 和用户 UAT 必须按当前任务分别授权和验收。

## F-005 当前长期记忆边界

- Nia 仍为唯一、最高优先级 system persona；只允许确定性服务管理 `game_alias`、`preferred_language`、`reply_style` 与 `favorite_cyber_town_topic`。模型既不能自行记住/删除，也不能把长期事实改写为 system/developer/tool 指令。
- 显式记住/忘记通过既有 Dialogue v1 直接返回 `completed / local-memory`，零 provider 调用；普通问题只读取双元 scope、active、未过期、匹配固定 key/别名的事实，随后作为 `UNTRUSTED_LONG_TERM_MEMORY` user 数据发送。
- 统一上下文顺序为唯一 persona system → 受限长期事实 → 完整短期 user/assistant → 当前 user；总工程预算 8192、长期事实最多 2048、回复预留 256，禁止半条事实、半回合和过期/遗忘正文复活。
- 72 项 fake-only golden set、Godot loopback 和专项授权的真实 DeepSeek 评估均已验证跨 conversation/重启恢复、跨 player 隔离、更新、遗忘和 honest unknown；Step 5 真实评估额外确认四类批准事实与 Nia persona 优先，7 次调用/USD 0.000690。Step 6 独立 QA 零发现，Step 7 用户真实窗口 UAT 以 3 次调用/USD 0.000408 通过跨窗口、重启、更新和遗忘验收；后续真实调用仍需独立授权和跨进程预算台账。
