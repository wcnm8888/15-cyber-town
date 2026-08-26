# 当前任务状态

状态：`delivered / archived / no_active_task`。

F-007《多 NPC 与隔离》已完成 Step 0—7、独立 fake-only QA、用户 Godot UAT、关系 GET allowlist P1 最小修复与最终 Git 交付。最终本地统一门禁为 `1319 passed`；PR #7 的 GitHub Linux `quality` 通过后，功能 squash merge 提交为 `a049a94ad2104a4629a8e201399bb66592319fc5`，PR #8 随后完成任务卡与实施计划归档。

完整任务卡见 [`../archive/task-cards/F-007-multi-npc-isolation.md`](../archive/task-cards/F-007-multi-npc-isolation.md)，实施计划见 [`../archive/task-cards/F-007-implementation-plan.md`](../archive/task-cards/F-007-implementation-plan.md)。

当前没有活动任务。roadmap 中 R-09 与 R-10 是最高优先级候选，但尚未选择；不得自动进入候选任务卡起草、Step 0、实现或部署。

持续边界：不得读取 `.env`、调用真实模型、读取/修改/复用 F-005 验收数据库、调用台账或预算；未获新授权的验证与示例保持 fake-only。
