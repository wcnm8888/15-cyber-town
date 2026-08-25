# 记忆设计（分阶段）

## 原则

记忆是带来源、作用域、重要性、有效期和可撤销性的事实/摘要，不是聊天记录备份。任何检索结果都可能包含过时、错误或注入内容，必须按 scope、来源和预算过滤。

## 当前两层模型与后续候选

| 层级 | 内容与存储 | 生命周期 | 首阶段 |
| --- | --- | --- | --- |
| 工作记忆 | `player_id + npc_id + conversation_id` 三元 scope 内最近完整 user/assistant 回合；仅当前进程内存 | 最近 6 回合、128 活动 scope、idle TTL 1800 秒；服务重启后丢失 | F-004 已实现 |
| 结构化长期事实 | `player_id + npc_id` 双元 scope；标准库 SQLite 中的显式、白名单、低敏感事实及来源/version/status | 默认 30 天、显式永久、更新递增版本、遗忘清空正文；每 scope 64、全局 4096 | F-005 已通过 pytest 隔离数据库、真实 DeepSeek 评估及用户真实 Godot 窗口 UAT |
| 语义检索候选 | embedding/向量召回或 Qdrant | 必须另立任务、证明准确率、隔离、删除一致性与费用收益 | F-005 明确不实现 |

## 处理管线

当前 F-005 管线分两条确定性路径：

1. 显式管理：严格公开 Dialogue v1 → 冻结中英文记住/永久记住/忘记命令 → `(player_id, npc_id)` → SQLite `BEGIN IMMEDIATE`、request 指纹幂等、容量/TTL/版本/tombstone → 返回现有 `completed / local-memory`；此路径不调用 provider，也不把命令写成短期历史。
2. 普通对话：严格三元 conversation scope → 只检索同 `(player_id, npc_id)`、active、未过期且 `confidence > 0` 的相关长期事实 → 精确 key 优先于固定别名，按 importance/confidence/updated_at/memory_id 确定性排序 → 统一 UTF-8 工程预算 → 唯一 Nia system + 明确标为不可信的长期事实 user 数据 + 完整短期 user/assistant + 当前 user → provider 校验成功后原子提交一个完整短期回合。

长期只允许 `game_alias`、`preferred_language`、`reply_style`、`favorite_cyber_town_topic`；topic 仅接受冻结的中英文 Cyber Town 低敏感话题许可词汇，而非开放文本加禁止词黑名单。conversation/request/trace 仅作为来源，不影响同 player/NPC 跨 conversation 与服务重启召回。更新保持 `memory_id` 并递增 version，遗忘清空事实正文；同一 `(player_id, npc_id)` 的所有 conversation 都必须按 NFKC/casefold 清除含旧值的完整短期 user/assistant 回合，其他 player/NPC 不受影响。

总预算固定为 8192 估算单位：请求结构开销 64、每条消息开销 16、UTF-8 正文字节，并固定预留回复 256；长期事实最多占 2048。该工程估算不等于模型官方真实 token 统计；必须保留唯一 persona system 与当前 user，长期事实按整条裁剪，短期历史按最新完整回合优先选择、发送时按从旧到新排序，不允许半回合。

只有 `completed` 且公开响应验证通过的逻辑请求可以写入；degraded/local-fallback、422/502/503/504、取消、孤儿或晚到结果均不生成伪记忆。长期事实更新/遗忘递增所属双元 scope 代次：旧在途 provider 结果 fail-closed，已完成旧回复 replay 返回 409，不泄漏旧值也不重复调用；已持久化 Remember/Forget operation 在服务重启后 replay 不得误递增代次、清理有效历史或中断合法请求。同 ID 不同 payload 仍为 409，其他 owner 的有效缓存不受影响。超过 128 个会话时先清理过期会话，再淘汰没有在途工作的确定性 LRU；在途满载必须 fail-closed。

长期记录已包含 `memory_id`、双元 scope、来源 conversation/request/trace、importance、confidence、到期时间、version 与 status；SQLite operation/event 表只保留事务和无正文事件。正式业务路径锁定为 `data/cyber-town.sqlite3`，当前仍未创建；自动化只使用 pytest `tmp_path`，专项授权的 Step 5 真实评估和 Step 7 用户 UAT 分别使用 Git 忽略的 `data/uat/f-005/step-5-real-20260825/cyber-town.sqlite3`、`data/uat/f-005/step-7-user-20260825/cyber-town.sqlite3`，并共享 metadata-only 调用台账 `data/acceptance-ledgers/f-005.sqlite3`。

## Qdrant 启用门槛

F-005 已以固定 72 项 fake-only golden set 比较纯短期基线与结构化长期检索；precision/recall 均为 1.00，跨 scope 泄漏、遗忘后召回、过期召回、旧值复活与空结果虚构均为 0。Qdrant、embedding、SQLite FTS 和第二状态真相源不进入本任务；只有后续独立任务证明规则优化后仍有明确召回缺口，并满足隔离、删除一致性、延迟、费用与隐私门槛，才可重新评估。
