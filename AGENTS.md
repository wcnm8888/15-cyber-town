# Cyber Town 项目规则

## 项目定位与阶段

- 等级：L（多模块、Agent、状态持久化、安全与可观测性）。
- 当前阶段：`no_active_task / F-005_delivery_via_PR_5`。F-001—F-004 已分别通过 PR #1—#4 交付并归档；F-005 起始 `main` 基线为 `3e03d64d129871495f3fe73295ee9b11478f2e71`，功能提交为 `338852e4dd03f8c679f8a2db920e2ba7bd6f968e`。F-005 Step 5 真实评估 7 次/USD 0.000690；独立 QA 最终 NO FINDINGS；Step 7 用户真实窗口 UAT 3 次/USD 0.000408；任务累计 10 次/USD 0.001098，pending=0。最终本地 fake-only 门禁 1095 passed，正式数据库未创建、8000 端口已释放；首轮 GitHub Linux `quality` 已通过，任务归档、最终 CI 与合并事实以 PR #5 为准。当前无活动任务，不得自动进入 R-06。
- 本项目是 Agent 工程学习项目，同时交付可运行、可交互、可验证的 AI NPC 小镇。

## 关键边界

- Godot 只负责场景、输入、动画、交互与 UI；FastAPI 负责 API、编排、并发和错误映射。
- Agent 只处理角色化理解与有限建议；持久化状态、权限、好感度计算与状态机由确定性服务处理。
- NPC 的 persona 与玩家关系按 `npc_id + player_id` 隔离；F-004 短期工作记忆必须完整使用 `player_id + npc_id + conversation_id` 三元 scope；模型客户端可共享。
- LLM 输出是未可信输入：必须经 schema、策略和确定性规则校验，不能直接写入游戏状态。
- 不把完整聊天记录或向量相似度当作长期记忆；不将原始敏感对话写入普通日志。
- 首版只做玩家—单 NPC 对话，不引入 NPC 自主协作、批量生成或 WebSocket。

## 工作方式

1. 先读取本文件、`docs/README.md`、`docs/project-management/current-task.md` 和 roadmap；再读取当前任务必要的架构、测试与决策文档。
2. roadmap 经用户确认后，用户选择一项；Codex 只起草一张任务卡，等待批准后才进入 Step 0。
3. 每次实现按任务卡进行，运行对应测试、lint/typecheck/build 或人工验证，并更新进度和证据。
4. UI 任务必须先完成项目设计稿和用户确认，再实现一个页面、一个视口、一个状态并等待视觉验收。

## 安全与交付

- 默认禁止读取、提交或输出真实密钥；只有用户对具体本地验收明确授权时，应用才能通过既有 Settings 读取被 Git 忽略的 `.env`，且不得显示、记录、复制到文档或提交。自动测试与 CI 只能使用 synthetic/fake provider。
- `.env`、日志、SQLite 数据、向量数据、Godot 导入缓存和测试报告不得入库。
- 不修改同级 `13-intelligent-travel-assistant`；不删除、移动或覆盖既有文件。
- 真实 LLM、外部数据库、部署、推送、PR、合并和生产操作需在相应任务中取得明确授权。

## 文档权威

`docs/README.md` 是文档地图；当前状态以 `current-task.md`、roadmap、progress 与 evidence 的职责划分为准。聊天记录不是项目事实来源。
