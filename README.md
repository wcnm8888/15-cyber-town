# Cyber Town

一个用于系统学习 Agent 工程的 AI NPC 赛博小镇项目。目标是在 Godot 场景中让玩家与具备角色、记忆和可审计行为边界的 NPC 交互。

当前正在执行 `F-001 工程与契约基线`，状态为 `remote_ci_passed_awaiting_pr_merge`：用户 UAT、最终独立审查、本地交付门禁和本地提交均已完成；私有远程仓库、`origin`、远程 `main`/功能分支和 PR #1 已建立，GitHub Actions `Quality` 已通过。本地工程、安全配置、strict Pydantic v1 对话契约、三个派生 JSON Schema、统一离线质量门禁和最小 CI 已建立。尚未合并 PR、归档 F-001 或进入 R-02，也尚无 API、Godot、LLM 或数据库能力。项目规则与当前事实见 [AGENTS.md](AGENTS.md) 和 [docs/README.md](docs/README.md)。

当前统一验证命令：`uv run --frozen python scripts/quality.py`。它先执行 Git ignore 与敏感信息预检，再执行 lock freshness、ruff、mypy、schema drift 和 pytest，最后复查安全策略；不需要 API key 或业务外部服务。

## 本地验证

项目要求稳定 Python 3.12.10 和 `uv 0.6.14`。在仓库根目录执行：

```powershell
uv sync --locked --all-groups
uv run --frozen python scripts/quality.py
```

## CI 边界

`.github/workflows/quality.yml` 在 `main` push、pull request 和人工触发时运行同一组命令。workflow 只有 `contents: read` 权限，不引用 secrets、不持久化 checkout 凭证、不启动服务容器，也不调用 LLM、数据库或其他应用服务。runner 从公开发行源取得 action、uv、Python 和锁定依赖；质量门禁本身不访问业务外部服务。CI 使用 `uv sync --locked` 拒绝陈旧锁文件。PR #1 已提供 GitHub-hosted Linux runner 通过证据。

首个候选端到端切片是“最小 Godot 场景中的玩家—单 NPC 一次真实对话，具备角色一致性、后端审计轨迹及自动/人工验证”。当前先完成其前置工程基线；任何任务都须在对应任务卡获批准后才能实施。
