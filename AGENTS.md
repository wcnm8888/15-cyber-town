# Cyber Town 项目规则

## 项目定位与阶段

- 等级：L（多模块、Agent、状态持久化、安全与可观测性）。
- 当前阶段：`delivered_and_archived / F-007_multi_npc_isolation / awaiting_next_task_selection`。F-001—F-007 已分别通过 PR #1—#7 交付；F-007 经 PR #7 的 GitHub Linux `quality` 通过后，于 2026-08-26 squash merge 到 `main` / `origin/main` 的 `a049a94ad2104a4629a8e201399bb66592319fc5`，并已完成任务卡与实施计划归档。当前没有活动任务；进入下一候选任务卡或 Step 0 前须取得用户授权。仍不得读取 `.env`、调用真实模型或复用 F-005 验收资源。
- 本项目是 Agent 工程学习项目，同时交付可运行、可交互、可验证的 AI NPC 小镇。

## 关键边界

- Godot 只负责场景、输入、动画、交互与 UI；FastAPI 负责 API、编排、并发和错误映射。
- Agent 只处理角色化理解与有限建议；持久化状态、权限、好感度计算与状态机由确定性服务处理。
- NPC 的 persona 与玩家关系按 `npc_id + player_id` 隔离；F-004 短期工作记忆必须完整使用 `player_id + npc_id + conversation_id` 三元 scope；模型客户端可共享。
- LLM 输出是未可信输入：必须经 schema、策略和确定性规则校验，不能直接写入游戏状态。
- 不把完整聊天记录或向量相似度当作长期记忆；不将原始敏感对话写入普通日志。
- 当前只做玩家与所选固定 NPC 的一对一对话，不引入 NPC 自主协作、批量生成或 WebSocket。

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
