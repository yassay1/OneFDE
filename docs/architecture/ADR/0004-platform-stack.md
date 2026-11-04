# 首版采用 Python 控制后端与 React 工作台

状态：纳入推荐技术基线；C0+C1b 持久控制后端已实施并本地验证，其余部分未实施。2026 年 11 月 4 日协作复核后保留技术组合。

## 问题与决定

OneFDE 是单创始人的内部工作台，需要持久任务状态和真实工程执行，首版没有 SEO、多租户或大规模并发需求。采用 React/TypeScript/Vite、Ant Design、React Router、TanStack Query；后端采用 Python 3.13、FastAPI/Pydantic 2、SQLAlchemy 2.1/psycopg 3/Alembic、PostgreSQL 17。Agent 使用 OpenHands SDK 内的 LiteLLM 接入，不另造 Agent loop。依赖精确版本在初始化时锁定，SDK 相关包作为兼容组合更新。

PostgreSQL 事务保存任务、Run 和 dispatch_jobs，独立 Worker 认领执行；首版一个活动工程 Run。界面 REST 短轮询，私有 S3 兼容存储保留产物，单账号 Cookie 会话认证。Linux/Compose/Caddy 管理控制服务，工程在专用执行节点；客户软件独立发布。

## 比较与代价

| 备选 | 本项目取舍 |
| --- | --- |
| Next.js 全栈 | 当前无 SSR 需求，且工程 SDK 为 Python；额外 Node 服务增加跨后端维护。选 SPA，明确补齐路由与服务端缓存 |
| 全 TypeScript 后端 | 单语言前端体验好，但 Python SDK 集成需增加另一服务或改换执行框架；本次优先减少 Agent 适配成本 |
| SQLite | 单进程简单，但业务 API 与 Worker 需共享任务认领及唯一性语义；采用与生产一致的 PostgreSQL |
| Redis/Celery 或工作流平台 | 有成熟调度能力，但当前串行切片不足以抵偿额外服务；数据库作业仍需自行处理租约、重复和状态不明，不能声称天然无故障 |
| WebSocket/SSE | 实时性好；当前约 2 秒任务刷新足够，先缩短实现路径 |
| LangGraph/自研 Harness | 有定制控制能力；当前直接使用 SDK 工具循环，将业务不变量留在程序 Coordinator |
| JWT/SSO/多租户 | 无当前需求；服务端会话简化吊销和单账号权限 |

## 后果与重访

这是开发默认方案，不是已安装或已实测声明。增加可维护的 PostgreSQL 作业处理责任；不把 FastAPI 进程内任务当持久调度。出现多实例、大量并发/定时任务或恢复运维负担时再比较专门队列；真正需要推送、多账号或 SSR 时分别重访。实际接入只做短冒烟，自有状态逻辑随开发检查。

用户提供的 TypeScript/Fastify、Redis/BullMQ 和独立 Python 工程服务可承载相同协作模型，但当前没有现成 TypeScript 后端或该语言团队约束。围绕已推荐 Python SDK 增加另一后端/协议边界不减少 MVP 工作，故不换栈；这不是要求所有未来组件必须同语言。持续 Task、输入、评审和事件可靠性不依赖上述替换，具体职责见 [ADR 0001](0001-coordination.md)。

官方依据和各层边界见[架构技术表](../architecture.md)，部署约束见[部署设计](../../operations/deployment.md)。上游支持能力不代表当前账号、模型和环境已运行通过。
