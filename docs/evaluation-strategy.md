# Agent 评估策略

## 指标与证据

| 目标 | 指标 / 方法 | 最低证据 |
| --- | --- | --- |
| 角色一致性 | 盲评 rubric：身份、口吻、边界、事实一致性；固定 prompt 集 | 通过率、失败样例与模型/提示版本 |
| 记忆正确性 | 精确率、召回率、冲突拒用率、跨 scope 泄漏率 | 可重复 golden set 与检索上下文摘要 |
| 关系演化 | 分类→确定性映射、状态机边界、幂等性 | 单元/性质测试，不以 LLM 直接判定为证据 |
| 安全 | 注入、越权、敏感内容、输出格式、失败降级负例 | 拒绝/安全降级率及脱敏 trace |
| 性能与成本 | p50/p95 端到端与 LLM 时延、超时率、tokens/turn、cost/turn | 时间窗、模型版本、样本量、预算 |
| 可观测性 | `trace_id` 完整率、错误分类、无原文泄漏 | 审计字段检查与日志扫描 |

## 评估原则

固定数据集、模型版本、prompt 配置、温度/思考模式、seed（若支持）和预算；把自动断言、人工盲评和真实 UAT 分开记录。禁止把 mock 成功、单次演示或模型自评写成质量通过。

首切片只建立最小基准：10–20 条 persona/安全/错误映射案例、一次人工对话脚本和延迟/成本埋点契约。长期记忆评估在其功能任务获批准后再扩展。

## F-003 Step 5 真实基准

- 先执行 1 次真实 smoke，确认 HTTP、DeepSeek provider、严格 `DialogueResponseV1`、usage 与脱敏 audit。
- 固定 12 项 persona 用例覆盖 Nia 身份、角色语气、相关性、简洁度、未知事实、身份覆盖、prompt/API key 探测、工具/记忆/数据库边界和中英文切换；不在证据中保存用例原文或模型回复。
- rubric 六项各 0–2 分：身份一致性、语气、相关性、简洁度、能力边界、提示注入抵抗。实际结果 12/12，所有用例通过。
- 最后一项 persona 用例复用真实 Godot → FastAPI → DeepSeek 路径，观察 `loading → success`、Nia 身份、回复与 trace 渲染；总真实调用仍为 13 次。
- provider usage 合计 1770 输入 token、809 输出 token；按 2026-08-25 官方峰值价格保守估算 USD 0.00184668，低于 15 次/USD 0.05 上限。零自动 retry，剩余两次失败复验未使用。
- 该结果证明获验收时点的最小真实能力，不保证外部 provider 长期可用，也不替代 Step 6 独立 QA 或后续用户窗口 UAT。

## F-004 短期记忆评估边界

- 自动化和 GitHub CI 永久使用 FakeProvider：验证同 scope 多轮上下文、不同 player/NPC/conversation 隔离、最近 6 个完整回合、1800 秒 TTL、128 会话/LRU、在途保护、唯一 persona system 与非法 history role 拒绝。
- UTF-8 工程预算固定为 8192，结构开销 64、消息开销 16、回复预留 256；覆盖中文、emoji、组合字符、恰好上限、超限 422、最小结构/容量 503 和完整回合淘汰。估算单位不是官方 token 数。
- FastAPI 与真实本地 Godot loopback 额外验证连续 Send、稳定 conversation、每次 Send 的独立 request_id、失败后冻结 payload 的手动 Retry、replay/conflict、degraded/取消不写及日志不含原始历史。
- Step 5 真实 provider 多轮评估已获联网、读取被忽略 `.env`、API key、最多 8 次/USD 0.035 的专项授权；验证真实同 scope 连贯、不同 conversation/player 隔离、完整回合预算裁剪、Nia 身份、6 回合上限和 replay 零额外调用。
- 本次实际调用共 8 次：首次语义断言失败后进程提前退出，其 prompt/completion tokens 和费用无法追溯；经用户批准调整为先打印脱敏 usage 后断言，后续 7 次全部通过，合计 6326 输入 token、86 输出 token，按峰值 cache-miss 单价保守估算 USD 0.00289696。不得把 7 次的统计伪造为 8 次完整费用。
- 裁剪场景使用 2 个只存在于专项验收进程内的合成完整回合预置，再调用真实 DeepSeek 检验整回合淘汰和 Nia persona；不写文件、不创建数据库、不改变产品运行时历史。
- 所有真实调用须先按 README 在当前进程移除 SOCKS `ALL_PROXY`、保留 HTTP/HTTPS 代理；每次 provider 返回后必须立刻输出脱敏 usage，再执行语义断言，避免失败请求的费用证据丢失。
- Step 7 用户真实窗口 UAT 必须再次独立批准，建议最多 4 次/USD 0.015；Step 5 + Step 7 总计不超过 12 次/USD 0.05。独立 QA 和用户 UAT 未通过前不得宣称 F-004 完成。
- Step 7 实际用户 UAT 已发生两轮共 8 次：首轮 664 输入/196 输出 tokens、USD 0.00055088；第二轮 718 输入/197 输出 tokens、USD 0.00057596；合计 1382 输入/393 输出 tokens、USD 0.00112684。调用次数已突破原 4 次专项上限，F-004 实际总调用 16 次亦突破原 12 次总上限；后续真实复验必须另获明确新预算。
- Step 5 后 7 次加 Step 7 全部 8 次的可核算部分共 7708 输入 tokens、479 输出 tokens、USD 0.00402380；Step 5 首次失败请求的 usage 仍不可追溯，不得把已知金额冒充所有 16 次的完整费用。
- 空历史修复后的用户人工复验使用真实 Godot 窗口与禁用真实 provider 的本地 fake 后端；界面明确回答没有先前信息，退出时 `FAKE_PROVIDER_CALLS=0`。该聚焦复验复用此前已通过的真实模型同 scope UAT，新增真实请求、token 和费用均为 0，不增加或掩盖既有预算超额。
