# OneFDE 桌面 Web 前端设计

状态：2026-11-08 晚间收尾时，六页已接当前运行契约，不再是当日上午的“仅审计、未开发”。上午审计原文保留在下文和[实施记录](implementation.md#产品实现收尾2026-11-08)。运行契约现为 **46** 项已实现 HTTP 操作，另有 1 项 planned 下载；比上午审计的 44 项多出 `pageFdeWork` 与 `getFdeWork`。历史 F1—F6 仍只证明当时范围。

已接上的能力包括 Case 服务端筛选、FDE 分页工作历史和单条读取、Office 待办里的项目上下文、Engineering 历史只读与固定 Diff、Knowledge 按用途隔离。普通 FDE Work 仍待消费者，模型修订不等于 Worker 在线。2026-11-08 的付费工程请求超过授权，不能写成合规验收。

| 需要了解什么 | 阅读 |
| --- | --- |
| 四角色职责、核心对象、逐页线框、交互与成熟产品取舍 | [design.md](design.md) |
| 每个主要模块的字段/API/生成/持久化/更新/操作/权限/状态、A/B/C/D与代码证据 | [api-mapping.md](api-mapping.md) |
| 状态归属、分页与终态刷新、上下文及权限边界 | [architecture.md](architecture.md) |
| 当前前端差异、W0—W5分期与可检查验收；历史F0—F6证据 | [implementation.md](implementation.md) |

当前行为以代码和[能力映射](api-mapping.md)为准。上午审计时的差异表仍可对照，其中“输入采用未挂载、44 项操作”已被同日后续实现取代。YAML 产物下载仍为 planned。

产品范围以[PRD](../product/PRD.md)为准。Office/项目中心本轮仅检查导航与上下文，不重新设计。已有四角色场景来源见[美术接入记录](../operations/frontend-art-verification-20261107.md)；参考图与engineering-preview模拟原型不授予开发许可，也不证明后端能力。
