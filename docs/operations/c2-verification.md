# C2 Worker与SDK接入检查

最新状态：本地WSL/S1/S2与DeepSeek环境已就绪；2026-11-04本地真实模型网页冒烟已通过（Task/Run/产物/验证/接受），详见[CA验证](coding-agent-verification.md)。云端单ECS生产部署与费用账单级核对仍未实施；历史物理另机要求已由[ADR0009](../architecture/ADR/0009-single-ecs-mvp.md)取代。

2026年11月4日本地检查。结果：**可测试控制/适配部分已实现，C2真实工程退出条件未完成**。缺少专用Linux执行节点、受控网络、Worker生产服务连接/私有目录、受限模型凭据与费用额度；未启动工程容器、未调用真实模型、无前端或公网部署。

## 保留与实现

当前目录无Git元数据，实施前保存113个源码/文档文件到忽略的 `work/c2-before`，逐文件比较；没有重置已有实现。AGENTS、PRD、原始产品定义、原两份迁移字节未变；已有依赖包版本均未升级。C2通过可选worker extra新增精确OpenHands系列1.59.0及传递依赖，API核心安装仍独立。

- DispatchJob增加owner/token/数据库时钟租约、认领/结束时间、次数、资源引用、结果摘要和正文。迁移head为d5454eda0523，14张业务控制表数量不变；存在认领历史时拒绝擦除式降级。
- 短事务认领/续租/资源登记/回填，外部执行不持有业务Session。并发只认领一次；旧owner/token或过期租约不能写结果；未知现场保持interrupted占用，不自动重新执行。
- 心跳观察原HTTP停止意图，适配层独立确认Docker容器不再运行。回填在全局槽锁内重新核对意图，cancelled/superseded优先，保留已落盘产物；回填同内容重放，不同内容冲突。
- 私有本地不可变源码blob与回执，读回校验SHA-256和大小后登记Artifact。每Task工作区、每Run Session/Conversation分离，Session密钥独立私有保存，不挂载工程代码。
- 独立Worker check/once/run/import-profile入口、配置样例、非秘密模型修订供给。仅工程终端/文件工具，复用SDK Agent Loop；无通用调度平台、角色模型或伪成功HTTP接口。

具体代码边界见 [代码组织](../development/code-structure.md)，配置/启动与恢复限制见 [Worker手册](../../backend/WORKER.md)，上游源码与适配取舍见 [ADR0006](../architecture/ADR/0006-c2-worker-sdk-boundary.md)。

## 实际执行结果

以下命令从 `D:\proj\OneFDE\backend` 执行；所有数据库测试使用真实PostgreSQL17.7，未用SQLite替代控制事务。

| 命令/检查 | 实际结果与证据 |
| --- | --- |
| `uv sync --locked --extra worker` | 安装成功；sdk/workspace/tools均1.59.0；已使用真实SDK类型进行绑定检查 |
| `uv run --locked --extra worker pytest -q --junitxml=work/c2-tests.xml` | **95 passed，0 skipped**，最终36.41秒；原58项全部保留；新增20项PG及17项配置/文件/停止/SDK绑定检查 |
| `uv run --locked --extra worker python -m scripts.http_smoke --password-file <临时文件>` | 原**19项真实HTTP检查通过**，两个API进程，开发库草稿重启可查；仅进程环境覆盖一次性测试账号，未编辑.env，临时密码文件已删除 |
| `uv run --locked --extra worker python -m scripts.c2_smoke` | 新增**9项真实HTTP控制检查通过**，两个API进程、真实Worker控制器、PG及实际私有blob，执行端明确模拟，无模型/工程容器 |
| `uv run --locked --extra worker python -m scripts.c1b_smoke` | 原**35项真实HTTP控制检查通过**，同Task多Run/输入采用/版本/评审/重启场景仍可用 |
| `uv run --locked --extra worker alembic upgrade head`、`alembic check` | 现有开发库升级成功，**No new upgrade operations detected** |
| `uv run --locked --extra worker python -m scripts.check_migrations` | 唯一新建空PG库从base到head成功；空库downgrade base再upgrade head及两次漂移检查通过；最终仅删除本次新建库 |
| `uv run --locked --extra worker python -m scripts.export_openapi --check` | 已实现25操作/规划1操作；字段、状态码、路径及schemas与C2前相同，只更新运行JSON的info.description和生成说明 |
| `uv run --locked --extra worker ruff check src tests scripts migrations`、`ruff format --check ...` | 通过 |
| `uv build --out-dir work/dist` | wheel与sdist构建成功，应用版本保持0.1.0 |
| `uv run --locked --extra worker python -m onefde.entrypoints.worker check` | **预期退出2**；固定SDK已安装，具体环境缺项列于下节，未发起模型调用 |

95项测试包含：并发单次认领、认领与回填回滚、未采用输入阻止认领、owner/token/过期拒绝、续租、过期冻结、不重执行、结果重放/冲突、停止意图优先且未确认不释放、真实私有blob校验/损坏拒绝、已分配后配置异常保持占用、心跳失联只留回执、配置引用供给、历史降级保护。SDK绑定使用实际Agent/LLM/Tool类型，但Docker/Conversation是测试替身，不能记作真实Engineering成功。

HTTP证据包含API进程ID、Task/Run/Engagement UUID和通过条目，不含Cookie、CSRF、密码或模型凭据。原始本地文件：`backend/work/c2-tests.xml`、`http-smoke.json`、`c1b-http.json`、`c2-http-evidence.json`、`c2-migration-evidence.json`、`c2-command-evidence.json`、`c2-audit.json`。脚本本身在tests/e2e及scripts中，可复跑；c2_smoke/pytest清空独立_test库，不能用于开发库。

仅一个现有Starlette TestClient/httpx弃用提示；未出现测试失败或skip。开发中新增PG测试曾发现SQLAlchemy取时钟时提前autoflush触发claim CHECK，已改为先读时钟再完整赋值后通过；新增续租测试曾漏导入timedelta，补齐后全量通过。远程CI只更新配置，未实际运行。

## 阻塞与尚未验证

实际环境为个人Windows AMD64；没有本轮专用Linux节点。Worker check输出六项阻塞：专用Linux、隔离确认、独立Worker数据库连接、绝对私有目录、隔离网络、明确费用/配额。另未提供所选模型的secret_ref对应受限密钥；check只检查环境，不据此证明任何模型可用。镜像manifest已核对digest，未拉取/运行工程镜像。

因此未执行：真实模型工具往返、真实工程改文件/命令、Agent Server挂载/Session恢复、实际容器资源/网络隔离、请求计数/费用封顶及停止延迟。不会把替身测试、上游源码或metadata配置状态写成这些检查通过。

已知当前边界：本地私有blob尚未上传S3或提供下载；每Run新建Conversation，未自动恢复旧Session；interrupted需要受控人工核查，未实现解锁/恢复命令；心跳DB失联保留回执但不自动回填；资源控制为CPU/内存/PID/时间及产物大小，节点磁盘配额由执行环境配置；SDK迭代/费用限制还需提供方配额配合。受限模型密钥可能在Agent Server同容器内存在，未承诺模型凭据与任意shell彻底隔离。

下一项：在已准备的专用Linux执行节点配置受限网络/目录/服务身份/模型额度，导入真实模型修订，先执行check，再通过HTTP提交一个很小的工程Task，运行Worker once；检查文件实际变化、终端退出/结果blob/Session、停止证明、请求费用及重启查询。该证据齐备后再将C2标为完成，不推进前端或公网部署。

## 文件清单

新增：`core/execution.py`、`worker/{config,controller}.py`、`entrypoints/worker.py`、`infrastructure/{artifacts.py,runtime/openhands.py}`、`modules/tasks/{dispatch,configuration}.py`，对应包初始化文件；迁移d5454eda0523；`.env.worker.example`、`model-profile.example.json`、`WORKER.md`；`tests/integration/test_worker.py`、两份runtime/SDK单元测试、`tests/e2e/c2_smoke.py`、`scripts/{c2_smoke,check_migrations}.py`；本记录与ADR0006。

修改：tasks models/service/runs支持受信任Worker归属与真实产物key；bootstrap与OpenAPI生成说明；迁移head断言/架构检查；pyproject/uv.lock、CI和.gitignore；README、后端说明、实施计划、代码组织、架构/数据模型、部署/测试文档及现有规划文件。PRD/产品定义、原迁移及已有依赖版本未改。

## 2026年11月4日本地WSL开发环境准备

授权：用户明确选择WSL2+Docker本地方案并要求同步约定；DeepSeek稍后配置，禁止模型调用及付费资源。边界以[ADR0007](../architecture/ADR/0007-local-wsl-development.md)为准，命令与恢复方式见[WSL手册](../../backend/local-wsl/README.md)。本轮没有创建业务Task/Run、模型修订或评审，不使用环境检查产物冒充Engineering提交。

### 配置事实

- 新增`OneFDE` Ubuntu24.04.5 WSL2发行版，D盘50GB动态虚拟盘；Python3.13.5、uv0.12.5，worker extra按原锁安装，SDK三包1.59.0，原Agent Server镜像digest不变。
- 独立Ubuntu签名仓库Docker29.1.3/Compose2.40.3；不与Docker Desktop共享daemon。原Windows数据库与凭据保留，新演示开发库和独立测试库迁移到d5454eda0523。
- Worker身份无超级用户/建库/建角色/DDL/认证表读取/测试库连接权限；私有根700、配置600。Linux用户UID10001匹配固定镜像，未放宽挂载权限。
- 本发行版关闭Windows盘自动挂载/程序互操作；实际仅重启OneFDE验证，不全局关闭WSL。工程网络internal且禁IPv6，独立桥INPUT规则拒绝容器到宿主的新连接，systemd随Docker启动恢复；数据库在另一个网络、端口仅绑定127.0.0.1:55433。
- 工程1 CPU/2GiB/256 PID；数据库0.5 CPU/384MiB/128 PID；Worker仍15分钟/最多20次SDK迭代。未改影响其他发行版的全局内存设置。模型开关false、费用未设置、模型配置0条。

### 实际命令与结果

以下Linux命令从`/home/onefde/OneFDE/backend`执行；初始化与Windows源同步命令见手册。

| 命令/检查 | 实际结果/证据 |
| --- | --- |
| `uv sync --locked --extra worker`，开发库`alembic upgrade head`/`alembic check` | 安装成功，head为d5454eda0523，无漂移；没有升级应用锁文件 |
| `uv run --locked --extra worker python -m onefde.entrypoints.worker check --environment-only` | **退出0，无环境阻塞**，不检查模型效果/预算，见[环境预检](evidence/c2-wsl-environment-preflight.json) |
| 同命令去掉`--environment-only` | **退出2**，明确模型执行关闭、费用/配额缺失；见[执行预检](evidence/c2-wsl-execution-preflight.json) |
| `uv run --locked --extra worker python local-wsl/check_environment.py` | **6组真实环境检查通过**：Windows挂载/互操作配置、internal控制网分离、受限DB、固定SDK容器/资源/挂载、真实命令/三类TCP拒绝（宿主使用已验证可连接的临时监听端口）、停止/文件Session持久化/不可变归档；见[完整命令及结果](evidence/c2-wsl-environment.json) |
| `uv run --locked --extra worker pytest -q --junitxml=work/wsl-tests.xml` | **100 passed，0 skipped，17.46秒**；1条既有Starlette弃用警告。见[JUnit](evidence/c2-wsl-tests.xml) |
| 临时`uvicorn`进程绑定127.0.0.1:8001，经真实HTTP health/login/session/logout后关闭 | **200/200/200/204**；开发库Task/Run/ModelProfile均0条，未输出密码/Cookie/CSRF。见[API检查](evidence/c2-wsl-api-check.json) |
| Windows `ruff check`、`ruff format --check`、`scripts.export_openapi --check` | 通过；无HTTP字段或数据库结构变更 |

环境归档SHA256为`5fa5ecfec40b9d656647680da4c16e47a3335a13a30869a662d4601dd3a9be55`（936字节，3个文件），私有blob位于Worker根下的environment前缀；不是业务Artifact版本。实际命令经真实Agent Server执行，没有Agent/LLM调用。

### 联调修复与限制

真实接入暴露并修复两处原适配问题：SDK健康检查timeout是keyword-only；`--rm`容器在清单与inspect之间删除时，需要再取得一次成功清单证明不存在，不能把inspect失败本身当作停止。绑定替身改为真实参数签名，并覆盖停止竞态的成功/不可达分支。

环境联调另处理：UID1000与镜像10001不匹配导致私有Session不可写；Docker29 internal网络不发布请求的回环端口，改用受信任Docker inspect取得专用桥地址，由同宿主Worker访问Agent Server，不开放外网。一次未启动数据库的连接失败通过启动检查和演示DB重启策略处理。原生下载慢时使用临时、限WSL地址的本机代理中继；安装后已关闭并移除临时daemon代理配置。失败轮次不计通过。

SDK导入首次尝试读取公开模型价格表后回退，本轮未发送模型推理请求；环境检查现强制使用内置价格表。SDK cleanup在已自动删除容器后可能输出“no such container”，停止证据由独立成功清单核实，不依赖该输出。

**未完成/未验证**：DeepSeek非秘密配置/本地密钥/费用额度、模型出口白名单及其实际拒绝检查、真实模型生成网页/检查脚本、Backend→Worker→Engineering回填与业务评审、真实请求计数/费用封顶/停止延迟、正式专用节点隔离及公网部署。当前只完成环境准备，C2整体保持未完成。

## 后续本地单机Compose适配（2026年11月4日）

按用户授权完成S1/S2：API/PG/可信Worker容器化，ecs_shared创建时硬化/限额与私网SDK连接、无模型standby、离线白名单探测、2GiB整体持久盘硬边界、认领前容量拒绝和重启恢复。Linux106项零skip通过；九组真实SDK环境检查与三类资源触顶探测通过，HTTP队列始终未认领后取消。逐项范围、命令/Task/Run/归档摘要及JSON/XML证据统一见[单机验收](single-ecs-verification.md)。

本轮环境归档不是业务提交；没有Agent/LLM推理、真实Engineering成功或业务接受。C2真实模型网页任务、费用计数/停止延迟继续未完成；云端E07—E11/在线模型/生产配额、正式交付与备份继续待验收。旧WSL记录及其中阻塞保留为当时事实，以本节与单机验收为最新状态。

## 后续DeepSeek环境配置（仅环境，不运行C2）

用户已填写Key，并明确只配环境、不执行最小调用或C2网页任务。已完成.env选定字段同步、私有600文件与Worker实际加载、非秘密模型修订供给及DeepSeek域名代理/TLS检查；[脱敏证据](evidence/deepseek-environment.json)记录无提供方HTTP/模型请求、无Task/Run创建。Worker仍standby、模型关闭，执行预检退出2。Key的API有效性、模型/SDK工具兼容性和费用/真实工程闭环仍未验证；不把TLS连通或configured状态当作smoke_passed。之前记录中的空Key/无配置为各轮历史事实。
