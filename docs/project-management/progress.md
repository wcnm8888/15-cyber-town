# 项目进度

## 当前状态

- 生命周期：`F-005 / step_7_complete / ready_for_git_delivery`。
- F-005 Git 基线：分支为 `feat/f-005-long-term-memory-retrieval-evaluation`，HEAD / `main` / `origin/main` 均为 `3e03d64d129871495f3fe73295ee9b11478f2e71`；Python 3.12.10 / SQLite 3.47.1。已冻结长期双元 scope、4 个 fact keys、64/4096/4、30 天 TTL、2048 长期预算、2 秒锁等待和 SQLite 路径/ignore；旧 fake 测试误创建的正式路径 SQLite 已按用户专项授权定向删除、未读取内容，隔离根因已修复，真实调用台账与隔离验收库保留。
- F-005 Step 0—4：已完成标准库 SQLite schema/repository、双元 scope、显式记住/永久记住/忘记、版本/过期/容量/tombstone、事务幂等、确定性检索、唯一 persona system 下的不可信事实、8192/2048/256 预算及 Godot→FastAPI→FakeProvider 联调；自动测试数据库均位于 pytest `tmp_path`。
- F-005 Step 5 离线评估：固定 72 项 golden set precision `1.00`、recall `1.00`；跨 scope 泄漏、遗忘/过期召回、旧值复活和空结果虚构均为 0；纯短期跨 conversation baseline recall `0.00`。
- F-005 Step 5 调用治理：受 Git 忽略的 `data/acceptance-ledgers/f-005.sqlite3` 与计量 provider 已实现跨进程原子预留、Step 5 8 次/USD 0.035、Step 7 4 次/USD 0.015、总计 12 次/USD 0.05；provider 返回后先落脱敏 usage，reserved/unknown、损坏、预算耗尽和并发冲突 fail-closed。
- F-005 Step 5 真实专项：用户独立授权后完成跨 conversation 召回、repository/service 重建恢复、跨 player 隔离、更新替换、四类批准事实、Nia persona 优先、遗忘后不复活与空结果 honest unknown；实际 7 次调用、1244 输入 token、106 输出 token，逐次向上取整的保守台账费用 USD 0.000690，pending=0。显式记住/忘记、隔离拒绝与空结果均零 provider 调用。
- F-005 最新验证：统一 fake-only 全量 `1095 passed`；lock 45 packages、ruff、mypy 57 files、Schema、Godot import/unit、9 健康 + 10 对话 loopback、ignore/sensitive 全通过。完整门禁显式禁用 dotenv 与真实 provider。
- F-005 Step 6 已授权修复：首轮 5 项 P1、3 项 P2 均已补失败优先负例并修复；独立复审追加验证跨 conversation/NFKC 旧值清除、在途任务代次、已完成缓存旧值 replay 409、服务重启后的 Remember/Forget durable replay 不污染合法历史，以及默认启动链路 pytest SQLite 隔离。
- F-005 Step 6 独立复审：后端 reviewer `274 passed / 3 deselected`，Godot/API reviewer `360 passed`，两人最终均为 `NO FINDINGS / P0=0 / P1=0 / P2=0 / P3=0`；正式 acceptance ledger 仍为 7 次、1244/106 tokens、USD 0.000690、pending=0。
- 当前能力：保留 F-002 健康诊断、F-003 固定 Nia 对话与冻结公开 Dialogue v1；三元 scope 纯内存短期记忆和双元 scope 标准库 SQLite 长期事实分别隔离，唯一 persona 与统一工程预算共同约束 provider 多消息。
- 一致性：同 scope 等待≤2 秒、跨 scope provider 并发≤2；幂等共享/replay/Retry 不重复写入，degraded、失败、取消、孤儿与晚到结果不生成伪记忆。
- F-004 Step 4：FastAPI + FakeProvider 已验证 scope 隔离、最近 6 回合、422/503/502/504、degraded、replay/conflict 与失败恢复；真实 Godot → FastAPI → FakeProvider 对话 loopback 共 10 个场景，新增连续三轮和第二轮失败后手动 Retry 继续对话。
- F-004 历史归档时 fake-only 完整统一入口为 pytest 584 passed；该数值仅是历史基线，F-005 当前完整门禁为 1095 passed。
- 配置与隐私：自动化设置 `CYBER_TOWN_DISABLE_DOTENV=1` 并固定 provider disabled；统一门禁不读取真实 `.env`/API key、不调用真实模型；专项已批准的真实评估同样不保存 prompt、history、玩家消息或模型回复。
- F-004 Step 5 真实评估：同 scope 召回、跨 conversation/player 隔离、完整回合裁剪、Nia persona、6 回合容量和 replay 零额外调用均通过；真实调用共 8 次，其中后续 7 次完整记录 6326 输入/86 输出 tokens，峰值费用上界 USD 0.00289696。
- 调用台账已知缺口：Step 5 首个失败请求在 usage 打印前退出，其 token 与费用不可追溯；Step 7 已实际发生 8 次并超过原 4 次上限。任何后续真实调用须重新明确授权，不沿用旧额度，也不得伪造全部请求完整费用。
- F-004 交付：基线 `5ea85a3ec39cdd3df64f39626dfaf3b238305a24`；功能提交 `eb8a9cc69a93f004a346e8d27f81b10fa3c89a46` 已通过 PR #4 squash merge 并完成任务归档，当前 `main` / `origin/main` 为 `3e03d64d129871495f3fe73295ee9b11478f2e71`。
- F-004 Step 6 失败优先修复：2 个取消 orphan + 同 ID Retry 负例及 5 个 assistant 历史污染负例均先失败后通过；幂等 task 归属与完整 user/assistant 成功历史均严格校验；F-003 历史 UAT 与 F-004 未执行 UAT 的 P3 描述已澄清。
- F-004 Step 6 独立 QA 复审：后端专项 412 passed，最多 32 个 Retry waiter 仍只调用一次 provider、写入一次历史且释放 scope 锁；Godot/API 专项 22 passed，6 个独立污染/role/outcome 边界 fail-closed。两名 reviewer 均为 NO FINDINGS，全量 569 passed，零真实模型调用。
- Step 7 UAT：同 scope 回忆正确、新 scope 未泄漏真实代号，但空历史两次虚构其他代号，修复前 UAT 未通过。首轮 4 次/664 输入/196 输出/USD 0.00055088，第二轮 4 次/718 输入/197 输出/USD 0.00057596；Step 7 合计 8 次/1382 输入/393 输出/USD 0.00112684，超过原批准 4 次调用上限。
- F-004 累计真实调用 16 次，超过原 12 次总上限；Step 5 后 7 次加 Step 7 全部 8 次的可核算部分为 7708 输入/479 输出 token、USD 0.00402380。Step 5 首次失败请求 usage 仍不可追溯，不伪造完整总费用。
- Step 7 fake-only 修复：10 个空历史中英文/隔离/API 负例先失败后通过；明确追问先前交流且无历史时直接返回确定性 local-fallback，零 provider/费用/记忆写入；冻结 persona 与公开 v1 不变。专项 174 passed、全量 pytest 584 passed。
- Step 7 用户窗口最终复验：用户亲自运行真实 Godot 窗口与 fake 本地后端，新会话明确回答“不知道”；后端结束打印 `FAKE_PROVIDER_CALLS=0`，8000 端口释放，新增真实调用/token/费用均为 0。用户 UAT 通过。
- F-005 Step 7 用户 UAT：用户亲自在真实 Godot 窗口通过初始 unknown、记住、跨窗口/重启召回、更新、遗忘与最终 unknown；Step 7 为 3 次、500/141 tokens、USD 0.000408，F-005 累计 10 次、1744/247 tokens、USD 0.001098，pending=0。8000 端口已释放，正式数据库未创建。
- 交付历史：F-001/F-002/F-003/F-004 已分别经 PR #1/#2/#3/#4 完成交付与归档；F-005 已完成 Step 0—7 并达到 `ready_for_git_delivery`，不复用历史任务的 Git 授权。
- 临时资源：未发现已登记或可明确归属于 F-004 的项目外独立临时目录；项目 `.venv`、受忽略的 `.env`、Godot 缓存及共享工具保留，未删除任何目录。
- 尚未完成：F-005 Git 提交、push、PR、远程 CI、合并与最终归档均未授权或执行；尚未实现 Qdrant/embedding、好感度、多 NPC、R-06 或正式素材。

## 下一批准动作

等待用户另行授权 `F-005 Git 交付`；当前不提交、不推送、不创建 PR、不归档，也不进入 R-06。
