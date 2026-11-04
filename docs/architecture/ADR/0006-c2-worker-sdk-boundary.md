# C2独立Worker与固定SDK边界

状态：2026年11月4日控制/适配代码已实现并测试；真实Linux/模型冒烟阻塞，C2尚未达到退出条件。延续[隔离ADR](0003-execution-validation.md)及[模块结构](0005-backend-code-structure.md)。

## 决定

Worker作为独立受信任进程，复用tasks公开领域入口；认领、租约、停止意图和结果持久化由PostgreSQL协调，不加Redis或通用工作流。SDK在基础设施适配层，领域模块不导入OpenHands。API不等待模型，不提供公共认领/假成功回调。

对dispatch_jobs做增量迁移。认领owner/token/租约防止旧Worker覆盖新事实；租约过期是现场未知，进入interrupted并保持占用，不能当作重执行许可。结果回执先落私有存储，再在同一事务更新Run/Task/产物/事件与作业摘要。此机制提供幂等回填，不声称任意外部副作用恰好一次。

## 借鉴与适配

核对发布 `v1.59.0`、提交 `ccae18cb897bef7960f210aa3f380b577a84be7c` 后，SDK/workspace/tools用精确版本可选extra锁定，不把API运行强制绑定工程依赖。Agent Server Python镜像固定manifest digest；不跟踪latest，不复制Agent Loop。

- 沿用上游 [DockerWorkspace](https://github.com/OpenHands/software-agent-sdk/blob/ccae18cb897bef7960f210aa3f380b577a84be7c/openhands-workspace/openhands/workspace/docker_workspace.py) 的本地容器、回环端口、RemoteConversation和终端/文件编辑工具。仅挂载任务工作区与当前Run Session，明确白名单转发环境；不开放额外端口。
- [RemoteConversation](https://github.com/OpenHands/software-agent-sdk/blob/ccae18cb897bef7960f210aa3f380b577a84be7c/openhands-sdk/openhands/sdk/conversation/impl/remote_conversation.py)不使用传入的本地persistence_dir。按[Agent Server配置源码](https://github.com/OpenHands/software-agent-sdk/blob/ccae18cb897bef7960f210aa3f380b577a84be7c/openhands-agent-server/openhands/agent_server/config.py)设置OH_CONVERSATIONS_PATH并挂载私有路径，另存其加密密钥。每Run新Conversation，Task/Run不依赖SDK Session生命周期。
- SDK暂停只约束Agent，cleanup未检查docker stop返回值。OneFDE独立停止并核实容器不存在/不运行；未知时冻结。为捕获健康检查初始化失败时的容器，窄范围覆写 `_wait_for_health` 并读取 `_container_id`；这是对固定SDK版本的明确耦合，升级必须复核，绑定测试覆盖此分支。
- SDK没有本切片所需的直接CPU/内存参数，创建容器后、发起Agent前设置Docker限制。使用SDK迭代/费用上限和零重试，不自建推理循环；提供方配额/实际调用计数/费用精度仍需真实接入验证。
- 先用受限本地不可变blob完成真实文件保存与摘要校验；不在缺少对象存储凭据时宣称S3接通，不提前实现下载接口。成功终端退出与固定源码是最小工程证据，业务接受仍由现有评审决定。

上游[官方容器示例](https://docs.openhands.dev/sdk/guides/agent-server/docker-sandbox)和[会话持久化](https://docs.openhands.dev/sdk/guides/convo-persistence)提供机制，OneFDE增加租约归属、停止证据和业务事务边界。操作/限制造成的真实差异见[Worker手册](../../../backend/WORKER.md)，检查及未执行项见[C2验证](../../operations/c2-verification.md)。
