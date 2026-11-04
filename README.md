# OneFDE

OneFDE 是面向生鲜行业技术服务公司的内部经营与工程交付工作台。Business负责经营与获客，FDE负责客户方案与交付组织，Engineering负责工程实现，Knowledge横向支持前三者并整理候选能力。Backend保存工作与权限；Capability Library是可复用资产，经营/客户业务资料保留原事实与归属。

客户使用最终交付的软件；首版不需要登录 OneFDE。2026 年 11 月 4 日已实现并验证 C0+C1b持久控制；C2已实现Worker认领、停止确认、结果回填与固定SDK适配，真实工程执行仍受专用Linux/模型环境阻塞，尚未完成C2验收。

## 当前重点

以水果店供应商报价比较为首个贯穿案例，验证需求整理、工程任务、真实开发、部署访问、资产整理和第二次复用的完整链路。目前没有试点门店或真实报价样例，先以明确标注的模拟数据验证工程能力。

模拟第一轮只比较商品、等级和规格明确一致且单位可换算的报价；信息不足时标记待核对。运费、起订量和送货条件不计入本轮比较，结果应说明这一限制。

## 文档入口

| 需要了解什么 | 阅读位置 |
| --- | --- |
| 公司方向、产品定位与原始确认状态 | [产品定义基线](docs/product/product-definition.md) |
| 当前 MVP 范围、交接与完成条件 | [PRD](docs/product/PRD.md) |
| 接下来的阶段、依赖与进度 | [实施计划](docs/development/implementation-plan.md) |
| 如何验证核心链路 | [测试与验收场景](docs/operations/testing.md) |
| 关键页面操作与任务反馈 | [产品设计](docs/design/design.md) |
| 系统总架构图、为什么这样分工、一次需求如何流转 | [架构总览与设计](docs/architecture/architecture.md) |
| Task、Run、Session 与状态 | [数据模型](docs/architecture/data-model.md) |
| 首个工程切片的 HTTP 字段与错误契约 | [OpenAPI](docs/architecture/openapi.yaml) |
| 环境、认证、凭据、发布与恢复 | [部署设计](docs/operations/deployment.md) |
| 客户或演示项目如何记录 | [Engagement 约定](engagements/README.md) |
| 首个模拟案例及待确认内容 | [报价比较演示](engagements/demo-supplier-quotes/brief.md) |
| Knowledge如何支持三个角色、能力库与业务资料的区别及权限 | [知识服务与能力库约定](capability-library/README.md) |
| Agent 在本仓库如何工作 | [AGENTS](AGENTS.md) |

## 项目结构

`docs/` 保存产品与研发文档；`engagements/` 说明具体交付上下文；`capability-library/` 说明可复用资产。`backend/src/onefde/` 是按业务模块组织的后端安装包，含FastAPI/SQLAlchemy/Alembic、uv锁、PostgreSQL环境和测试；`frontend/` 保持预留。

代码职责与依赖规则见 [后端代码组织](docs/development/code-structure.md)，本轮结构调整证据见 [重构验证](docs/operations/structure-refactor-verification.md)。本地启动、迁移、HTTP 示例与测试命令见 [后端 README](backend/README.md)，最新结果见 [C1b验证记录](docs/operations/c1b-verification.md)，前轮证据保留在 [C0+C1a记录](docs/operations/c0-c1a-verification.md)。产品设计、架构和数据模型中的后续能力仍是推荐基线；没有公网部署。正式项目资料以本仓库为维护位置；聊天中的调研报告和导出文档是研究依据或审阅快照。

## 当前边界

已完成文档体系与 Router 源码研究。推荐 React/TypeScript/Vite 工作台，Python/FastAPI 控制后端，PostgreSQL 事务任务与独立 Worker，OpenHands SDK/DockerWorkspace，私有 S3 兼容产物存储，Linux/Compose/Caddy 部署。FDE 负责业务方案、程序 Coordinator 负责一致性，不增加第五个路由模型。模型配置兼容 API，MiMo 仅为候选；具体模型、资源账号和域名尚未配置；控制后端与 PostgreSQL 已本地运行，完整推荐组合尚未接通。

用户已明确先后端、前端之后单独设计。C2已有95项后端测试和9项新增HTTP控制检查证据，原19/35项HTTP回归通过；SDK绑定使用真实固定类型与测试资源替身，不作为模型工程成功证据。最新结果见 [C2验证](docs/operations/c2-verification.md)，配置和启动见 [Worker手册](backend/WORKER.md)。下一项是准备专用Linux/受限模型配置后跑一个真实文件/工具小任务，前端继续后置。

协作基线采用模块化 Backend：Task Service 管持续工作/输入/分配/评审，Dispatcher 管执行，Runtime 复用 SDK。工程待答时保存现场并结束本轮，采用回答后原 Task 下开新 Run；工程提交须经业务接受。短检索/咨询保持直接调用，不要求所有交互经过路由模型。完整规则只在架构、数据模型和接口维护。
