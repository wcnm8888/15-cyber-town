# F-006 实现计划

状态：`step_7_complete / awaiting_git_delivery_authorization`。

本计划只服务于已批准的 [`F-006 任务卡`](current-task.md)。Step 0 已完成：任务合同、SQLite 追加迁移策略、F-005 已合并事实和最小视觉契约均已锁定。Step 1 已完成：功能分支、失败优先的 F-006 配置边界测试与冻结配置均已建立。Step 2 已完成：纯领域严格建议解析、确定性规则与状态机已通过定向验证。Step 3 已完成：有序迁移、`0002`、状态/事件 repository、事务幂等、锁边界与审计回放均已通过验证。Step 4 已完成：同次受限建议、只读关系 GET、低保真 Godot 展示与 fake-only loopback 均已通过验证。Step 5 已完成：纯内存对抗/性质评估与 FakeProvider 受控操纵回归均无违规。Step 6 已完成：黑盒 FakeProvider HTTP QA、操纵输入和并发 scope 验证均无产品缺陷。Step 7 已完成：最小视口修复、重新用户 UAT 与最终 fake-only 本地门禁均通过；等待单独的 Git 交付授权。

## 已锁定决策

- 关系 scope：`player_id + npc_id`；初始 `20`，范围 `0..100`，单次最大 `±2`，每日一次有效非零变化。
- 分类：`supportive`、`friendly`、`neutral`、`dismissive`、`hostile`；非零变化要求 `confidence >= 80`。
- LLM 只在现有对话调用中给出内部严格建议；确定性服务拥有规则、状态机和持久化写入权。
- SQLite 采用有序追加迁移和新的 `0002_relationship_state.sql`；禁止修改 `0001_long_term_memory.sql` 或创建第二数据库。
- 新增只读关系 GET，Dialogue v1 保持不变；获批准的最小 Godot 视觉契约已在 Step 4 内完成，后续正式视觉设计仍不在范围。
- F-006 全程 fake-only，不额外调用真实 provider，也不设置真实调用预算。

## 后续地图

1. Step 1：`feat/f-006-deterministic-affection`、失败优先配置/边界测试。（已完成：首次 77 failed，最终 `test_config.py` 354 passed。）
2. Step 2：严格建议契约、确定性规则、状态机与参数化性质测试。（已完成：首次模块缺失，最终领域 68 passed、配置联合 422 passed。）
3. Step 3：迁移列表、`0002`、状态/事件 repository、事务、幂等、锁与审计回放。（已完成：34 项定向测试、全套 1248 项、mypy/ruff/format/diff 均通过。）
4. Step 4：DialogueService、只读 API、已批准的 Godot 展示、FakeProvider loopback 和必要文档。（已完成：140 项定向后端测试、Godot 单测、10 场景关系 loopback 通过。）
5. Step 5：fake-only 注入/操纵对抗、并发与性质评估。（已完成：4040 个规则/冷却判定、24 个越权/注入建议、2 个 UTC 日界和 3 条 completion→API 操纵回归，违规 0；关系专项 82 passed。）
6. Step 6：独立 QA。（已完成：临时 FakeProvider HTTP 黑盒验证初始/成功/重放/scope/422、越权 suggestion 和 4 请求并发，未确认产品缺陷；本地浏览器 loopback 被工具策略拒绝并记录。）
7. Step 7：用户真实 Godot 窗口 + FakeProvider UAT 与最终 fake-only 门禁。（已完成：最小视口修复后，用户截图确认 `Reason: rule_friendly` 完整可见；统一质量入口通过。）
8. Git 交付：单独授权。
