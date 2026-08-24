# Cyber Town

一个用于系统学习 Agent 工程的 AI NPC 赛博小镇项目。目标是在 Godot 场景中让玩家与具备角色、记忆和可审计行为边界的 NPC 交互。

`F-001 工程与契约基线` 已由 PR #1 交付归档。当前活动任务是 `F-002 Godot—FastAPI 最小连通`；Step 6 用户 UAT 与最终本地交付审查已通过，状态为 `ready_for_git_delivery`，等待另行授权 Git 交付。项目仍没有对话 API、LLM、数据库或 NPC 业务能力，也未进入 R-03。项目规则与当前事实见 [AGENTS.md](AGENTS.md) 和 [docs/README.md](docs/README.md)。

当前统一验证命令：`uv run --frozen python scripts/quality.py`。它执行 Git ignore/敏感信息预检、lock、ruff、mypy、schema、Godot 导入与单测、真实 loopback 连通/失败恢复、pytest 和最终策略复检；不需要 API key 或业务外部服务。需要 Godot 4.7.2，可通过 `CYBER_TOWN_GODOT` 指向 executable；Windows 默认也会检查本项目批准的便携路径。

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

`.github/workflows/quality.yml` 在 `main` push、pull request 和人工触发时运行同一入口。workflow 只有 `contents: read` 权限，不引用 secrets、不持久化 checkout 凭证、不启动服务容器，也不调用 LLM、数据库或生产服务。runner 从公开发行源取得 action、uv、Python、锁定依赖和经 SHA-256 固定的 Godot 4.7.2 Standard Linux 包；所有集成流量仅在 runner 的 `127.0.0.1:8000` 内发生。F-002 尚未触发远程 CI。

R-03 的单 NPC 真实对话仍是下一候选价值切片；F-002 完成独立 QA、用户 Godot UAT、Git/PR/CI 和归档前不得进入。
