# OneFDE

OneFDE 是面向生鲜行业技术服务公司的内部经营与工程交付工作台。Business负责经营与获客，FDE负责客户方案与交付组织，Engineering负责工程实现，Knowledge横向支持前三者并整理候选能力。Backend保存工作与权限；Capability Library是可复用资产，经营/客户业务资料保留原事实与归属。

客户使用最终交付的软件；首版不需要登录 OneFDE。2026 年 11 月 4 日已实现并验证 C0+C1b持久控制；C2已实现Worker/SDK/本地沙盒，并在用户配置 DeepSeek Key 后完成本地真实模型网页小任务（改文件、检查、固定验证、业务接受）；C3工程上下文/结果契约已落地。云端生产隔离与公网交付仍未验收。

## 当前重点

以水果店供应商报价比较为首个贯穿案例，验证需求整理、工程任务、真实开发、部署访问、资产整理和第二次复用的完整链路。目前没有试点门店或真实报价样例，先以明确标注的模拟数据验证工程能力。

用户已确认[黑客松实施方案](docs/product/hackathon-proposal.md)。P0—P4 本地切片、薄工作台，以及 Business 咨询、售后和模拟找店已有本地记录。当前进度、未完成项和 11 月 5–6 日验收只在[实施计划](docs/development/implementation-plan.md)与[测试与验收](docs/operations/testing.md)维护。

模拟第一轮只比较商品、等级和规格明确一致且单位可换算的报价；信息不足时标记待核对。运费、起订量和送货条件不计入本轮比较，结果应说明这一限制。

## 文档入口

| 需要了解什么 | 阅读位置 |
| --- | --- |
| 公司方向、产品定位与原始确认状态 | [产品定义基线](docs/product/product-definition.md) |
| 当前 MVP 范围、交接与完成条件 | [PRD](docs/product/PRD.md) |
| 接下来的阶段、依赖与进度 | [实施计划](docs/development/implementation-plan.md) |
| 如何验证核心链路 | [测试与验收场景](docs/operations/testing.md) |
| 如何复现 Business 三条工作流 | [Business 本地验收](docs/operations/business-v1.md) |
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

`docs/` 保存产品与研发文档；`engagements/` 说明具体交付上下文；`capability-library/` 说明可复用资产。`backend/src/onefde/` 是按业务模块组织的后端安装包，含FastAPI/SQLAlchemy/Alembic、uv锁、PostgreSQL环境和测试。`frontend/` 是这条薄路径的 React 页面；构建出 `frontend/dist` 后，由开发 API 在可信 Origin 上提供。

代码职责与依赖规则见 [后端代码组织](docs/development/code-structure.md)。本地启动、迁移和检查命令见 [后端 README](backend/README.md)。阶段证据按日期留在 `docs/operations/`，当前结论见[实施计划](docs/development/implementation-plan.md)。没有公网部署。正式项目资料以本仓库为维护位置。

## 当前边界

部署基线是单台阿里云 ECS + Docker Compose，方案见[部署设计](docs/operations/deployment.md)和[ADR0009](docs/architecture/ADR/0009-single-ecs-mvp.md)。本地 Compose 见[操作手册](deploy/README.md)，未购买云机或公网部署。技术组合、Worker 边界和角色规则分别以[架构](docs/architecture/architecture.md)、[Worker手册](backend/WORKER.md)和[数据模型](docs/architecture/data-model.md)为准。

协作基线采用模块化 Backend：Task Service 管持续工作/输入/分配/评审，Dispatcher 管执行，Runtime 复用 SDK。工程待答时保存现场并结束本轮，采用回答后原 Task 下开新 Run；工程提交须经业务接受。短检索/咨询保持直接调用，不要求所有交互经过路由模型。完整规则只在架构、数据模型和接口维护。
