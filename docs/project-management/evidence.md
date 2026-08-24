# 启动阶段证据索引

| 验证项 | 方法 | 结果 | 未覆盖范围 |
| --- | --- | --- | --- |
| 目标路径安全性 | 检查 `E:\\Agent\\comprehensive-cases`、目标目录与同级旅行助手 | 目标目录原不存在；已新建独立兄弟目录；旅行助手未修改 | 未对旅行助手内容做无关读取 |
| Git 事实 | `git -C E:\\Agent\\comprehensive-cases rev-parse --show-toplevel` | 父目录不是 Git 仓库；新项目未初始化 Git | 后续仓库初始化、远程与 CI 未授权且未执行 |
| 参考文章与源码结构 | 阅读 HelloAgents 第十五章及其 GitHub 目录 | 文章/源码采用 Godot 项目 + FastAPI backend；包含 SimpleAgent、记忆、好感度、日志 | 未下载、复制或运行文章源码 |
| 技术时效性 | 查阅 Godot、FastAPI、DeepSeek、Qdrant 官方文档 | 见 `docs/tech-stack.md` 的带链接审查结论 | 未安装依赖、未调用 API、未启动服务 |
| 文档安全 | 人工检查本次新增的 `.env.example` 与 `.gitignore` | 无真实凭证；运行期数据、日志和 `.env` 被忽略 | 后续提交前仍需敏感信息扫描 |
| roadmap 人工门禁 | 用户在 2026-08-24 明确回复“确认 roadmap，然后按照优先级起草任务卡” | roadmap 已批准；按 P0 选择 `R-01`，起草 `F-001` | 该门禁当时不包含 `F-001` 实现授权；后续审批见下一行 |
| F-001 审批门禁 | 用户在 2026-08-24 明确批准任务卡并允许进入 Step 0 | `F-001` 已批准；仅执行 Step 0 | Step 1 未获授权 |
| Step 0 工具核对 | 只读执行版本/路径检查；不输出 Git 身份值 | Git 2.49.0、uv 0.6.14 可用；稳定 Python 路径缺失；仅 3.11.0rc2 可启动 | 未下载解释器、未安装依赖、未初始化 Git |
| Step 0 技术锁定 | 对照任务卡固定可替换且可验证的工程边界 | Python 3.12 + uv + root pyproject/uv.lock + Hatchling + backend/src + Pydantic v2 + 派生 schema + Python 质量入口 | 需在 Step 1 通过真实环境和失败测试验证 |
