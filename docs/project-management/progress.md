# 项目进度

## 当前状态

- 生命周期：`no_active_task / F-005_delivery_via_PR_5`；当前没有获批准的后续任务。
- 当前能力：Godot/FastAPI 健康诊断、固定 Nia 对话、三元 scope 进程内短期记忆，以及双元 scope 标准库 SQLite 低敏感长期事实；公开 Dialogue v1、既有 Godot 场景和唯一 Nia persona 保持不变。
- F-005 交付：功能提交 `338852e4dd03f8c679f8a2db920e2ba7bd6f968e`，统一交付与归档载体为 GitHub PR #5；首个功能 HEAD 的 GitHub-hosted Linux `quality` 已通过，最终归档 HEAD 的 CI 和合并事实以 GitHub 为准。
- 最终自动化：统一 fake-only 质量入口 `1095 passed`；lock、ruff、mypy、Schema、Godot import/unit、9 健康 + 10 对话 loopback、ignore/sensitive 均通过，自动化不读取 `.env` 或调用真实 provider。
- 检索评估：72 项固定 golden set precision `1.00`、recall `1.00`；跨 scope 泄漏、已遗忘召回、旧值复活和空结果虚构均为 0。
- 独立 QA：首轮 5 项 P1、3 项 P2 及近邻全部失败优先修复；两名 reviewer 最终均为 `NO FINDINGS`。
- 真实评估与用户 UAT：Step 5 为 7 次、1244/106 tokens、USD 0.000690；Step 7 为 3 次、500/141 tokens、USD 0.000408；合计 10 次、1744/247 tokens、USD 0.001098，pending=0，未超预算。
- 用户真实 Godot 窗口已验证初始 unknown、记住、跨窗口/重启召回、更新、遗忘及最终 unknown；8000 端口已释放，正式业务数据库不存在。
- 运行资源：Step 5/Step 7 隔离 SQLite、metadata-only 调用台账及 SQLite sidecar 均受 Git 忽略并保留；项目 `.venv`、`.env`、Godot 缓存与共享工具同样保留，未获得任何删除授权。
- 未覆盖：Qdrant/embedding、好感度、多 NPC、正式素材、生产部署及 R-06 均未实现。

## 下一批准动作

等待用户根据 roadmap 选择下一候选任务；不得自动起草任务卡、读取 API key、调用真实模型或进入 R-06。
