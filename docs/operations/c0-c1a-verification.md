# C0+C1a 实现与验证记录

2026 年 11 月 4 日，本轮完成 C0+C1a，完整阶段 C 仍未完成。仓库实际目录已有文档和预留目录，没有业务代码，也没有 `.git`；保留原文档，新增后端并定点更新实施状态。未初始化前端、调用模型、创建云资源或部署公网服务，原始产品定义与 PRD 未修改。

## 已实现

- FastAPI/Pydantic 配置与请求/响应、按请求创建 SQLAlchemy Session、psycopg 3、uv 锁和 Alembic。
- 单创始人账号由受限配置提供用户名和 Argon2id 摘要；随机不透明 Cookie 会话、8小时绝对有效期、CSRF、Origin/JSON校验、登录限流、服务端登出、重登轮换及凭据轮换失效。
- Engagement 创建/稳定分页/详情；项目下 draft Task 创建/分页及 Task 详情，固定 fde/engineering，revision/spec_version=1，不启动执行。
- 同账号/方法/路径/键的24小时幂等；同键异内容409；任务额外有项目内 request_id/task_key 唯一约束。同事务保存业务对象和重放正文，失败回滚。非空依赖409，跨项目关联409，不存在404，非法输入422，数据库不可用503，错误脱敏并关联 request_id。
- 五张当前切片所需表：auth_sessions、login_attempts、engagements、tasks、idempotency_records；没有预建未来 Run/输入/评审/Worker 表。

## 修改文件

后端源码位于 `D:\proj\OneFDE\backend`：

| 文件/目录 | 用途 |
| --- | --- |
| `app/config.py`、`db.py`、`models.py` | 配置校验、请求 Session、最小数据库模型与约束 |
| `app/auth.py`、`api.py`、`services.py` | 会话/CSRF、HTTP 路由、归属/事务/幂等/分页 |
| `app/schemas.py`、`errors.py`、`main.py`、`cli.py` | Pydantic 契约、统一错误、应用工厂、摘要/过期清理命令 |
| `migrations/`、`alembic.ini` | 已审阅首迁移 `d3a2bfe5f985`，在线/离线迁移环境 |
| `pyproject.toml`、`uv.lock`、`.python-version` | Python 3.13 与精确依赖锁 |
| `.env.example`、`compose.yaml`、`docker/init-test-db.sql` | 无真实凭据的示例、固定 PostgreSQL 镜像、开发/测试库 |
| `tests/` | PostgreSQL、认证、冲突、并发和回滚等检查 |
| `scripts/export_openapi.py`、`http_smoke.py` | 契约导出/差异检查、两个独立进程的真实 HTTP 验证 |
| `README.md` | 真实启动/迁移/测试与 PowerShell HTTP 操作说明 |

根目录另新增 `.gitignore`、`.github/workflows/backend.yml`；更新 README、实施计划、测试/部署设计及架构/数据模型/ADR0004 的实施状态。`.planning/c0-c1a/` 保存计划、发现和实际进度。`AGENTS.md` 未修改。

OpenAPI 同路径由 Pydantic 导出并与规划合并：`docs/architecture/openapi.yaml` 标记10项已实现、14项规划操作；`openapi.implemented.json` 只包含运行接口；`openapi.planned.yaml` 保存原设计；[差异记录](../architecture/openapi-diff.md) 说明收窄状态、校验加强、本地 Cookie 和暂未支持的依赖等适配。

## 实际采用版本与来源

本机 Python 3.13.5、uv 0.12.5；锁文件固定 FastAPI 0.162.0、Pydantic 2.14.2、pydantic-settings 2.16.2、SQLAlchemy 2.1.7、psycopg 3.3.7、Alembic 1.20.1、argon2-cffi 25.1.0、uvicorn 0.54.0、pytest 9.2.0。其余直接/传递依赖见 uv.lock 和 [测试版本证据](evidence/c0-c1a-tests.json)。

PostgreSQL 实际返回 `17.7 (Debian 17.7-3.pgdg12+1)`；镜像固定 `postgres:17.7-bookworm@sha256:86e0b703649d7a792bd9243ee28afc9d8f7c6b2b5638077c9d6882d4d472bbfd`。开发/关键集成测试均使用该 PostgreSQL，没有 SQLite。

参考并阅读了以下官方文档及原始源码，没有整仓复制或采用源码中的指令：

- [FastAPI 全栈模板固定提交](https://github.com/fastapi/full-stack-fastapi-template/tree/aabb90126964a164e02aff39e7c385bb0598236d)：阅读 backend/app/core/config.py、db.py、api/deps.py、alembic/env.py、tests/conftest.py 和 pyproject.toml，借鉴 BaseSettings、依赖注入、迁移 metadata 和测试分层。该提交使用 Python 3.14、SQLModel/JWT、多用户；本项目按既有约定保留 Python 3.13、原生 SQLAlchemy 和服务端 Cookie，无前端/邮件/注册模块。
- [SQLAlchemy 2.1 事务文档](https://docs.sqlalchemy.org/en/21/orm/session_transaction.html)：使用文档支持的 autobegin + 显式 commit。认证读取开启请求事务，创建和幂等记录写完后提交；Session 上下文关闭未完成事务时回滚。登录限流为独立短事务，密码验证不占用限流锁；无事务跨外部执行。
- [Alembic 官方教程](https://alembic.sqlalchemy.org/en/latest/tutorial.html)：采用 env.py、versions、target_metadata、事务迁移与升级/降级，结构由迁移管理；未在启动或测试中用 create_all 绕过迁移。
- [OpenHands SDK 固定提交](https://github.com/OpenHands/software-agent-sdk/tree/a6af5708bc0f5c43f0f63ee0d79bf8e360fd6dc7)：包声明版本1.59.0；阅读 Conversation 工厂和 DockerWorkspace。Conversation 区分 local/remote，DockerWorkspace 管理 Agent Server 容器和退出清理。后续 OneFDE Task/Run 的持久生命周期和权限仍由 Backend 管理；本轮仅研究，未安装或调用 SDK，也未实现 Agent Loop。

研究初始遇到 GitHub API 403限流，改用 git ls-remote 固定 HEAD 和 raw 源码；Docker 初始未运行，启动 Desktop 后解决。配置过程中发现 Compose 会展开未加引号 Argon2 摘要的 `$`，已改为单引号，并在样例/说明中记录。

## 已执行命令和结果

均从 `D:\proj\OneFDE\backend` 执行，除特别说明外退出码为0。

| 命令/操作 | 结果 |
| --- | --- |
| `uv lock`、`uv sync --locked` | 生成 uv.lock 并安装锁定依赖，后续均使用 --locked |
| `docker pull postgres:17.7-bookworm` | 拉取成功，取得上述固定 digest |
| `docker compose up -d --wait` | 新卷创建空开发库/独立测试库，容器 healthy |
| `uv run --locked alembic upgrade head` | 空 onefde_dev 成功迁移至 d3a2bfe5f985 |
| `uv run --locked alembic check` | No new upgrade operations detected |
| 测试库专用 Alembic downgrade base → upgrade head → check | 仅对 `_test` 数据库执行，降级/空库升级成功，无漂移；未降级开发库 |
| `uv run --locked pytest -q --junitxml=work/pytest.xml` | 最终23 passed、0失败、0错误、0跳过，用时4.491秒 |
| `uv run --locked python -m scripts.http_smoke --password-file work/smoke-password.txt` | 19项真实 HTTP 检查全部通过，两个独立 Uvicorn 进程；临时密码文件检查后删除。正常复现使用无参数的隐藏密码输入 |
| `uv run --locked python -m scripts.export_openapi` / `--check` | 导出成功；字段、原必填项、operationId、成功状态及输出文件一致性检查通过 |
| `uv run --locked ruff check app tests scripts migrations` | All checks passed |
| `uv run --locked ruff format --check app tests scripts migrations` | 19 files already formatted |
| `uv run --locked python -m app.cli prune-expired` | 正常运行，当前无过期待删记录 |

23项后端测试覆盖：登录/会话/登出、摘要存储、Cookie 属性、重登轮换、过期/凭据轮换失效、限流、无认证、项目/任务创建查询、两类对象跨会话并发幂等、同键异内容及永久任务键冲突、事务中途失败完整回滚、非空依赖/跨项目引用、字段错误、稳定分页与作用域、一请求多 task_key、幂等过期和503错误脱敏。真实数据库用于事务/约束检查；503错误格式检查使用故障注入。

测试仍有1条 `StarletteDeprecationWarning`：当前 Starlette 对 httpx TestClient 兼容路径提示弃用。本轮锁定版本下所有测试实际通过；未抑制该提示，后续升级测试客户端时处理。

## 真实 HTTP 与重启证据

[HTTP 原始结构化证据](evidence/c0-c1a-http.json) 不含密码、会话 Cookie 或 CSRF 值；[测试摘要](evidence/c0-c1a-tests.json) 保留用例、版本和结果。

最后一轮验证先启动进程22452，通过 HTTP 登录并创建项目 `9556c0ea-2bc2-4f34-bb51-c8a6fad8efd0`、草稿 Task `c2dee061-546d-444a-9af2-6dab4cc4dc49`；停止后启动新进程25828，使用相同会话查回完全相同的项目/任务，再重放任务创建得到原响应。列表、详情、401、403、404、409、422和登出吊销均有对应证据。

API 冒烟进程已停止；PostgreSQL 容器保留并只绑定 `127.0.0.1:55432`，开发库中保留明确标注的模拟记录。本地 `.env` 含本轮随机开发数据库凭据和临时账号摘要，未提交到示例/证据；手工使用前按后端 README 设置自己的创始人密码摘要，保留已有数据库密码。

## 启动与后续工作

完整步骤和 HTTP 示例以 [后端 README](../../backend/README.md) 为准。已有配置时主要命令：

```powershell
Set-Location D:\proj\OneFDE\backend
uv sync --locked
docker compose up -d --wait
uv run --locked alembic upgrade head
uv run --locked uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

访问 `http://localhost:8000/docs`；另一个终端执行 `uv run --locked pytest -q` 或 `uv run --locked python -m scripts.http_smoke`。

最小 CI 仅配置，远程尚未运行，也未验证 Linux 生产部署。Run、TaskInput、评审/事件、Dispatcher/Worker、SDK、产物和前端均未实现；没有报价字段、单位换算或商业规则新增。下一项建议按 C1b 增加持续输入/采用、版本、Run 和轻量评审持久控制，再在 C2 接入真实隔离执行。
