# 项目进度

## 当前状态

- 生命周期：`no_active_task / F-004_delivery_via_PR_4`。
- 当前能力：保留 F-002 健康诊断、F-003 固定 Nia 对话与冻结公开 Dialogue v1；新增三元 scope 纯内存短期记忆、最近 6 个完整回合、128 会话/1800 秒 TTL/LRU、8192 UTF-8 工程预算、provider 多消息和同 scope 串行。
- 一致性：同 scope 等待≤2 秒、跨 scope provider 并发≤2；幂等共享/replay/Retry 不重复写入，degraded、失败、取消、孤儿与晚到结果不生成伪记忆。
- F-004 Step 4：FastAPI + FakeProvider 已验证 scope 隔离、最近 6 回合、422/503/502/504、degraded、replay/conflict 与失败恢复；真实 Godot → FastAPI → FakeProvider 对话 loopback 共 10 个场景，新增连续三轮和第二轮失败后手动 Retry 继续对话。
- 当前 fake-only 完整统一入口 pytest 584 passed；lock 45 packages、ruff、mypy 42 files、Schema、Godot import/unit、9 健康 + 10 对话 loopback、ignore/sensitive 全部通过，新增空历史回忆负例已通过。
- 配置与隐私：自动化设置 `CYBER_TOWN_DISABLE_DOTENV=1` 并固定 provider disabled；统一门禁不读取真实 `.env`/API key、不调用真实模型；专项已批准的真实评估同样不保存 prompt、history、玩家消息或模型回复。
- F-004 Step 5 真实评估：同 scope 召回、跨 conversation/player 隔离、完整回合裁剪、Nia persona、6 回合容量和 replay 零额外调用均通过；真实调用共 8 次，其中后续 7 次完整记录 6326 输入/86 输出 tokens，峰值费用上界 USD 0.00289696。
- 调用台账已知缺口：Step 5 首个失败请求在 usage 打印前退出，其 token 与费用不可追溯；Step 7 已实际发生 8 次并超过原 4 次上限。任何后续真实调用须重新明确授权，不沿用旧额度，也不得伪造全部请求完整费用。
- F-004 交付：基线 `5ea85a3ec39cdd3df64f39626dfaf3b238305a24`；功能提交 `eb8a9cc69a93f004a346e8d27f81b10fa3c89a46` 已推送至 `feat/f-004-short-term-memory-context-budget`，PR #4 首个功能 HEAD 的 GitHub-hosted Linux `quality` 已通过；任务卡和实现计划在同一 PR 准备归档，最终 CI 和合并事实以 GitHub 为准。
- Step 6 失败优先修复：2 个取消 orphan + 同 ID Retry 负例及 5 个 assistant 历史污染负例均先失败后通过；幂等 task 归属与完整 user/assistant 成功历史均严格校验；F-003 历史 UAT 与 F-004 未执行 UAT 的 P3 描述已澄清。
- Step 6 独立 QA 复审：后端专项 412 passed，最多 32 个 Retry waiter 仍只调用一次 provider、写入一次历史且释放 scope 锁；Godot/API 专项 22 passed，6 个独立污染/role/outcome 边界 fail-closed。两名 reviewer 均为 NO FINDINGS，全量 569 passed，零真实模型调用。
- Step 7 UAT：同 scope 回忆正确、新 scope 未泄漏真实代号，但空历史两次虚构其他代号，修复前 UAT 未通过。首轮 4 次/664 输入/196 输出/USD 0.00055088，第二轮 4 次/718 输入/197 输出/USD 0.00057596；Step 7 合计 8 次/1382 输入/393 输出/USD 0.00112684，超过原批准 4 次调用上限。
- F-004 累计真实调用 16 次，超过原 12 次总上限；Step 5 后 7 次加 Step 7 全部 8 次的可核算部分为 7708 输入/479 输出 token、USD 0.00402380。Step 5 首次失败请求 usage 仍不可追溯，不伪造完整总费用。
- Step 7 fake-only 修复：10 个空历史中英文/隔离/API 负例先失败后通过；明确追问先前交流且无历史时直接返回确定性 local-fallback，零 provider/费用/记忆写入；冻结 persona 与公开 v1 不变。专项 174 passed、全量 pytest 584 passed。
- Step 7 用户窗口最终复验：用户亲自运行真实 Godot 窗口与 fake 本地后端，新会话明确回答“不知道”；后端结束打印 `FAKE_PROVIDER_CALLS=0`，8000 端口释放，新增真实调用/token/费用均为 0。用户 UAT 通过。
- 交付历史：F-001/F-002/F-003 已分别经 PR #1/#2/#3 交付归档；F-004 通过 PR #4 统一交付并准备归档，最终 CI 和合并事实以 GitHub 为准。
- 临时资源：未发现已登记或可明确归属于 F-004 的项目外独立临时目录；项目 `.venv`、受忽略的 `.env`、Godot 缓存及共享工具保留，未删除任何目录。
- 未实现：数据库、长期记忆、情节摘要、语义检索、跨进程恢复、多 NPC、正式素材和 R-05。

## 下一批准动作

当前无活动任务；等待用户从 roadmap 选择并批准下一张任务卡。F-004 授权、真实模型调用预算和 Git 交付授权不得复用于 R-05。
