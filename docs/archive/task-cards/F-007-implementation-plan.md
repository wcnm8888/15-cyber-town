# F-007 实施计划（归档）

状态：`archived / delivered / 2026-08-26`。

F-007 Step 0—7 已完成。交付过程中先后关闭控制空白 `npc_id` 绕过 allowlist 的 P1、固定 640×400 视口裁切 `Reason` 的 P2，以及关系 GET 在持久化前未拒绝未知 NPC 的 P1；三项均以失败优先回归、独立复审或 UAT 证据收口。最终 fake-only 统一门禁为 `1319 passed`，Dialogue v1 与 SQLite migration 不变。

四个可二分提交 `a02bb4c`、`2fba507`、`f381316`、`15cef84` 已推送；PR #7 的 GitHub Linux `quality` 通过后，于 2026-08-26 squash merge 到 `main` / `origin/main` 的 `a049a94ad2104a4629a8e201399bb66592319fc5`。未进入部署或下一 roadmap 任务。

完整范围、阶段记录与证据见 [`F-007-multi-npc-isolation.md`](F-007-multi-npc-isolation.md)。
