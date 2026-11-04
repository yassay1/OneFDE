# C1b 持久控制实现与验证

2026年11月4日完成本轮C1b。原C1a实现、开发数据库、PRD0.6及当前Knowledge协作说明保留；仅定点更新本轮事实。没有真实模型调用、Worker、前端或公网部署，确定性结果不作为Engineering工程完成证据。

## 已实现与事务边界

- TaskInput：HTTP保存pending，记录真实会话操作者、顺序、证据和回复归属。采用/拒绝显式保存理由、处理人、时间与版本；采用answer同时解决对应question，单独采用未答question或跨Task回复会拒绝。
- Task版本：记录输入只增加revision；非空采用或完整spec替换增加一个spec_version并保存不可变快照，拒绝不增加spec_version。版本列表/详情可读，旧Run固定快照不被后续输入改写。
- Run/待派发状态：queue与start分开；start/continue/retry原子登记Run、快照、作业及Task状态。全局事务锁与活动部分唯一索引保证一个活动工程Run，interrupted也占用。202不表示执行。
- 停止：未认领queued/pending作业可在锁下证明未执行并撤销；已开始运行只记cancel_requested，内部受控结果确认停止后释放。stop_for_update保留Task回draft，业务cancel才关闭Task。interrupted不开放强制释放/直接retry。
- 评审：仅当前版本的completed/submitted Run可评审，产物必须属于同一提交。accept还要求无pending/未答问题及检查证据；request_changes保存不可变评审并追加pending变更输入，Task回draft。Engineering不能自接受。
- 有序Task/Run事件、固定产物元数据和只读模型修订元数据。未接对象存储/上传/下载签名，也没有模型配置编辑API。

每个任务写命令先获得Task行锁，核对expected_revision。HTTP幂等记录先重放，再判断版本/状态；业务变更、版本、输入处理、评审、事件和幂等响应同事务提交。Run变更按幂等锁→全局执行锁→Task行锁的顺序，事务不跨外部执行。内部结果服务由调用方提交，公共路由未开放伪造工程成功接口。

## 文件与迁移

| 文件 | 本轮改动 |
| --- | --- |
| `backend/app/models.py`、`schemas.py` | 输入/版本/Run/作业/评审/事件/元数据模型与校验 |
| `backend/app/task_service.py`、`task_api.py` | 持久领域命令、内部受控结果边界与HTTP接口 |
| `backend/app/services.py`、`api.py`、`main.py` | 复用认证/幂等，支持PATCH/200/202和各对象分页，草稿保存版本1与事件 |
| `backend/migrations/versions/4bf8db3c4ef3_c1b_task_inputs_versions_runs_reviews_.py` | 扩展Task，新增9张所需表，回填C1a版本1，保护不可变历史 |
| `backend/tests/test_c1b.py`、`test_c1b_boundaries.py`、`conftest.py` | 持续协作/并发/回滚/迁移测试，独立测试库清理与确定性fixture |
| `backend/scripts/c1b_smoke.py`、`export_openapi.py` | 真实HTTP控制与跨进程检查、契约导出/差异检查 |
| `backend/README.md`、`.github/workflows/backend.yml` | 可复现命令、HTTP操作、C1b边界和CI配置（远程未运行） |
| 根入口/架构/数据模型/ADR/实施/测试文档、OpenAPI | 按事实更新进度，保留用户已有修改及原产品定义 |

新增表为task_versions、model_profile_revisions、runs、dispatch_jobs、task_inputs、task_reviews、task_events、run_events、artifacts。没有Worker租约/认领循环、依赖DAG或通用工作流框架。当前模型修订元数据由部署供给/测试fixture写入；开发库未新增真实模型配置，缺少有效修订时start返回409 MODEL_PROFILE_UNAVAILABLE。

迁移从d3a2bfe5f985升级至4bf8db3c4ef3。开发库3个旧草稿及3条回填版本保留，原请求/spec不变。存在C1b业务历史/配置/产物时拒绝破坏性降级，使用审阅备份或前向修复。测试实际覆盖C1a旧结构插入草稿后升级/回填、无漂移和有历史时降级拒绝。

版本、评审、事件、模型修订、产物元数据有数据库UPDATE/DELETE保护；输入原文与已处理决定、Run快照和登记结果受触发器保护。测试清理仅对显式独立`_test`库TRUNCATE，未清空开发库。

## 实际检查与证据

以下命令从`D:\proj\OneFDE\backend`执行：

| 命令/检查 | 实际结果 |
| --- | --- |
| `uv run --locked alembic upgrade head` | 现有开发库升级成功，旧草稿版本1回填 |
| `uv run --locked alembic current` | 4bf8db3c4ef3 (head) |
| `uv run --locked alembic check` | No new upgrade operations detected |
| `uv run --locked pytest -q --junitxml=work/c1b-tests.xml` | 52 passed，0失败/错误/跳过，最终13.016秒；含原23项回归 |
| `uv run --locked python -m scripts.c1b_smoke` | 35项真实HTTP控制检查通过，两个独立回环API进程 |
| `uv run --locked ruff check app tests scripts migrations` | All checks passed |
| `uv run --locked ruff format --check app tests scripts migrations` | 25 files already formatted |
| `uv run --locked python -m scripts.export_openapi --check` | 与Pydantic运行契约一致，无过期导出 |

实际版本沿用uv.lock，没有新增SDK/模型依赖：Python3.13.5、uv0.12.5、FastAPI0.162.0、Pydantic2.14.2、SQLAlchemy2.1.7、psycopg3.3.7、Alembic1.20.1、PostgreSQL17.7。测试仍有1条Starlette/httpx TestClient兼容路径弃用提示，未抑制，当前锁定版本检查通过。

[测试摘要](evidence/c1b-tests.json)保存52个用例、精确版本和结果；[HTTP证据](evidence/c1b-http.json)保存检查、Task/Run/版本/评审，不含密码、会话Cookie或CSRF值。

HTTP最终使用进程14236和17068，同一个Task `bf30604a-9492-47b4-9522-f34fbde44c11`经历：记录/采用澄清→Run1提问并停止→回答/采用→Run2提交→要求修改→采用新规格→Run3提交→接受。生成4个规格版本、2次评审、24个有序Task事件。进程重启后Task、三个Run、版本和评审返回一致；原采用请求即使当前Task已关闭仍按原键重放原响应。

三个Run ID：`25ea062a-9483-45cb-ba64-2541dac1c92a`、`50cd6192-4a1a-4b1c-ac37-b4722b4e1c60`、`63662ef0-7477-4a9c-9f37-36a4252a7617`。

输入/Run/评审的客户端操作使用真实HTTP；Run开始/问题/完成事实由内部确定性测试适配写入，产物明确为SIMULATED元数据，没有调用模型、运行Worker、构建文件或证明真实产物可下载。脚本仅操作独立测试库并使用内存临时账号，不修改开发配置；验证结束API进程关闭，PostgreSQL容器保留。

## 契约与已发现问题

运行契约以Pydantic为源导出到`openapi.implemented.json`，同路径`openapi.yaml`合并未来设计。目前25个已实现操作，1个规划中的下载签名操作。新增两项版本读取接口与4个输入处理审计字段，其余原字段/必填项、operationId和成功状态均已核对，见 [契约差异](../architecture/openapi-diff.md)。原设计快照没有改写。

过程中实际发现并修正：actions operationId与原契约actOnTask不一致；临时脚本Windows默认GBK读取中文失败，改为显式UTF-8；HTTP脚本共享规格字典导致原重放正文被修改（服务正确409），改为独立副本；无正文logout缺JSON头（服务正确400），改为显式Content-Type。失败轮未当作通过。测试共享fixture的lint重定义也已修正，最终检查全部通过。

本轮事务/锁/索引实现继续采用[SQLAlchemy PostgreSQL部分索引](https://docs.sqlalchemy.org/en/21/dialects/postgresql.html#partial-indexes)和[锁后刷新ORM对象的官方机制](https://docs.sqlalchemy.org/en/21/orm/queryguide/api.html#populate-existing)，配合已有请求Session和显式提交边界，没有引入调度框架。

## 复现与下一步

```powershell
Set-Location D:\proj\OneFDE\backend
uv sync --locked
docker compose up -d --wait
uv run --locked alembic upgrade head
uv run --locked uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

开发接口见`http://localhost:8000/docs`；配置、单账号登录和输入采用HTTP示例见 [后端README](../../backend/README.md)。另一个终端运行`uv run --locked pytest -q`及`uv run --locked python -m scripts.c1b_smoke`，测试库须独立且以`_test`结尾。

本轮C1b完成，完整C阶段仍未完成。远程CI仅配置未运行。下一项为C2：受限Worker/SDK接入、作业认领与确定停止/结果证据适配；模型凭据/配额及执行隔离落实后再做一次真实工具冒烟。薄FDE和实际同Task多轮工程证据属于后续C3。对象存储/签名下载、任务依赖、前端与报价规则仍未实现。
