# Cyber Town

一个用于系统学习 Agent 工程的 AI NPC 赛博小镇项目。目标是在 Godot 场景中让玩家与具备角色、记忆和可审计行为边界的 NPC 交互。

`F-001`—`F-006` 已分别通过 PR #1—#6 完成交付和归档；F-006 已由 PR #6 squash merge 到 `main` / `origin/main` 的 `3c2059aad7ef5a1e9dd0154ad49d2b0e93f8f47f`。F-007 Step 7 已完成：固定视口两行回复裁切 `Reason` 的 P2 通过最小 Godot 布局修复关闭，Nia、Ivo、Rhea 的真实窗口 UAT 通过；Git 交付前又关闭关系 GET 未在持久化前拒绝未知 NPC 的 P1，最终统一门禁为 `1319 passed`。Git 交付已获授权并进行中。冻结的 Dialogue v1 JSON Schema 不变；全程 fake-only，不读取 `.env`、不调用真实模型。项目规则与当前事实见 [AGENTS.md](AGENTS.md) 和 [docs/README.md](docs/README.md)。

当前统一验证命令：`uv run --frozen python scripts/quality.py`。它执行 Git ignore/敏感信息预检、lock、ruff、mypy、schema、Godot 导入与单测、9 个 F-002 健康 loopback、10 个对话 fake loopback、1 个三 NPC 切换 loopback、pytest 和最终策略复检；对话场景包含连续多轮与失败后的手动 Retry 恢复。每个质量子进程强制禁用 `.env`、剔除继承的 provider key 并固定 `LLM_PROVIDER=disabled`；对话集成仅使用本地 FastAPI 和 fake provider。需要 Godot 4.7.2，可通过 `CYBER_TOWN_GODOT` 指向 executable；Windows 默认也会检查本项目批准的便携路径。

## 本地验证

项目要求稳定 Python 3.12.10 和 `uv 0.6.14`。在仓库根目录执行：

```powershell
uv sync --locked --all-groups
uv run --frozen python scripts/quality.py
```

## 本地诊断场景

先在仓库根目录启动后端：

```powershell
uv run --frozen python -m cyber_town.api
```

再开一个终端运行 Godot 主场景：

```powershell
E:\Agent.tools\godot\4.7.2\Godot_v4.7.2-stable_win64_console.exe --path game
```

默认请求 `GET http://127.0.0.1:8000/api/v1/health`，timeout 为 3 秒。场景只显示标题、连接状态和 Retry；失败后不自动重试。原生桌面客户端不需要 CORS。

## CI 边界

`.github/workflows/quality.yml` 在 `main` push、pull request 和人工触发时运行同一入口。workflow 只有 `contents: read` 权限，不引用 secrets、不持久化 checkout 凭证、不启动服务容器，也不访问真实 LLM、正式数据库或生产服务；F-005 的 SQLite 测试只使用隔离临时数据库。runner 从公开发行源取得 action、uv、Python、锁定依赖和经 SHA-256 固定的 Godot 4.7.2 Standard Linux 包；所有集成流量仅在 runner 的 `127.0.0.1:8000` 内发生。F-002 的远程交付与最终 CI 事实由 PR #2 记录。

## 本地对话场景

真实 provider 默认关闭，统一自动化与 CI 不读取真实 `.env`、不继承 provider key、不调用真实模型。只有取得明确外部调用授权后，才能在当前 PowerShell 进程启用本地 `.env` 中已被 Git 忽略的配置：

```powershell
$env:LLM_PROVIDER = 'deepseek'
[Environment]::SetEnvironmentVariable('ALL_PROXY', $null, 'Process')
uv run --frozen python -m cyber_town.api
```

清除当前进程的 `ALL_PROXY` 只用于规避本机 SOCKS 代理需要额外 `socksio` 的限制，不修改系统代理；既有 HTTP/HTTPS 代理保持不变。不要输出 `.env`、API key、玩家消息或模型回复。每个真实请求可能产生费用，SDK 不自动重试。

后端启动后，在另一个终端打开独立对话场景：

```powershell
& 'E:\Agent.tools\godot\4.7.2\Godot_v4.7.2-stable_win64_console.exe' --path game --scene res://scenes/dialogue.tscn
```

短期记忆每个 conversation scope 最多保留最近 6 个成功完整回合，最多 128 个活动会话，空闲 TTL 为 1800 秒；该层随服务重启丢失。F-005 长期层只允许 `game_alias`、`preferred_language`、`reply_style`、`favorite_cyber_town_topic` 四类明确授权的低敏感事实，使用 `(player_id, npc_id)` 与标准库 SQLite 保留、更新、过期和遗忘；自动测试只使用 pytest 隔离数据库。启用 provider 的常规启动会装配正式路径 `data/cyber-town.sqlite3`，且不自动接入验收调用台账；F-005 Step 7 用户 UAT 必须使用单独的隔离 SQLite 和 `MeteredAcceptanceProvider` 启动器，不得使用上面的普通启动命令。

上下文上限 8192 为 UTF-8 字节与固定开销的工程估算，不是 provider 官方 token 数；长期事实最多 2048，固定预留 256 回复单位，唯一 persona system 后只注入标记为不可信的事实及完整短期回合。没有可用记忆或已遗忘时返回确定性 `degraded / local-fallback`，不调用 provider、不计费。F-005 的真实评估最多 8 次/USD 0.035，用户 UAT 最多 4 次/USD 0.015；两个阶段都须单独授权，并由跨进程 SQLite 台账在调用前预留、provider 返回后先持久化脱敏 usage。
