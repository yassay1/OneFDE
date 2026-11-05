# C2独立Worker与固定SDK边界

状态：2026年11月4日控制/适配代码已实现并测试；本地Linux无模型环境已验证，真实模型工程尚未执行，C2尚未达到退出条件。延续[隔离ADR](0003-execution-validation.md)及[模块结构](0005-backend-code-structure.md)。

## 决定

单ECS目标按[ADR0009](0009-single-ecs-mvp.md)更新；本ADR的独立Worker指进程/服务边界，不要求物理另机。本地已实现ecs_shared模式、同名宿主路径/私网认证/create-time安全参数及无模型standby；结果见[单机验收](../../operations/single-ecs-verification.md)。生产在线出口/配额等缺口保留；不能用旧专用节点确认开关代替共享模式确认。

本地开发例外以用户授权的[ADR0007](0007-local-wsl-development.md)为准；不通过专用节点确认开关冒充生产隔离，默认禁止模型执行。

Worker作为独立受信任进程，复用tasks公开领域入口；认领、租约、停止意图和结果持久化由PostgreSQL协调，不加Redis或通用工作流。SDK在基础设施适配层，领域模块不导入OpenHands。API不等待模型，不提供公共认领/假成功回调。

对dispatch_jobs做增量迁移。认领owner/token/租约防止旧Worker覆盖新事实；租约过期是现场未知，进入interrupted并保持占用，不能当作重执行许可。结果回执先落私有存储，再在同一事务更新Run/Task/产物/事件与作业摘要。此机制提供幂等回填，不声称任意外部副作用恰好一次。

## 借鉴与适配

核对发布 `v1.59.0`、提交 `ccae18cb897bef7960f210aa3f380b577a84be7c` 后，SDK/workspace/tools用精确版本可选extra锁定，不把API运行强制绑定工程依赖。Agent Server Python镜像固定manifest digest；不跟踪latest，不复制Agent Loop。

- 沿用上游 [DockerWorkspace](https://github.com/OpenHands/software-agent-sdk/blob/ccae18cb897bef7960f210aa3f380b577a84be7c/openhands-workspace/openhands/workspace/docker/workspace.py) 的本地容器、回环端口、RemoteConversation和终端/文件编辑工具。仅挂载任务工作区与当前Run Session，明确白名单转发环境；不开放额外端口。
- [RemoteConversation](https://github.com/OpenHands/software-agent-sdk/blob/ccae18cb897bef7960f210aa3f380b577a84be7c/openhands-sdk/openhands/sdk/conversation/impl/remote_conversation.py)不使用传入的本地persistence_dir。按[Agent Server配置源码](https://github.com/OpenHands/software-agent-sdk/blob/ccae18cb897bef7960f210aa3f380b577a84be7c/openhands-agent-server/openhands/agent_server/config.py)设置OH_CONVERSATIONS_PATH并挂载私有路径，另存其加密密钥。每Run新Conversation，Task/Run不依赖SDK Session生命周期。
- SDK暂停只约束Agent，cleanup未检查docker stop返回值。OneFDE独立停止并核实容器不存在/不运行；未知时冻结。为捕获健康检查初始化失败时的容器，窄范围覆写 `_wait_for_health` 并读取 `_container_id`；这是对固定SDK版本的明确耦合，升级必须复核，绑定测试覆盖此分支。
- SDK没有本切片所需的直接CPU/内存参数；ecs_shared窄覆写`_start_container`，创建时设置限额/权限，启动前登记ID，默认只读根，仅有界tmpfs允许必要写入与解包执行。旧模式保留创建后、发起Agent前设置限制。使用SDK迭代/费用上限和零重试，不自建推理循环；提供方配额/实际调用计数/费用精度仍需真实接入验证。
- 先用受限本地不可变blob完成真实文件保存与摘要校验；不在缺少对象存储凭据时宣称S3接通，不提前实现下载接口。成功终端退出与固定源码是最小工程证据，业务接受仍由现有评审决定。

上游[官方容器示例](https://docs.openhands.dev/sdk/guides/agent-server/docker-sandbox)和[会话持久化](https://docs.openhands.dev/sdk/guides/convo-persistence)提供机制，OneFDE增加租约归属、停止证据和业务事务边界。操作/限制造成的真实差异见[Worker手册](../../../backend/WORKER.md)，检查及未执行项见[C2验证](../../operations/c2-verification.md)。

## 后续工程设计入口

Engineering上下文、工具、验收证据、固定版本验证及续作的推荐设计见[Coding Agent](../coding-agent.md)，上游差异见[参考依据](../coding-agent-research.md)。沿用本ADR的固定依赖和执行端口，不重写Agent Loop；C3/D补充项不倒写为C2已实现，也不扩大当前最小真实接入冒烟的前置条件。本轮仅文档，无SDK升级或接口变化。
