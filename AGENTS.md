# Cyber Town 项目规则

## 项目定位与阶段

- 等级：L（多模块、Agent、状态持久化、安全与可观测性）。
- 当前阶段：`F-002` Step 6 已完成，用户 UAT 与最终本地交付审查通过，状态为 `ready_for_git_delivery`。尚未提交、推送、创建 PR、运行远程 CI 或归档，不得进入 R-03。
- 本项目是 Agent 工程学习项目，同时交付可运行、可交互、可验证的 AI NPC 小镇。

## 关键边界

- Godot 只负责场景、输入、动画、交互与 UI；FastAPI 负责 API、编排、并发和错误映射。
- Agent 只处理角色化理解与有限建议；持久化状态、权限、好感度计算与状态机由确定性服务处理。
- NPC 的 persona、玩家关系、会话和记忆必须按 `npc_id + player_id` 隔离；模型客户端可共享。
- LLM 输出是未可信输入：必须经 schema、策略和确定性规则校验，不能直接写入游戏状态。
- 不把完整聊天记录或向量相似度当作长期记忆；不将原始敏感对话写入普通日志。
- 首版只做玩家—单 NPC 对话，不引入 NPC 自主协作、批量生成或 WebSocket。

## 工作方式

1. 先读取本文件、`docs/README.md`、`docs/project-management/current-task.md` 和 roadmap；再读取当前任务必要的架构、测试与决策文档。
2. roadmap 经用户确认后，用户选择一项；Codex 只起草一张任务卡，等待批准后才进入 Step 0。
3. 每次实现按任务卡进行，运行对应测试、lint/typecheck/build 或人工验证，并更新进度和证据。
4. UI 任务必须先完成项目设计稿和用户确认，再实现一个页面、一个视口、一个状态并等待视觉验收。

## 安全与交付

- 禁止读取、提交或输出真实密钥；仅使用 `.env.example` 的空占位符。
- `.env`、日志、SQLite 数据、向量数据、Godot 导入缓存和测试报告不得入库。
- 不修改同级 `13-intelligent-travel-assistant`；不删除、移动或覆盖既有文件。
- 真实 LLM、外部数据库、部署、推送、PR、合并和生产操作需在相应任务中取得明确授权。

## 文档权威

`docs/README.md` 是文档地图；当前状态以 `current-task.md`、roadmap、progress 与 evidence 的职责划分为准。聊天记录不是项目事实来源。
