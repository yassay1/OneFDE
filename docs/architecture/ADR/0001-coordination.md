# FDE 与程序协调层的职责划分

状态为纳入推荐技术基线。已接入范围以[实施计划](../../development/implementation-plan.md)为准。2026 年 11 月 4 日修订持续协作设计；具体框架见 [ADR 0004](0004-platform-stack.md)。

## 背景

FDE 必须理解客户证据、制定交付方案并组织工程工作。Router 源码研究表明，接单路由与任务运行状态需要程序约束；把它们全部交给一个模型会增加重复派发和上下文混乱风险。

## 推荐

FDE 负责业务语义、能力取舍与任务拆分；Coordinator 负责权限、幂等、版本、依赖、唯一活动运行和结果归属。一个业务控制后端先承载该协调模块，项目内先串行执行，不新增第五个常驻 Orchestrator LLM。

Coordinator 的具体职责拆为 Task Service（持续工作、输入、分配、评审）和 Dispatcher（运行与派发）；Runtime 复用 OpenHands。短检索/咨询直接工具或有界角色调用，长期交付使用 Task。明确目标角色与 Task 时直接走程序，不增加一次 LLM 路由。

同一未关闭交付中延续 Task；补充保存 pending，由所有者采用成新规格后再执行。工程成果进入 review，接受后才完成 Task。需要业务输入时结束本轮 Run、确认无写入并保存现场后释放执行名额，回答后新 Run 可复用可信 Session/代码。此项替代 11 月 3 日“blocked Run 保留名额并继续同 Run”的设计；故障失联仍保留 interrupted 占用。

## 比较与代价

全部由 FDE 管理组件少，但状态恢复依赖会话记忆；独立 Orchestrator LLM 入口统一，但与 FDE 重复理解和拆任务。混合方案需要先定义 Task/Run 契约，其代价小于复制一套完整多 Agent 调度系统。

A2A 区分消息/任务且终态不重开；Odoo 允许已关闭业务任务重开。两者边界不同，首版选择 review 前可持续修改、关闭后建关联任务，避免重开导致旧评审/授权失效的额外机制。吸收状态与版本原则，不实现 A2A 传输协议或 Odoo 全套可配置阶段。[A2A](https://a2a-protocol.org/dev/topics/life-of-a-task/)、[Odoo](https://www.odoo.com/documentation/19.0/applications/services/project/tasks/task_stages_statuses.html)

## 验证与重访

2026年11月4日补全：Knowledge作为横向知识支持服务Business/FDE/Engineering，不成为第四个业务负责人或权限路由器。四角色六组关系见[PRD](../../product/PRD.md)，知识服务、能力资产、业务来源及公开用途边界见[约定](../../../capability-library/README.md)；工程事实交接不等于销售直接派工程。此次细化不增加Agent数量、状态机或中间件。

阶段 C 检查重复请求、并发认领、迟到结果和恢复；阶段 D 检查多任务集成。出现多个独立业务团队或明显的跨项目路由瓶颈时，再评估独立路由 Agent。对象及状态以[数据模型](../data-model.md)为准。

2026 年 11 月 5 日报价试点按已登记 Case 读取持久交接、客户答复和 Run 结果。用事务内阶段回执恢复，保留既有工程派发记录及全局槽。实现边界见[数据模型](../data-model.md#报价自动售后试点状态)。

2026 年 11 月 6 日通用 FDE 首版将工具选择交给兼容模型。Backend 按原 Case 的消息水位与 Task 版本唤醒工作，工具写入与回执同事务提交，租约失效后从业务记录重建。模拟权限在受信登记和工程认领时校验。评审建议保存在 FDE 工作中，正式评审沿用原 Task 命令。 [运行与验收](../../operations/fde-agent-v1.md)
