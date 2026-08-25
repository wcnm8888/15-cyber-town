# Cyber Town

一个用于系统学习 Agent 工程的 AI NPC 赛博小镇项目。目标是在 Godot 场景中让玩家与具备角色、记忆和可审计行为边界的 NPC 交互。

`F-001` 与 `F-002` 已分别由 PR #1、PR #2 交付归档。当前活动任务是 `F-003 单 NPC 角色化真实对话`：真实 smoke、12 项 persona 评估、真实端到端、修复后的独立 QA、用户真实窗口 UAT 和 fake-only 最终本地门禁均已通过，状态为 `ready_for_git_delivery`。Git 交付和归档尚未开始。项目仍没有数据库、记忆、多 NPC 或 R-04 能力。项目规则与当前事实见 [AGENTS.md](AGENTS.md) 和 [docs/README.md](docs/README.md)。

当前统一验证命令：`uv run --frozen python scripts/quality.py`。它执行 Git ignore/敏感信息预检、lock、ruff、mypy、schema、Godot 导入与单测、9 个 F-002 健康 loopback、8 个 F-003 对话 fake loopback、pytest 和最终策略复检。每个质量子进程强制禁用 `.env`、剔除继承的 provider key 并固定 `LLM_PROVIDER=disabled`；对话集成仅使用本地 FastAPI 和 fake provider。需要 Godot 4.7.2，可通过 `CYBER_TOWN_GODOT` 指向 executable；Windows 默认也会检查本项目批准的便携路径。

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

`.github/workflows/quality.yml` 在 `main` push、pull request 和人工触发时运行同一入口。workflow 只有 `contents: read` 权限，不引用 secrets、不持久化 checkout 凭证、不启动服务容器，也不调用 LLM、数据库或生产服务。runner 从公开发行源取得 action、uv、Python、锁定依赖和经 SHA-256 固定的 Godot 4.7.2 Standard Linux 包；所有集成流量仅在 runner 的 `127.0.0.1:8000` 内发生。F-002 的远程交付与最终 CI 事实由 PR #2 记录。

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

F-003 已完成 Step 7，用户真实窗口 UAT 和最终本地交付审查均通过；Git 操作、归档、额外真实模型调用和 R-04 仍需相应明确授权。
