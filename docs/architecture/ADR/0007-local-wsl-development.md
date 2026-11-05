# C2本地WSL开发执行环境

状态：2026年11月4日用户明确授权实施；仅限本地开发。补充[ADR0003](0003-execution-validation.md)，本地操作约定保留；后续云端MVP拓扑以[ADR0009](0009-single-ecs-mvp.md)为准，不再要求默认另购执行ECS。

## 适用范围

在个人Windows机器上用专用Ubuntu WSL2发行版与Docker Engine验证自有、明确授权的演示任务。首项为简单网页与检查脚本，不接客户资料、不做报价、工作台前端或公网部署。当前只准备环境，禁止调用模型、消费工程作业或开通付费资源。

## 决定

- 独立`OneFDE`发行版、Linux内工作目录、独立Docker daemon和演示控制库；不修改既有Windows开发库或复制其凭据。Backend仍复用同一应用/迁移/Task协议，不开发另一执行器。
- 关闭本发行版Windows磁盘自动挂载和Windows程序互操作；只同步源文件。工程容器只挂载Task工作区与Run Session，容器不取得Docker socket、数据库/所有者/部署凭据。
- 明确`execution_mode=local_wsl`与`local_development_confirmed`；不能把`isolated_host_confirmed`设为true冒充专用节点。默认`model_execution_enabled=false`；`check --environment-only`不消费作业，也不证明模型或费用可用。`once/run`仍检查开关和预算。
- 无模型准备阶段使用internal离线网络并拒绝工程桥到宿主的新连接；只允许宿主发起的Agent Server连接回复。数据库在独立控制网络、端口仅绑定回环；Worker使用无认证表/DDL/建库/超级用户权限的独立身份。
- 复用固定SDK/镜像、CPU/内存/PID/时间限额、私有源码与回执、停止核实和现有评审。DeepSeek接入前另核对模型出口、凭据注入及提供方额度，不通过放开整个内网实现模型访问。

## 限制与完成证据

WSL发行版共享宿主虚拟化基础设施，可信Worker拥有本发行版Docker管理权限；关闭自动挂载不构成抵抗宿主管理员或容器逃逸的安全边界。仅用于受控开发，不作为客户隔离或生产安全验收。云端MVP采用同ECS受限容器和可信Worker，实际验收要求见ADR0009；更强隔离按实际风险重访。

环境完成须有实际依赖/容器/挂载读写/资源/网络拒绝/停止/持久化及受限DB检查。环境通过后C2真实工程仍未完成；只有后续真实模型经Backend→Worker执行、固定产物回填和所有者评审，才记录对应功能退出条件完成。专用节点验证单列。

操作与证据见[本地WSL手册](../../../backend/local-wsl/README.md)及[C2验证](../../operations/c2-verification.md)。
