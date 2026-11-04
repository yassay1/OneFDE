# 后端结构重构验证记录

2026年11月4日完成。范围仅文件组织、Python包安装与依赖方向；C2未推进，没有新增业务接口、数据库结构、业务规则、Worker、SDK或前端。当前PRD0.7、原产品定义和用户已有Knowledge协作文档内容保留。

## 已完成的结构调整

应用从backend/app迁移到backend/src/onefde。入口为bootstrap/entrypoints，基础能力为core，数据库/HTTP/幂等适配为infrastructure，业务模块为auth、engagements和tasks。任务用例按tasks、inputs、runs、reviews拆分，公开内部命令入口为modules/tasks/service.py。完整职责、依赖方向和命令见 [代码组织](../development/code-structure.md)，决定见 [ADR0005](../architecture/ADR/0005-backend-code-structure.md)。

原services/task_service相互引用已消除；摘要函数不再从认证HTTP模块导入，通用分页不再反向依赖任务查询。业务命令不导入FastAPI或路由，不自行提交；原幂等事务和认证短事务边界保持。HTTP路由分组、operationId、响应状态与字段均保留。

测试按unit/integration/e2e/architecture/support归类。原52项用例完整保留，数据工厂、常量和确定性控制适配放在support；不再从测试用例或conftest导入普通辅助。两套HTTP场景移至tests/e2e，原scripts.http_smoke和scripts.c1b_smoke入口继续可用。

pyproject加入固定uv_build==0.12.5和module-name=onefde，uv sync进行可编辑安装；uv.lock仅将根项目改为可编辑包，原有包名称/版本集合未变。旧app源码在逐文件确认与开工快照一致后，归档到忽略的work目录；运行目录没有旧app副本，也没有PYTHONPATH注入。

## 检查前的保留措施

项目仍无Git元数据，无法获取git diff。开工将56个源码/文档/配置文件保存到work/structure-before，不含.env、凭据或缓存；另保存运行OpenAPI、ORM建表/索引DDL和开发库schema。原两份版本迁移、产品文档和四份OpenAPI文件均进行哈希/字节比较。

重构前实际执行：52项测试通过（12.765秒）、35项C1b HTTP检查通过、Alembic无漂移、OpenAPI导出一致。补查C1a场景时本机数据库容器停止，返回503/连接超时；启动原容器后恢复，未删除卷或修改开发凭据。

## 重构后实际结果

以下命令从D:\proj\OneFDE\backend执行。原测试断言保留，只调整导入与辅助位置；数据库继续为PostgreSQL17.7，未使用SQLite。

| 检查 | 实际结果 |
| --- | --- |
| `uv lock` / `uv sync --locked` | 安装onefde-backend可编辑包；原运行/开发依赖版本未变 |
| `uv run --locked pytest -q --junitxml=work/structure-tests.xml` | **58 passed**，0失败/错误/跳过，最终13.260秒；原52项全部保留，增加6项架构检查 |
| `uv run --locked pytest tests/unit tests/architecture -q` | **12 passed**，0.892秒，不连接数据库 |
| 原`scripts.http_smoke` | **19项通过**；验证会话/CSRF、创建查询、重放冲突、两个进程之间持久化与登出 |
| `uv run --locked python -m scripts.c1b_smoke` | **35项通过**；同Task三Run、四规格版本、两评审和两个API进程之间状态一致 |
| `uv run --locked alembic upgrade head` | 当前head 4bf8db3c4ef3，无新迁移；原迁移回填/降级保护测试仍通过 |
| `uv run --locked alembic check` | No new upgrade operations detected |
| `uv run --locked python -m scripts.export_openapi --check` | 三项导出文件一致性检查通过 |
| `uv run --locked ruff check src tests scripts migrations` | All checks passed |
| `uv run --locked ruff format --check src tests scripts migrations` | 77 files already formatted |
| `uv build --out-dir work/dist` | 成功构建sdist和wheel |
| 源码目录外隔离Python加载wheel | 51份应用Python文件完整；所有onefde模块从wheel加载，运行OpenAPI与基线相同；包内无tests/scripts/.env |

六项架构检查分别覆盖：依赖层次/业务模块方向、生产导入图无循环、任务命令不自行commit/rollback、测试辅助不依赖测试用例、正式src包安装、无数据库的运行契约一致性。

C1a HTTP复查在独立_test库上临时覆盖进程配置，使用随机测试账号；未写入现有.env，不需要知道或替换真实创始人密码。临时明文测试文件用后删除。C1b脚本继续只使用独立测试库和内存凭据。验证进程结束后关闭，开发PostgreSQL容器保留。

## 不变性证据

- **运行OpenAPI完全相等**；openapi.yaml、openapi.implemented.json、openapi.planned.yaml、openapi-diff.md四文件字节不变。仍为25项已实现操作、1项规划中的下载签名操作。
- **数据库结构不变**：14张表的ORM建表/索引DDL与开工快照完全相同；开发库schema导出移除pg_dump随机限制标记后完全相同。
- **迁移不变**：d3a2bfe5f985和4bf8db3c4ef3两份版本脚本字节不变；只更改env.py的模型导入路径及移除不再需要的sys.path配置。
- 原31个Pydantic类与15个ORM类的类定义语法树逐一相同。原52项测试用例名称和数量全部保留，增加项仅为架构约束。
- 原有锁定包名称/版本集合不变；PRD和product-definition相对开工快照字节不变。

具体哈希、用例和结果见 [结构化摘要](evidence/structure-refactor.json)，两套HTTP证据见 [C1a](evidence/structure-c1a-http.json) 和 [C1b](evidence/structure-c1b-http.json)。证据不含密码、Cookie或CSRF值。

## 修改范围和已处理问题

主要修改为src/onefde应用包、测试目录/辅助、scripts开发入口、pyproject/uv.lock、Alembic导入配置及CI命令；README、AGENTS、实施计划、架构和测试文档同步当前路径。新增代码组织文档、ADR0005及本记录；历史C1a/C1b验证文档保留当时事实与命令。

接线阶段缺少的Literal导入、路由模型别名及HTTP错误模块导入位置已修正；临时C1a驱动最初从根目录读取.env失败，随后改在backend执行；一次新架构测试的引号格式检查失败，仅格式化后检查通过。失败项均记录在进度中，未当作通过。

仍有1条原Starlette/httpx TestClient弃用提示，未抑制；uv跨盘缓存安装有hardlink回退提示，构建/安装成功。远程CI和Linux生产部署本轮未运行。

## 当前操作入口

```powershell
Set-Location D:\proj\OneFDE\backend
uv sync --locked
docker compose up -d --wait
uv run --locked alembic upgrade head
uv run --locked uvicorn onefde.entrypoints.api:create_app --factory --host 127.0.0.1 --port 8000
```

开发接口仍为http://localhost:8000/docs。维护命令改为`python -m onefde.entrypoints.cli`；完整登录、测试和HTTP示例以 [后端README](../../backend/README.md) 为准。没有新增模型/Worker执行入口，下一阶段C2保持未开始。
