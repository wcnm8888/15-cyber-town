# 当前任务状态

状态：`git_delivery_authorized / F-007_multi_npc_isolation / pending_commit_push_pr_ci_merge_archive`。

F-006《确定性好感度系统》已完成 Git 交付并归档：PR #6 已 squash merge 到 `main` / `origin/main` 的 `3c2059aad7ef5a1e9dd0154ad49d2b0e93f8f47f`。完整任务卡见 [`../archive/task-cards/F-006-deterministic-affection.md`](../archive/task-cards/F-006-deterministic-affection.md)，实施计划见 [`../archive/task-cards/F-006-implementation-plan.md`](../archive/task-cards/F-006-implementation-plan.md)。

当前任务为 [`F-007 多 NPC 与隔离`](f-007-multi-npc-isolation-candidate.md)。Step 7 已完成。真实窗口首轮发现合法两行 reply 令关系底部为 `372>360` 的 P2；失败优先回归后仅将消息输入最低高度 `48→36`、内容间距 `4→2`，最终同场景与完整 `Reason` 同屏。重新 UAT 确认 Nia/Ivo/Rhea 独立 reply、trace、关系变化、切换清空和回切 owner 快照。Git 交付前审计又确认关系 GET 对未知 NPC 返回 200 初始快照并进入 repository read 的 P1；最小修复在 API 边界复用固定 persona allowlist，13 类非法路径均在持久化前拒绝、3 个合法 NPC 保持 200，最终统一门禁 `1319 passed`。用户已授权 Git 交付；当前仅推进提交、推送、PR、远端 CI、合并与归档，不进入 R-08 或部署。

持续边界：不得读取 `.env`、调用真实模型、读取/修改/复用 F-005 验收数据库、调用台账或预算；所有候选验证与示例保持 fake-only。
