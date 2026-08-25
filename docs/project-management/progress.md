# 项目进度

## 当前状态

- 生命周期：`F-003 / ready_for_git_delivery`。
- 当前能力：保留 F-002 健康诊断，并新增固定 NPC `neon_guide / Nia`、冻结 persona、`POST /api/v1/dialogue`、独立 Godot 对话场景、隔离 DeepSeek adapter、脱敏 audit 和进程内幂等。
- Step 5 真实验收：1 次 smoke + 12 项 persona 评估全部通过，最后一项复用 Godot → FastAPI → DeepSeek 真实端到端；rubric 12/12，该专项共 13/15 次请求、1770 输入 token、809 输出 token，官方峰值费用上界 USD 0.00184668 / USD 0.05；该统计不包含后续用户 UAT。
- Step 6 修复：首轮 3 项 P1、6 项 P2，以及复审新增的同类畸形 SDK `choices` P2 均已补充失败优先负例并修复；覆盖 dotenv/key 隔离、SDK DEBUG 隐私、冻结参数、model/usage/choices、幂等回收、重复 JSON、Godot HTTP 边界和 fake 对话集成。
- 独立 QA：后端 reviewer 为 `P0/P1/P2/P3 = 0`、197 passed；Godot/API reviewer 为 `P0/P1/P2 = 0`、58 passed；额外 19 个首轮问题专项和 14 个畸形 SDK 响应独立复验均通过。
- 当前全量门禁：pytest 262 passed；lock 45 packages、mypy 35 source files、ruff、schema、Godot import/unit、9 个 F-002 loopback、8 个 F-003 fake loopback、ignore、sensitive 和 `git diff --check` 均通过。
- 用户 UAT：用户明确返回 `UAT_RESULT=PASS`、`PORT_8000_STOPPED=YES`；真实成功回复、503/504/502 失败与手动 Retry 恢复、提示注入边界和发送期间按钮禁用均通过。用户未单独提供 UAT 真实调用次数及新增费用，不推算总量；最终 Codex 门禁零真实模型调用。
- 配置边界：本地 `.env` 已被 Git 忽略，provider 默认 disabled；真实 provider 仅在明确授权的验收进程中启用，未暴露或提交 key，未修改系统代理配置。
- 交付边界：F-001/F-002 已分别由 PR #1/#2 完成交付；F-003 仍在本地未提交功能分支，独立 QA、用户 UAT 和最终本地门禁已通过，但尚未执行远程 CI、Git 交付或归档。
- 未实现：数据库、对话历史/记忆、多 NPC、正式素材和 R-04 均不在当前范围。

## 下一批准动作

等待用户单独批准 F-003 Git 交付；获得授权前不执行 add、commit、push、PR、远程 CI、合并或归档，也不进入 R-04。
