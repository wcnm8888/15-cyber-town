# F-008 实施计划（归档）

状态：`archived / delivered / 2026-08-26`。

本归档计划对应 [`F-008《可观测性与 Agent 评估》`](F-008-observability-agent-evaluation.md)，来源为 roadmap `R-09`。功能 worktree 固定为 `E:\Agent\comprehensive-cases\15-cyber-town-f008`，分支为 `feat/f-008-observability-agent-evaluation`，基线为 `origin/main / 742317ca560f01fc2e4a7f1e73ebb2a6096af37f`。

| Step | 内容 | 状态 |
| --- | --- | --- |
| 0 | 契约、隐私、存储、CLI、retention、replay 与资源决策 | 完成 |
| 1 | metadata DTO/enum/HMAC/recorder protocol 与禁止原文边界 | 完成 |
| 2 | FastAPI/DialogueService/provider/记忆/关系 instrumentation | 完成 |
| 3 | 版本化 evaluator、24-case fixture 与三进程重复基线 | 完成 |
| 4 | 独立 SQLite、只读 CLI、retention 标记与 replay index | 完成 |
| 5 | fake-only 综合矩阵、故障注入、性能、重启与回放 | 完成；P1 已修复，误生成的 2 个 synthetic `.env` 与 1 个 `.env.example` 已精确清理并复核 |
| 6 | 独立 fake-only QA | 完成；无未关闭缺陷，完整门禁通过 |
| 7 | 用户 UAT、最终门禁与 Git 交付准备 | 完成；Godot/CLI UAT、重启恢复、24-case 三进程评估与最终 1418-test 门禁通过 |

F-008 Step 0—7 已完成。四个可二分功能提交 `fb732f0`、`eda6b54`、`5fc19a5`、`9afa28b` 经 PR #11 的 GitHub Linux `quality` 通过后 squash merge 为 `c78f1c190bd3a3753e849aa7da76c88dbf5c27b2`。最终统一门禁为 `1418 passed`；未部署、未进入 R-10 或选择下一 roadmap 任务。

完整范围、阶段记录和证据见 [`F-008-observability-agent-evaluation.md`](F-008-observability-agent-evaluation.md)。
