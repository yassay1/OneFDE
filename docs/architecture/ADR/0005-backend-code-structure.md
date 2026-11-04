# 后端采用src包与按业务模块组织的单体

状态：2026年11月4日已实施并本地验证；范围仅代码组织和依赖，不推进C2。

## 决定

应用包为`backend/src/onefde`，业务模块为auth、engagements、tasks；模块内分HTTP路由、Pydantic契约、ORM映射、查询和用例。Task/Input/Run/Review目前保留在任务模块内，按实际写用例拆分文件。bootstrap与entrypoints负责装配和启动，core保存独立基础能力，infrastructure提供数据库/HTTP/幂等适配。

## 原因与取舍

C1b后集中models/schemas和task_service开始承载多种职责，通用services与任务服务存在相互引用，测试辅助也跨测试模块导入。使用明确的单向依赖和公开用例入口消除这些关系；src包通过可编辑安装支持API、CLI、迁移和未来受控入口复用同一应用代码。

继续使用原生SQLAlchemy与显式Session，不为每张表建立Repository抽象，不增加命令总线或微服务。Run/评审拆成文件不改变同一业务事务。采用固定uv_build仅用于包装纯Python应用，不升级运行依赖。

## 验证与后果

原52项测试与两套HTTP场景继续运行，增加6项架构检查；验证运行OpenAPI、ORM DDL、开发库schema、迁移文件和锁定应用版本不变。新启动路径为`onefde.entrypoints.api:create_app`，维护命令为`python -m onefde.entrypoints.cli`。旧源码归档到忽略的work目录，不保留可被误用的app副本。

目录/依赖规则见 [代码组织](../../development/code-structure.md)，实际结果见 [重构验证](../../operations/structure-refactor-verification.md)。C2接入执行器时再增加实际适配，当前没有Worker或SDK目录占位。

参考：[Python src布局](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/)、[FastAPI多文件应用](https://fastapi.tiangolo.com/tutorial/bigger-applications/)、[uv构建后端](https://docs.astral.sh/uv/concepts/build-backend/)。这些提供工程机制，业务模块边界为OneFDE自身取舍。
