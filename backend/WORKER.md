# C2 受控 Worker

已实现 PostgreSQL 认领、心跳、停止确认和结果回填，以及固定版本 OpenHands 接线。当前个人 Windows 宿主不满足执行边界，没有提供真实模型凭据；真实工程小任务未运行，C2退出条件尚未满足。实际检查见 [C2验证](../docs/operations/c2-verification.md)。

## 控制 API 与迁移

控制 API 沿用 [README](README.md) 的 `.env`、认证和回环启动方式；不在 API 进程启动 Worker。开发库先执行：

```powershell
uv sync --locked
uv run --locked alembic upgrade head
uv run --locked alembic check
uv run --locked uvicorn onefde.entrypoints.api:create_app --factory --host 127.0.0.1 --port 8000
```

新 head 为 `d5454eda0523`，只扩展 dispatch_jobs：Worker标识/随机认领代次、数据库时钟租约、认领/结束时间、次数、现场引用、结果摘要和回填正文。已有两份迁移不变；存在 C2 认领历史时拒绝降级擦除。升级前按部署文档备份。

## 专用 Linux 节点上的首次配置

这里只给操作步骤，尚未执行这些基础设施配置。使用独立 Linux 执行节点、本地 Docker Linux Engine、受限数据库服务身份、受控私网连接；节点不能承载个人文件或控制数据库。管理员先完成容器出网策略：只允许指定模型/批准的依赖来源，拒绝控制网络、数据库与宿主服务。`network`名称和确认开关不会自动建立防火墙；Worker不为用户开通云资源、建立网络或配置配额。

在该节点的 backend 目录中执行：

```bash
uv sync --locked --extra worker
cp .env.worker.example .env.worker    # 仅首次，不覆盖既有配置
chmod 600 .env.worker
install -d -m 700 /srv/onefde-worker
```

编辑 `.env.worker` 中独立的数据库 URL、绝对私有目录、已受限的 Docker network 和费用上限。完成专用节点/网络/提供方配额核对后再设置 `ONEFDE_WORKER_ISOLATED_HOST_CONFIRMED=true`。不要复制创始人密码摘要、会话密钥、对象桶或部署凭据到执行节点。DB服务身份需读任务/版本/模型修订，读写作业/Run/Task/事件/问题/产物相关表，不授予建库、改表或管理账号权限；本轮未自动创建生产角色。

将模型示例复制到自己的**非秘密配置文件**，填写 HTTPS 端点、`openai/<模型ID>`、提供方名称及 `env:ONEFDE_MODEL_...` 引用。`openai/` 是 SDK/LiteLLM 的兼容协议前缀，不限定商业提供方。原始密钥由节点 secret 管理机制注入同名环境变量，不能放入此 JSON、数据库、CLI 参数或工程上下文；`.env.worker` 不负责将额外模型变量写入进程环境。

```bash
uv run --locked --extra worker python -m onefde.entrypoints.worker import-profile --file model-profile.example.json
uv run --locked --extra worker python -m onefde.entrypoints.worker check
uv run --locked --extra worker python -m onefde.entrypoints.worker once
# 或持续消费，SIGINT/SIGTERM 请求本轮受控停止
uv run --locked --extra worker python -m onefde.entrypoints.worker run
```

实际使用前替换示例中的占位端点/模型，勿原样导入。import-profile仅创建不可变配置修订，输出 revision_id；状态是 configured，未标为 smoke_passed。通过登录后的 `GET /api/v1/model-profiles` 查询；按原HTTP契约 queue/start，并在start传该 revision_id。202表示持久接单，之后按 Run/事件查询。配置检查不调用模型；有阻塞返回2。所选修订的凭据在认领后、创建资源前解析，缺失则技术失败且明确尚未创建现场。

SDK/workspace/tools均固定1.59.0；Agent Server固定 `1.59.0-python@sha256:96038f92dc66228e389a95c2e5081dfc2cd4f5d307f051a7df9b1d50ccb86be7`。默认1 CPU/2GiB/256进程；创建容器后、启动Agent前用Docker设置限制，失败则不执行Agent。15分钟执行截止、SDK最多20次迭代、无LLM自动重试、无condenser/critic；SDK费用上限必须填写，提供方也必须配置限额。迭代限制和SDK成本统计不等于已实测的提供方硬调用/费用封顶，真实请求计数/最后一请求费用及停止延迟需在接入冒烟核验。

## 持久化与停止语义

- 认领/心跳/资源登记/回填各使用独立短 Session 与事务。外部 SDK 执行不持有业务事务；全局槽锁和行锁保护单一活动Run。
- 只有当前owner+随机token且租约有效的Worker可续租或首次回填。完整结果/产物引用/停止证据摘要一起保存，同代次同结果重放返回原结果，异结果409。HTTP启动幂等沿用原契约。
- API的cancel/stop_for_update只记停止意图，Worker心跳通知适配器。适配器停止容器后，必须通过成功的Docker清单/inspect核实不再运行；SDK pause/cleanup不构成停止证据。回填事务重新核对停止意图，保留已捕获的产物，再按cancelled或superseded登记；提交不自动接受Task。
- 租约过期、适配异常且现场不明、Docker不可达均为interrupted，继续占用全局名额。绝不因租约过期自动重新执行。心跳数据库错误立即请求停机，保留本地回执，不再以原归属回填；数据库恢复后的下一次轮询将过期现场冻结。`once`模式在此情形需要后续受控轮询完成过期检测。
- 工作源码在 `root/tasks/<task_id>/workspace`；每Run Session在 `root/sessions/<run_id>`。只将这两处挂载工程容器，不挂载Worker环境、DB文件、Docker socket、产物仓库或私有密钥目录。Session通过Agent Server的 `OH_CONVERSATIONS_PATH=/session` 落盘；加密/会话密钥在 `root/private/<run_id>/session.key`，不挂载，备份需独立受限。
- 确认停止后把源码打包为不可变私有blob，校验大小/SHA-256后在同一回填事务登记Artifact；拒绝符号链接、特殊文件和超限源码。Worker先保存不可变结果回执到 `root/artifacts/receipts`，DB异常时供核查；回执不自动触发重放或重执行。
- Final文本只作结构化结果提案，submitted还需实际终端成功退出记录与已保存源码；此条件不替代业务评审或完整正确性证明。终端退出码写入可信作业结果证据，不把模型叙述当工具结果。模型问题沿原TaskInput机制记录，不让Worker空等答案。

同任务新Run保留工作区，默认新建SDK Conversation，ID使用Run UUID；未实现自动复用旧Session或interrupted运维解锁。私有本地blob是真实文件，但S3上传/备份、签名下载及产物跨节点读取尚未接入；API目前只列元数据。Session可能包含敏感内容，不能作为公开Artifact。受限模型凭据可能存在同一个工程容器内，这是ADR0003明确的限制，并未实现模型出口隔离。

## 无模型检查

已有PostgreSQL开发/独立测试配置后，从backend执行：

```powershell
uv sync --locked --extra worker
uv run --locked --extra worker pytest -q --junitxml=work/c2-tests.xml
uv run --locked --extra worker python -m scripts.c2_smoke
uv run --locked --extra worker python -m scripts.c1b_smoke
uv run --locked --extra worker python -m scripts.export_openapi --check
uv run --locked --extra worker python -m scripts.check_migrations
```

pytest和c2_smoke会清空指定 `_test` 库，不能指向开发库；c2_smoke启动两个本机API进程、真实控制器和明确标注的测试执行适配，不启动SDK/Docker工程现场、不调用模型。先运行c2_smoke重置测试数据，再运行不清库的原c1b_smoke。check_migrations需要测试服务器的建库权限；创建唯一空测试库、执行完整迁移/空库回退/重迁移/漂移检查，最终仅删除该新建库。基础API可只安装核心依赖；未安装worker extra时SDK绑定检查会skip，不得将skip报告为通过。完整交付检查必须用extra，实际结果见验证记录。
