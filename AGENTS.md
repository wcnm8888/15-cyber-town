# Cyber Town 项目规则

## 项目定位与阶段

- 等级：L（多模块、Agent、状态持久化、安全与可观测性）。
- 当前阶段：`delivered_and_archived / F-007_multi_npc_isolation / awaiting_next_task_selection`。F-001—F-007 已分别通过 PR #1—#7 交付；F-007 的 PR #7 功能合并提交为 `a049a94ad2104a4629a8e201399bb66592319fc5`，任务卡与实施计划随后由 PR #8 归档。当前没有活动任务；进入下一候选任务卡或 Step 0 前须取得用户授权。仍不得读取 `.env`、调用真实模型或复用 F-005 验收资源。
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

## 临时资源生命周期

- 创建 Git worktree、临时目录、测试/UAT SQLite、日志、报告或本地服务前，必须向用户说明准确路径、所属任务与 Step、内容类别、是否可能含敏感信息、预计保留期限和计划回收方式；随机后缀目录也必须登记。登记须以规范化绝对路径作为唯一标识，并将创建时间、责任任务/Step、状态和期限作为脱敏元数据持久化到当前任务卡或 `docs/project-management/evidence.md`。
- Codex 不执行临时资源删除。资源到期时必须先盘点并列出保留/删除建议、准确路径、影响范围、可恢复性和安全的手动删除方式，明确告诉用户哪些目标可以删除；随后由用户手动删除，Codex 只在用户反馈后执行只读复核。除非用户以后明确修改本条长期规则，不得因单次阶段授权自行恢复代删模式。
- Step、QA、UAT 与 Git 交付的完成、阻塞、取消、崩溃恢复和会话移交都必须更新持久化台账并执行收口门禁。用户可见报告须将仍在使用、已到期、用户已删除、历史上由 Codex 获准删除和明确保留的资源分别列示；不得仅在 evidence 或过程日志中记录而省略汇报。
- 建议用户手动回收前，必须盘点目标内 tracked、untracked、ignored、嵌套仓库和可能敏感的资源类别，只读取处置所需元数据，不读取秘密或数据库内容；手动清单必须明确这些资源会随目标一并删除及其可恢复性。
- 回收必须使用资源所属工具的安全入口，例如 Git worktree 使用 `git worktree remove`。执行前必须解析 canonical/real path，检查 Windows reparse point/junction，并验证目标位于用户批准根目录内且与 `git worktree list --porcelain` 的注册路径完全一致；明确拒绝盘符根、项目集合根、主 worktree、正式项目目录及其 reparse target。普通回收失败时立即停止并报告，未经单独授权不得使用 `--force`、递归删除或清理分支。
- Git 交付完成后，应先保留历史任务分支；同步正式目录前必须确认工作区干净、当前分支与 upstream 明确、已 fetch 最新远端，并验证本地 `main` 是 `origin/main` 的祖先。只允许 `git switch main` 后执行 `git merge --ff-only origin/main`；任一前置条件不满足即停止报告。随后核对 `git worktree list`、工作区状态、端口、正式数据库路径和临时资源台账。最终报告须明确删除清单、保留清单、磁盘回收量和剩余风险。

## 安全与交付

- 默认禁止读取、提交或输出真实密钥；只有用户对具体本地验收明确授权时，应用才能通过既有 Settings 读取被 Git 忽略的 `.env`，且不得显示、记录、复制到文档或提交。自动测试与 CI 只能使用 synthetic/fake provider。
- `.env`、日志、SQLite 数据、向量数据、Godot 导入缓存和测试报告不得入库。
- 不修改同级 `13-intelligent-travel-assistant`；不删除、移动或覆盖既有文件。
- 真实 LLM、外部数据库、部署、推送、PR、合并和生产操作需在相应任务中取得明确授权。

## 文档权威

`docs/README.md` 是文档地图；当前状态以 `current-task.md`、roadmap、progress 与 evidence 的职责划分为准。聊天记录不是项目事实来源。
