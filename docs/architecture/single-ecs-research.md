# 单ECS部署重审：资料与实现差距

2026年11月4日，仅研究与设计。需求来源为用户最新的“一台ECS部署整个OneFDE”指令，取代上一轮“工程物理另机”的MVP方向。选定方案在[ADR0009](ADR/0009-single-ecs-mvp.md)，物理设计在[部署设计](../operations/deployment.md)。下述机制来自官方资料；预算、拓扑和阈值为本项目设计建议，不是上游或ECS实测结论。

## 官方依据与取舍

| 一手来源 | 核对内容 | OneFDE采用/限制 |
| --- | --- | --- |
| [Compose生产部署](https://docs.docker.com/compose/how-tos/production/) | 明确单服务器运行路径，生产配置与开发配置分开 | 选单ECS+Compose；不把本地PG Compose冒充完整生产栈 |
| [Compose服务定义](https://docs.docker.com/reference/compose-file/services/) | CPU/内存/PID、网络、健康检查、secrets及安全参数 | 固定服务声明限额；动态兄弟容器需独立配置，不能依赖Worker的上限 |
| [Docker daemon权限](https://docs.docker.com/engine/security/) | 能控制daemon者可创建任意宿主挂载 | Worker明确为高信任；业务模型与Agent shell不取得Socket，`:ro`不是API只读 |
| [Docker资源限制](https://docs.docker.com/engine/containers/resource_constraints/) | 默认容器无资源上限，OOM可能影响宿主 | 先串行、小预算，create-time配额及准入；4核16GiB是估算并需压测 |
| [Docker防火墙](https://docs.docker.com/engine/network/firewall-iptables/) | 用户过滤规则与Docker转发链、已建立连接的关系 | 分开验证FORWARD/同桥与宿主INPUT；不把internal网络或宿主防火墙名称当完整证明 |
| [bind挂载](https://docs.docker.com/engine/storage/bind-mounts/)、[卷](https://docs.docker.com/engine/storage/volumes/) | daemon宿主决定bind源，持久卷独立于容器生命周期 | Worker使用同绝对宿主路径；Task/Run挂载最小化，持久卷不等于备份 |
| [Compose secrets](https://docs.docker.com/compose/how-tos/use-secrets/) | 按服务挂secret文件 | 平台当前读取环境引用，需可信启动适配；不声称本地Compose自动提供加密保险箱 |
| [OpenHands Sandbox指南](https://docs.openhands.dev/sdk/guides/agent-server/docker-sandbox) | Agent Server容器、RemoteWorkspace与工具执行生命周期 | 复用SDK循环；容器化机制不等于抵抗宿主管理员/Worker失陷/内核逃逸 |
| [固定上游DockerWorkspace源码](https://github.com/OpenHands/software-agent-sdk/blob/ccae18cb897bef7960f210aa3f380b577a84be7c/openhands-workspace/openhands/workspace/docker/workspace.py) | CLI创建容器、宿主回环端口、挂载/会话配置 | 按仓库锁定1.59.0实际安装源码复核私有钩子；不跟随最新指南直接升级 |
| [Caddy HTTPS](https://caddyserver.com/docs/automatic-https) | 证书申请与续期机制 | 明确域名站点和持久证书卷；上线时实际验证域名与可达条件 |
| [PG17 pg_dump](https://www.postgresql.org/docs/17/backup-dump.html)、[文件级备份](https://www.postgresql.org/docs/17/backup-file.html) | 逻辑导出与活库文件直接复制的不同 | dump/restore及角色/产物一致性检查，不tar正在写入的PGDATA冒充一致备份 |
| [ECS规格族](https://www.alibabacloud.com/help/en/ecs/user-guide/instance-families/) | x86规格及通用型核内存比例 | 起步建议4核16GiB，无GPU；型号/地域/报价/费用上限仍待确认，不进行购买 |
| [ECS元数据](https://www.alibabacloud.com/help/en/ecs/user-guide/view-instance-metadata/) | 元数据可含实例身份和访问凭据 | 工程网络明确拒绝100.100.100.200，不能只依赖安全组默认值 |

## 阅读的实际代码与结论

| 文件 | 当前观察 | 对单ECS的影响 |
| --- | --- | --- |
| [Worker入口](../../backend/src/onefde/entrypoints/worker.py)、[配置](../../backend/src/onefde/worker/config.py) | CLI check/once/run/import-profile；模式只有dedicated/local_wsl，默认禁模型 | 需独立ecs_shared模式和生产启动定义；配置供给短作业与运行期Worker分开DB身份，不伪造isolated_host_confirmed |
| [Worker控制器](../../backend/src/onefde/worker/controller.py) | 单消费进程、心跳线程、每次短事务；回执先保存再回填 | 可直接延续单机串行控制，不需要Redis；多角色尚需受控分派适配 |
| [派发领域服务](../../backend/src/onefde/modules/tasks/dispatch.py) | PG认领/租约/归属，失联冻结，不自动换代执行 | 数据库仍是权威状态源，重启不把未知工作当作可重跑 |
| [OpenHands适配](../../backend/src/onefde/infrastructure/runtime/openhands.py) | 冻结快照，固定镜像，私有key与两个挂载；update限额、独立停止核查、归档 | create-time硬化/容器内Worker私有HTTP/在线出口/归档过滤待补；保留SDK loop |
| [开发Compose](../../backend/compose.yaml) | 只有PG及回环端口 | 尚无API/Worker/gateway生产Compose；不能宣称迁移部署只需原文件up |
| [WSL真实环境证据](../operations/evidence/c2-wsl-environment.json) | 实际SDK文件/网络/停止/持久化通过，但无模型/业务Run | 可复用经验，不能代替ECS生产、模型调用或客户交付验收 |

固定镜像实际用户为10001，启动会写入特定目录；no-new-privileges/cap_drop/read-only要通过真实SDK检查。当前SDK可能把受限模型key配置到Agent Server中；MVP不默认新增模型网关，也不宣称shell绝对无法接触模型key。

## 排除的提前建设

不为四个角色建四台机器或四个常驻轮询服务；不新增LLM Router、Kubernetes、Redis/消息集群、MinIO作为MVP前提；不把运行客户软件与执行任意工程代码混为同一个容器。在线出口代理只做网络白名单，不承担模型路由。

当前讨论不更改Task/Run状态语义、报价业务规则、六组角色关系或资料用途权限。产品有后端时按受控运行模板发布，不让Agent提交任意宿主Compose或Dockerfile获得管理权限。
