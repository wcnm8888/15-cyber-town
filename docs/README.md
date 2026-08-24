# Cyber Town 文档地图

## 当前工作入口

- 项目规则：[`../AGENTS.md`](../AGENTS.md)
- 产品与范围：[`product-brief.md`](product-brief.md)
- 候选路线：[`project-management/roadmap.md`](project-management/roadmap.md)
- 当前任务：[`project-management/current-task.md`](project-management/current-task.md)
- 当前计划：[`project-management/implementation-plan.md`](project-management/implementation-plan.md)
- 当前状态：[`project-management/progress.md`](project-management/progress.md)
- 验收证据：[`project-management/evidence.md`](project-management/evidence.md)

roadmap 与 `F-001` 已由用户确认；Step 0 已完成并因稳定 Python 运行时缺失停在工具链门禁。未创建 `memory-bank/`，本 `docs/` 是唯一权威文档体系。

## 权威文档与更新规则

| 文档 | 唯一职责 | 何时更新 | 是否保存历史 |
| --- | --- | --- | --- |
| `product-brief.md` | 当前目标、用户、范围、非目标、成功标准 | 产品决策变化 | 否 |
| `architecture.md` | 当前模块、数据流、边界与失败降级 | 架构变化 | 否 |
| `tech-stack.md` | 已选/待验证技术、替代项和验证方法 | 技术决策变化 | 否 |
| `agent-design.md` | Agent 能力、隔离、工具与安全边界 | Agent 设计变化 | 否 |
| `memory-design.md` | 记忆生命周期、检索与遗忘规则 | 记忆方案变化 | 否 |
| `evaluation-strategy.md` | 角色、记忆、安全、延迟和成本评估 | 评估策略变化 | 否 |
| `testing-strategy.md` | 测试分层与质量门禁 | 测试策略变化 | 否 |
| `decisions.md` | 长期有效的架构决策与后果 | 重要决策确认 | 是，ADR 追加 |
| `project-management/roadmap.md` | 未完成候选任务、优先级、依赖 | 产品优先级变化 | 仅完成摘要 |
| `project-management/current-task.md` | 唯一活动任务卡及 Step | 任务选择或 Step 状态变化 | 否 |
| `project-management/implementation-plan.md` | 当前任务的可执行 Step、文件和验证 | 当前任务计划或阻塞变化 | 否 |
| `project-management/progress.md` | 当前状态、已验证结果、阻塞、下一批准动作 | 阶段收口 | 仅最近摘要 |
| `project-management/evidence.md` | 可复现的检查与验收结论索引 | 完成验证时 | 是，脱敏 |
| `archive/task-cards/` | 已关闭任务卡 | 任务合并并收口后 | 是 |

发生冲突时：当前代码、Schema、测试和 Git 事实 > 用户已批准范围/任务卡/设计稿 > 当前架构与测试文档 > roadmap、progress、evidence > archive、聊天记录。当前没有代码与任务卡，用户已锁定的启动范围优先。

## 读取最小集

新会话先读 `AGENTS.md`、本文件、roadmap、current-task、progress、evidence 和最近相关 ADR；只在需要时再读相应专项文档。不得将聊天记录、完整日志、密钥或临时截图当成长久文档。
