# 本地单机 Compose：操作与边界

适用：用户授权的 `OneFDE` WSL2 开发发行版；本地 S1/S2 无模型验证。当前配置不是可直接上线的生产文件。状态与证据统一见[单机验收](../docs/operations/single-ecs-verification.md)。本轮不调用模型、不购买资源、不发布客户产品。

## 已安装环境

Windows 源码位于 `D:\proj\OneFDE`，Linux 副本位于 `/home/onefde/OneFDE`。使用本发行版原生 Docker，避免误操作 Docker Desktop。保持一个 `wsl -d OneFDE` 终端打开进行开发；systemd 服务本身不会保证 WSL 永久驻留。关闭/重启本发行版后，数据留在其虚拟磁盘上。

项目名 `onefde-local`，与旧 `onefde-wsl` 数据库、Windows 数据库分别保存；不要对旧卷执行初始化或 `down -v`。服务划分：

| 服务 | 权限/网络 | 本地上限 |
| --- | --- | --- |
| api | 无 Socket/工作区；控制网及本地访问网；仅 `127.0.0.1:8002` 发布 | 0.5 CPU / 512MiB / 128 PID |
| postgres | 控制网固定地址，无发布端口；独立 `onefde-local_pgdata` 卷 | 0.5 CPU / 384MiB / 128 PID |
| worker | 可信管理服务，Socket GID附加组、控制网及工程网；当前仅 standby | 0.5 CPU / 1GiB / 128 PID |
| egress | 非root、只读、无cap；工程网与离线探测网 | 0.25 CPU / 128MiB / 64 PID |
| Sandbox | 按需动态兄弟容器；无Socket、控制网、模型环境变量或管理secret挂载 | 1 CPU / 2GiB（禁swap）/ 256 PID |
| probe | checks profile的无模型 TCP 测试端点；验证后停止 | 0.1 CPU / 64MiB / 32 PID |

API/Worker先共用一个锁定应用镜像，API虽装有SDK和Docker CLI，但没有Socket或工作区权限。四角色没有增加四个常驻进程；本轮没有实现其他角色。各固定服务也显式限制swap和日志，日志10MiB×3。生产Caddy/HTTPS、网站/工作台及产品发布不在此配置中。

## 启动与检查

### DeepSeek配置入口（backend/.env，不启用执行）

用户只编辑Windows的`backend/.env`：填写`DEEPSEEK_API_KEY=`，保留已准备的`DEEPSEEK_BASE_URL=https://api.deepseek.com`和`DEEPSEEK_MODEL=deepseek-flash`即可。`.env`已被Git及源码同步器排除，不需要进入WSL操作私有文件，也不要发送Key或含Key的截图。

其余由维护Agent操作：先同步源码，再从Windows仓库根运行`uv run --locked --project backend --extra worker python deploy/sync_deepseek.py`。它只选取三个DeepSeek字段，通过本地WSL标准输入传递；不会执行`.env`、展开变量、输出Key或复制数据库/登录凭据。受信任接收端原子写入WSL私有600文件`deepseek_api_key`及非秘密`deepseek-profile.json`。空Key拒绝同步；`--check`仅报告是否填写，不输出值。

Compose仅把Key作为只读secret提供给可信Worker，`launch.py`转成`ONEFDE_MODEL_ENGINEERING`；完整`.env`不进容器。保存`.env`不会自动同步或启用作业消费；同步后须重新创建Worker以加载新的secret文件，不仅restart旧bind。私有文件是由Agent维护的运行副本，后续修改仍以Windows `.env` 为入口。原`set_model_key.py`保留为可选终端输入方式，用户无需使用。

DeepSeek Key/profile/受限出口已在本地落地；真实网页冒烟见[CA验证](../docs/operations/coding-agent-verification.md)与`deploy/run_c2_webpage.py`（需显式 `ONEFDE_WORKER_MAX_COST_USD`）。Compose内 Worker 默认可保持 standby；冒烟使用宿主 venv Worker once，不因仅保存 `.env` 自动消费作业。

以下是**已有环境**操作，不是新机器自动安装器。先在 Windows 同步已审阅源码：

```powershell
Set-Location D:\proj\OneFDE
python backend/local-wsl/sync_source.py
wsl -d OneFDE
```

随后 Linux 中执行（常用命令均从仓库根）：

```bash
cd /home/onefde/OneFDE
docker compose --env-file /srv/onefde-local/private/compose.env -f deploy/compose.yaml up -d --wait api worker egress
docker compose --env-file /srv/onefde-local/private/compose.env -f deploy/compose.yaml exec -T worker python /app/ops/launch.py check
docker compose --env-file /srv/onefde-local/private/compose.env -f deploy/compose.yaml exec -T worker python /app/ops/launch.py execution-check
```

环境检查应退出0；完整执行检查应退出2，原因是模型关闭、未设置费用上限。`standby`只维持服务与健康检查，不建立作业数据库引擎或认领作业。不能通过环境检查开启消费，不能为消除阻塞填写虚假额度。

API地址 `http://127.0.0.1:8002/docs`；账号founder，随机密码只保存在本地私有 `owner_password` 文件，不进入Git或证据。使用独立浏览器配置文件，端口不能隔离同名Cookie。仅本地开发允许HTTP和非Secure Cookie。

首次已执行的准备顺序：专用WSL环境按[原手册](../backend/local-wsl/README.md)建立；root以该环境venv Python执行 `deploy/setup_local.py`；构建应用镜像；启动postgres；运行ops profile的migrate、initialize；最后启动API/Worker/egress。示例：

```bash
# root，仅在已批准的OneFDE发行版
/home/onefde/OneFDE/backend/.venv/bin/python /home/onefde/OneFDE/deploy/setup_local.py
# 以下为onefde用户，仓库根
docker compose --env-file /srv/onefde-local/private/compose.env -f deploy/compose.yaml build worker
docker compose --env-file /srv/onefde-local/private/compose.env -f deploy/compose.yaml up -d --wait postgres
docker compose --env-file /srv/onefde-local/private/compose.env -f deploy/compose.yaml --profile ops run --rm migrate
docker compose --env-file /srv/onefde-local/private/compose.env -f deploy/compose.yaml --profile ops run --rm initialize
```

镜像构建使用已安装原生Docker CLI/uv和现有Linux uv缓存的命名build contexts，`uv sync --locked --offline`、构建网络none；这些宿主路径是本地限定，云端构建流程需另行适配。基础Python/Postgres/Squid/Agent Server均固定digest；应用本地标签对应的实际镜像ID见证据，不把标签当不可变版本。

## 隔离与持久化

- `/srv/onefde-local/private` 为700，secret文件600，分服务挂载。迁移管理员、API、Worker分开数据库角色；Worker不能读认证表、改schema或写模型配置。`launch.py`仅支持列出的secret文件字段，不是通用 `*_FILE` 支持。
- Worker挂载 `/srv/onefde-local/worker` 同绝对宿主路径；Sandbox只得到该Task的workspace和该Run的session。UID/GID固定10001，根只读、cap_drop ALL、NNP、默认seccomp。`/tmp`及`/home/openhands`各256MiB tmpfs；固定Agent Server会在/tmp解包动态库，因此该有界tmpfs明确允许exec，仍保留nosuid/nodev。
- Socket `:ro` **不限制Docker API操作权限**，Worker仍等同宿主管理权限，只有可信代码可用。工程shell没有Socket；不允许把模型生成命令转成宿主Docker命令。
- Worker数据盘是**新建2GiB ext4 loop文件的硬总容量边界**，不是每Task独立project quota；含源码、Session、私有key及归档。超额会ENOSPC，数据库在另卷。运行前核验文件系统总量及可用空间，宿主可用内存至少4GiB，否则认领前拒绝。云端更大配额、每Task/Session配额、inode/宿主缓存与整体工程cgroup仍待生产验收。
- root安装 `onefde-shared-storage.service`，Docker依赖挂载成功；其ExecStartPost恢复本项目iptables规则。仅维护ONEFDE-SHARED自有链，不清空Docker/其他项目规则。动态Sandbox无restart策略，未知现场不自动重跑。
- control/sandbox/offline_out为internal网络，工程网固定Worker `.2`、代理`.3`；仅Worker可新连Agent8000。工程容器的新连Worker/宿主/控制库/其他目标拒绝，IPv6未启用。API额外local_access网使Docker可发布回环端口；这不授予Sandbox访问权限。
- 代理此阶段**仅允许离线fixture的CONNECT 443**；fixture不是真HTTPS服务或模型。无任意公网出口，未开放DeepSeek/依赖下载。后续接入必须单独验证域名、DNS、元数据/私网拒绝及预算；不要直接换成无限制bridge。
- 当前有本地持久化及摘要复核，没有异机备份；WSL虚拟盘丢失仍可能丢数据。不能据此宣称生产灾难恢复完成。

## 重跑验收

无模型检查会创建标注DEMO的控制记录，HTTP创建Run后始终不认领，并通过所有者cancel结束；它不是Engineering结果，不会进入submitted/accepted。错误/中断遗留的**同标记且从未认领**队列仅通过HTTP取消；任何已认领现场停止并人工核查。

```bash
docker compose --env-file /srv/onefde-local/private/compose.env -f deploy/compose.yaml --profile checks up -d probe
backend/.venv/bin/python deploy/verify_local.py
backend/.venv/bin/python deploy/verify_control.py
backend/.venv/bin/python deploy/verify_recovery.py
docker compose --env-file /srv/onefde-local/private/compose.env -f deploy/compose.yaml --profile checks stop probe
```

Coding Agent 无模型契约/固定验证（宿主 venv，需已同步源码与 Worker 环境变量）：

```bash
export ONEFDE_WORKER_DATABASE_URL="$(cat /srv/onefde-local/private/worker_url)"
export ONEFDE_WORKER_ROOT=/srv/onefde-local/worker
export ONEFDE_WORKER_NETWORK=onefde-local-sandbox
export ONEFDE_WORKER_EXECUTION_MODE=ecs_shared
export ONEFDE_WORKER_SHARED_HOST_CONFIRMED=true
export ONEFDE_WORKER_MODEL_EXECUTION_ENABLED=false
export OPENHANDS_SUPPRESS_BANNER=1 LITELLM_LOCAL_MODEL_COST_MAP=True
backend/.venv/bin/python deploy/verify_coding_agent.py
```

证据写入 `work/coding-agent-no-model.json`（及文档副本）；不调用模型、不认领业务作业。说明见[CA验证](../docs/operations/coding-agent-verification.md)。

## 报价产品 Origin

客户报价页不是 Compose 服务，也不使用 API 的 `8000`/`8002`。在仓库根执行 `python deploy/verify_product_origin.py`；保持打开时加 `--serve`。入口只使用 `http://127.0.0.1:8765/`。步骤见[P4演示](../docs/operations/p4-demo.md)。

`verify_local.py`启动临时宿主监听反例，真实SDK执行命令并耗尽独立Worker盘后删除测试文件；另用受限临时容器触发CPU/内存/PID限制，确认核心服务可用。只在这个独立演示项目运行。JSON在Worker盘 `evidence/`，公开副本须仅复制脱敏结果，原始secret/Session不可发布。

重启恢复另从Windows执行 `wsl --terminate OneFDE`，再打开该发行版终端，等待核心健康后执行verify_recovery与verify_local。不使用全局 `wsl --shutdown`。停止本地服务用compose stop，保留卷；不自动清理源码、产物或Docker缓存。
