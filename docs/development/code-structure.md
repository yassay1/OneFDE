# 后端代码组织

本规范描述已落地的模块单体及C2扩展。业务行为以PRD/数据模型为准；HTTP字段以Pydantic导出为准。此前结构重构保持C1b行为，见 [重构记录](../operations/structure-refactor-verification.md)；之后C2独立新增Worker和SDK边界，实际范围与阻塞见 [C2验证](../operations/c2-verification.md)。

## 查找代码

Python应用为`backend/src/onefde`，通过`uv sync --locked`可编辑安装。项目名称仍为onefde-backend，应用版本仍为0.1.0。构建后端固定uv_build==0.12.5，应用依赖版本未升级。

| 位置 | 职责 |
| --- | --- |
| `bootstrap.py` | 应用工厂、配置、连接池、路由和错误处理装配 |
| `entrypoints/api.py` | ASGI工厂入口；启动路径`onefde.entrypoints.api:create_app` |
| `entrypoints/cli.py` | 原密码摘要/过期记录清理命令 |
| `entrypoints/worker.py`、`worker/` | C2独立进程装配、私有配置、短事务/心跳/执行编排；不放领域状态规则 |
| `core/` | 配置、业务异常、安全摘要、时钟、通用Pydantic结构；不导入业务模块或HTTP/ORM |
| `infrastructure/db/` | SQLAlchemy Base/Engine、通用游标分页、供Alembic使用的模型注册汇总 |
| `infrastructure/idempotency.py` | HTTP幂等记录和原有提交边界，无业务模块导入 |
| `infrastructure/web/` | 共享请求Session/参数依赖和统一HTTP错误转换 |
| `core/execution.py`、`core/engineering.py`、`infrastructure/runtime/` | 执行端口、纯检查派生/角色修订，及OpenHands适配（上下文/结果契约/固定验证）；SDK不进入业务模块 |
| `infrastructure/artifacts.py` | 私有不可变本地blob与摘要校验；没有S3/下载能力 |
| `modules/auth/` | 会话/账号模型与契约、认证服务、HTTP依赖和Cookie响应 |
| `modules/engagements/` | 项目模型、契约、查询、创建服务和路由 |
| `modules/tasks/` | Task/Input/版本/Run/评审及相关元数据；对外命令入口`service.py`，查询入口`queries.py` |
| `modules/fde/` | P1薄FDE受控工具与项目交付详情聚合；调用tasks/engagements公开服务，不认领Worker作业、不接SDK |
| `modules/business/` | 客户会话和待办、规则路由、复试与候选。FDE 接单经现有 Task 服务，路由持有事务边界 |
| `modules/knowledge/` | P3文件型能力库检索、权限过滤、Business交接；不接向量库/模型，不派发工程 |
| `modules/dialogue/` | 四个员工的问答记录。读取 Business、FDE、Task 和 Knowledge 的公开查询，不反向让 FDE 依赖 Knowledge。替身在 `infrastructure/runtime/staff_chat.py`，默认不访问模型 |
| `modules/tasks/commands/` | tasks、inputs、runs、reviews四组写用例；不接HTTP对象，不自行commit/rollback |
| `modules/tasks/dispatch.py`、`configuration.py` | C2作业认领/租约/回填规则、不可变模型配置供给；调用方提交，未实现外部执行 |
| `modules/tasks/policies.py` | 原有状态、版本、依赖等规则，函数语义保持不变 |
| `modules/tasks/locking.py`、`events.py`、`versions.py`等 | 事务内锁、事件、版本及输入/产物辅助，供命令复用 |
| `migrations/` | 链尾 `a7c4e1b90d22`。顺序：C0+C1a `d3a2bfe5f985`、C1b `4bf8db3c4ef3`、C2 `d5454eda0523`、Business 会话 `f3afd81339dd`、报价售后 `71e7bc20e982`、复用验证 `b91f643af772`、FDE Agent `ce99d539d71a`、Business Agent `f2ee3d9000b1`、员工对话 `a7c4e1b90d22`。`env.py` 从安装包汇总 metadata |
| `tests/support/` | 测试数据工厂、常量、ORM汇总及确定性控制适配 |
| `tests/integration/` | 原数据库/API/事务/迁移测试和独立PostgreSQL fixture |
| `tests/unit/` | 内部结果/私有文件/配置/停止边界；SDK绑定用真实SDK类型和资源替身，不调用模型 |
| `tests/architecture/` | 依赖方向、循环、提交归属、包安装、测试辅助和运行契约检查 |
| `tests/e2e/` | 原19/35项HTTP进程场景；新增scripts.c2_smoke使用真实控制器+明确模拟执行 |
| `scripts/` | 开发检查入口与OpenAPI导出；生产包不导入它们 |

小模块保持router/schemas/models/service；任务模块因实际职责较多进一步拆分。当前Run、输入和评审仍围绕Task保持同事务一致性，不因表名不同创建独立服务。Worker只通过公开服务入口操作控制状态；SDK/文件实现留在基础设施，通过core执行端口返回事实。本地真实模型记录见 [测试与验收](../operations/testing.md)。私有文件已可测试，不表示已接对象存储。

## 依赖与事务

- 入口装配模块，HTTP路由调用公开服务/查询；业务命令不导入路由、FastAPI或入口模块。
- core保持向内依赖；基础设施不反向导入业务。`db/metadata.py`是明确的模型注册装配例外，业务模块不导入它。
- auth不依赖项目/任务；engagements不依赖tasks；tasks可调用项目查询校验归属。跨模块写入通过公开服务入口，模型外键使用SQLAlchemy表名引用。
- 一个Task命令由调用方持有Session与提交边界。原HTTP幂等包装负责业务变更/事件/响应记录同事务提交；内部结果服务仍由受控调用方提交。登录限流与会话原有短事务不变。
- 不使用函数内部导入规避循环。CLI中的按命令加载用于保持密码摘要命令无需读取数据库配置；不是业务模块互相引用。
- 测试模块共享辅助只从tests/support导入，conftest提供fixture，不作为普通工具模块被导入。
- Worker不跨外部执行持有Session，不与心跳线程共享Session。每次认领、心跳、资源登记和结果回填独立短事务；SDK回调只走受信任资源/结果端口，业务模块不能反向导入Worker或SDK。租约过期冻结，不自动重新执行。

以上规则由`tests/architecture/test_dependencies.py`执行，随完整测试进入CI。C2沿用该边界新增实际Worker/SDK文件，没有新增Repository基类、命令总线、事件总线或空的未来模块。专用节点配置/Worker启动见 [Worker手册](../../backend/WORKER.md)。

## 常用命令

从`backend`执行：

```powershell
uv sync --locked
uv run --locked uvicorn onefde.entrypoints.api:create_app --factory --host 127.0.0.1 --port 8000
uv run --locked python -m onefde.entrypoints.cli hash-password
uv run --locked alembic upgrade head
uv run --locked alembic check
uv run --locked pytest -q
uv run --locked pytest tests/unit tests/architecture -q
uv run --locked python -m scripts.http_smoke
uv run --locked python -m scripts.c1b_smoke
uv run --locked python -m scripts.export_openapi --check
uv run --locked ruff check src tests scripts migrations
uv build --out-dir work/dist
```

完整配置和 HTTP 示例见 [后端README](../../backend/README.md)。旧 `app.main` / `app.cli` 导入路径已迁移。结构重构当时保持 HTTP 地址、字段、状态码和 Cookie 策略。当前迁移链尾以本文件的迁移表为准，当前启动和检查命令以本文件和后端 README 为准。历史验证文档保留当时命令。

报价售后自动协作入口为 `entrypoints/quote_support.py`，负责本地运行、事务装配和测试入口核验。`modules/fde/quote_support.py` 通过 Case 和 Task 服务推进固定模板。工程认领守卫由 Worker 装配，Dispatcher 保持派发归属。

通用 FDE 的模型循环由 `entrypoints/fde_agent.py` 装配。`modules/fde/agent_work.py` 负责工作范围、租约和授权，`agent_tools.py` 校验并调用现有业务命令。Business 模型循环入口是 `entrypoints/business_agent.py`。复用交付入口是 `entrypoints/reuse_delivery.py`。兼容传输留在基础设施。工程归档和 Run 装配只在 `modules/tasks/assembly.py`；测试直接导入该模块。
