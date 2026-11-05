# Coding Agent 上游参考与适配依据

2026年11月4日查阅官方资料与固定源码，服务于[Coding Agent设计](coding-agent.md)。机制存在不等于OneFDE接入成功；Aider/mini-swe-agent仅作为设计参考，未安装或复制代码，在线文档按本次观察记录，实施前重新核对。

## 采用范围

| 来源 | 核对到的机制 | 本项目取舍 |
| --- | --- | --- |
| [OpenHands SDK](https://docs.openhands.dev/sdk) | 面向工程Agent的Python接口、工具与远程运行机制 | 延续现有SDK，不迁入整套上游产品/UI，不重写循环 |
| [固定Agent源码](https://github.com/OpenHands/software-agent-sdk/blob/ccae18cb897bef7960f210aa3f380b577a84be7c/openhands-sdk/openhands/sdk/agent/agent.py) | 模型/事件/工具执行和condenser处理 | 执行能力交给SDK，自有代码只处理业务及适配边界 |
| [固定AgentContext](https://github.com/OpenHands/software-agent-sdk/blob/ccae18cb897bef7960f210aa3f380b577a84be7c/openhands-sdk/openhands/sdk/context/agent_context.py) | system_message_suffix、Skill加载选项 | 角色规则通过扩展加入，资料和开发约定由可信装配层筛选 |
| [固定DockerWorkspace](https://github.com/OpenHands/software-agent-sdk/blob/ccae18cb897bef7960f210aa3f380b577a84be7c/openhands-workspace/openhands/workspace/docker/workspace.py) | 容器创建、远程Agent Server、挂载与网络配置 | 复用机制；创建时硬化、配额、路径与独立停止证据归OneFDE，详见部署设计 |
| [自定义工具指南](https://docs.openhands.dev/sdk/guides/custom-tools) | Action/Observation/Executor与ToolDefinition扩展模式 | 后续接窄范围知识查询；鉴权/用途检查归Backend，工具注册不授予权限 |
| [Aider仓库地图](https://aider.chat/docs/repomap.html) | 提供重要文件/符号及依赖相关性，在token预算内选择上下文 | 先按需定位文件；实际出现规模瓶颈后才评估地图，当前不引入图排序/索引系统 |
| [Aider检查反馈](https://aider.chat/docs/usage/lint-test.html) | 执行项目lint/test并把失败交给模型修复 | 借鉴反馈闭环；命令/验收按本项目任务确定，最终证据由自有适配固定 |
| [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) | 简洁循环、shell操作与线性历史，适合观察模型行为和执行轨迹 | 参考其简化原则，不叠加第二套Runtime；其工具/环境选择不直接成为本项目权限策略 |
| [SWE-agent现状](https://github.com/SWE-agent/SWE-agent) | 官方建议默认考虑mini-swe-agent | 保留为研究背景，不另接旧框架或其评测设施 |

## 固定版本与最新指南的差异

执行依赖继续使用ADR0006的SDK/workspace/tools 1.59.0及固定镜像；本轮不升级依赖。[固定AgentBase](https://github.com/OpenHands/software-agent-sdk/blob/ccae18cb897bef7960f210aa3f380b577a84be7c/openhands-sdk/openhands/sdk/agent/base.py)已有上下文扩展和可选condenser，启用时仍须复核固定类型、参数与预算。

最新[结构化输出指南](https://docs.openhands.dev/sdk/guides/structured-output)展示工具response_schema；[固定FinishTool](https://github.com/OpenHands/software-agent-sdk/blob/ccae18cb897bef7960f210aa3f380b577a84be7c/openhands-sdk/openhands/sdk/tool/builtins/finish.py)的create拒绝参数，FinishAction只有message。因此本设计继续用Finish消息承载JSON提案并在可信端验证；未来专用类型化工具或SDK升级另行复核，不能把最新示例写成当前已可用接口。

最新指南的工具构造示例与本仓库register_tool/TerminalTool接线也有差异；实施以锁文件、固定发布源码和现有绑定测试为准。上下文压缩虽然上游可用，当前适配condenser=None，压缩摘要不能取代Task事实。

## 本地实现差距

下表是本轮读取源码时的快照。检查期间发现后端存在并发修改，本文不替其他实施任务声明完成或失败；实际实现进度以各自验证记录为准，本轮只维护工程设计。

| 事实来源 | 本轮核对结果 | 待补设计 |
| --- | --- | --- |
| [Run创建](../../backend/src/onefde/modules/tasks/commands/runs.py) | 固定spec/inputs/actor/角色/模型/config/permissions/`engineering`清单 | Git基准仍后置；真实模型未测 |
| [执行端口](../../backend/src/onefde/core/execution.py) | ExecutionRequest/ExecutionReport隔离SDK与领域服务 | 检查覆盖在proof；业务模块不导入SDK |
| [OpenHands适配](../../backend/src/onefde/infrastructure/runtime/openhands.py) | AgentContext角色后缀；命令证据；自动检查匹配；固定验证容器 | 真实模型修复循环与费用封顶待测 |
| 同一适配的工作区/提交 | 比对/受控恢复；源码排除bash_events；验证后源码成员不变才可submitted | Git diff/构建产物目录约定可继续加强 |
| [Worker手册](../../backend/WORKER.md)及[CA验证](../operations/coding-agent-verification.md) | 无模型契约与固定验证已实测 | 真实模型小任务、费用/请求计数与停止延迟仍需实测 |

工具日志只证明执行事实，测试样例还须对应业务规则；上游benchmark分数不作为本项目模型/客户交付验收。新增业务行为、数据范围与工程成果均按本仓库需求、权限及证据判断。
