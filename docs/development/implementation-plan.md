# OneFDE 分阶段实施计划

本计划按可交付结果推进，不按比赛期限倒排。2026 年 11 月 4 日已将协作调研同步到阶段 B 推荐文档；已完成 C0+C1b 持久控制、本地沙盒与一次真实网页工程冒烟。黑客松 P0—P3 与 P4 本地 Origin 已落地；真实模型报价 Run、薄工作台页面与公网部署仍未完成。先实现当前纵向切片，不另建调度框架预研项目。

范围依据见 [PRD](../product/PRD.md)，首个具体案例见[模拟报价项目](../../engagements/demo-supplier-quotes/brief.md)；参赛切片见[黑客松实施方案](../product/hackathon-proposal.md)。技术推荐以[架构](../architecture/architecture.md)和 ADR 为准：React/Vite、FastAPI、PostgreSQL、OpenHands/DockerWorkspace、Compose/Caddy；实际模型、账号与域名为接入配置项。

最新研发优先级：用户明确先后端，前端之后单独设计。P0—P4 的本地切片已完成；下一动作是薄三入口页面，或获授权后用真实 Engineering Run 替换报价案例的确定性回填。当前不初始化完整工作台 UI 依赖。既有前端设计作为行为参考，视觉和页面实现后置。

最新MVP部署基线：用户指定单台阿里云ECS+Docker Compose，一体化承载公司站、工作台、API/PG/Worker、四角色Runtime、OpenHands工程容器及客户产品；同机按服务/权限/网络/资源分开，见[ADR0009](../architecture/ADR/0009-single-ecs-mvp.md)。后续用户已授权S1/S2：本地Compose与ecs_shared适配、真实无模型隔离/资源及重启验证已完成；未购买云资源或公网部署，操作见[Compose手册](../../deploy/README.md)。下方早期“工程物理另机”的进度条目保留为历史，不再是当前门槛。

## 阶段与退出条件

| 阶段 | 当前状态 | 工作范围 | 退出条件 |
| --- | --- | --- | --- |
| A 需求与文档基线 | 文档初稿完成，已检查 | 原样归档产品定义；写 PRD、入口与 Agent 约定；明确项目/能力记录；列测试场景与首个模拟案例 | 平台与客户软件边界清楚；当前目标有编号与可观察条件；规则、提案和未知项分开；文档内部链接有效 |
| B 关键流程与工程方案 | 推荐文档基线完成；C0+C1a 已实施，其余待实施 | 产品交互、物理映射、架构、最小 OpenAPI、部署设计与四条 ADR | 推荐组合、状态、字段与环境边界相互一致；接入前补齐账号、固定版本和限额 |
| C 最小持续工程工作切片 | C0+C1b完成；C2本地真实网页冒烟已通过；C3工程契约/固定验证已落地；P1薄FDE受控工具与交付详情API已落地，薄页面后置 | 短接入冒烟后实现 Task/输入/Run/评审；先以创始人代行所有者，再连接最薄 FDE 受控工具 | 同 Task 能提问、答复、新 Run 续作、提交、要求修改与接受；自有状态路径有证据，不重复证明 SDK 基础能力 |
| D 首个软件交付闭环 | 报价产品v1.1、样例检查与FDE平台控制链（确定性Run回填）已通过；本地 Origin `127.0.0.1:8765` 已检查。真实模型Engineering与公网发布未做 | 按已确认模拟规则实现报价工具，连接多个任务的前置产物、集成与部署，完善实际操作说明 | 指定版本可从交付入口访问，约定样例得到预期结果，信息不足项明确标记；代码、运行、检查与入口可追溯 |
| E 知识支持与再次复用 | P3最小切片已落地：资产检索/权限与第二项目再检查。无模型循环、无向量库 | Knowledge向Business/FDE/Engineering提供支持，接收三者反馈，整理少量候选资产；用第二组需求复用 | 三类请求/来源/用途边界可追溯；实际使用版本、适配和重新检查有证据，不以总结代替复用 |
| F 真实试点校准 | 尚无试点 | 找到门店，取得经授权脱敏资料，核对流程、规则、输出与实际反馈 | 真实资料与演示假设分开；能据实际使用修订需求与能力边界，不将模拟验算当作经营价值证明 |

## 阶段 A 本次文档清单

阶段 A 完善以下内容，正式产品定义原样保存。阶段 B 已补推荐架构、物理映射、最小 OpenAPI、部署设计与四条 ADR。真实命令和运行证据随实现补充。

| 文档 | 本轮内容 |
| --- | --- |
| `docs/product/product-definition.md` | 原产品定义按原字节归档，保留其中的原始版本和状态 |
| `docs/product/PRD.md` | P01—P10 需求、角色交接、完成条件、范围与待确认项 |
| `README.md`、`AGENTS.md` | 当前项目状态、文档入口、按任务读取资料和完成证据约定 |
| `engagements/README.md` | 特定交付上下文、任务与运行、资料边界及维护责任 |
| `engagements/demo-supplier-quotes/brief.md` | 用户已确认的模拟比较边界、样例提案、缺口与当前证据状态 |
| `capability-library/README.md` | 分类、最低条目内容、验证状态、来源和复用规则 |
| `docs/operations/testing.md` | 可观察的验证场景、需求关联、执行证据要求；未执行结果 |
| 本文件 | 阶段、依赖、退出条件和实际进度 |

## 阶段 B 的准备顺序

1. 已澄清模型不锁定 MiMo，采用兼容 API 的配置式接入；用户授权推荐环境，优先验证独立 Linux 容器工作区。执行前补可用账号、固定模型/SDK/镜像版本和运行限额，不要求用户先选框架。
2. 画出一次请求从 Engagement 到任务、运行和结果的关键交互。完成标志是新增、补充、取消、重试和待业务澄清都有可辨别行为。
3. 定义最小 Task/Run、Session 和工作区关系，明确输入与产物版本、当前执行代次、幂等及前置依赖。完成标志是单任务执行与多任务交接可以检查，不依赖会话记忆。
4. 比较模型适配、工程执行、隔离、数据存储与部署候选；需要时记录少量 ADR。完成标志是关键选择说明依据、代价、确认状态和后续验证方式。
5. 将当前工程验证切片细化到可执行任务、接口与检查。完成标志是阶段 C 可直接按明确范围验证，而非先搭完整四中心界面。

混合协调、Task/Run 分离与一个活动工程 Run 是首版推荐。FDE 负责业务诊断和方案；程序协调层负责一致性，不新增第五个常驻 Agent。Session 只在同任务且可信时复用，物理和权限边界由部署设计明确。

本阶段初稿见[关键交互](../design/design.md)、[架构](../architecture/architecture.md)、[数据模型](../architecture/data-model.md)及架构中的 ADR 入口。后续文档工作按 `planning-with-files-zh` 与 `writing-for-agents` 进行，替代此前 `documents` 规范；历史产出作为当时记录保留。

## 阶段 C 接入与首个开发切片

Engineering执行的直接复用、自有适配、上下文、检查证据与续作按[Coding Agent设计](../architecture/coding-agent.md)细化；[上游参考](../architecture/coding-agent-research.md)区分固定SDK与最新指南。新增CA01—CA10见[测试场景](../operations/testing.md#coding-agent细化验收)，均为待执行。先用现有适配完成C2真实小任务，再按C3/D补上下文/结果契约和固定源码验证，D/E接知识查询；repo map、压缩、多Agent按实际瓶颈后置。本轮只更新设计，不实施这些切片，不新增C2冒烟前置项目。

### 实施顺序

C0、C1a与C1b持久控制已完成；C2 Worker/SDK及本地WSL环境已实现，真实模型工程和薄FDE仍未完成。C1b命令与证据见 [验证记录](../operations/c1b-verification.md)。实际命令见 [后端 README](../../backend/README.md)，检查证据见 [验证记录](../operations/c0-c1a-verification.md)。

| 顺序 | 具体工作 | 完成标准 |
| --- | --- | --- |
| C0 后端工程起点（已完成，本地验证） | backend、uv 锁、配置样例、PostgreSQL 开发/测试环境、Alembic、pytest 与最小 CI 配置；远程 CI 未运行，SDK后在C2固定安装 | 后端启动/迁移/检查命令真实可用，配置与密钥分开；不初始化 frontend/pnpm 或 UI |
| C1 控制持久化（C1a+C1b 已完成，本地验证） | 已有迁移、认证、Engagement、Task/TaskInput/版本、Run/待派发状态、轻量评审/事件与幂等；执行消费者在C2扩展 | 导出 OpenAPI；输入保存/应用分开，版本、回复归属、评审证据和认证边界可检查 |
| C2 一次工程执行（本地真实模型冒烟已通过） | dispatch_jobs认领/租约/停止确认/回填、独立Worker、固定SDK及私有源码保存；本地WSL/Compose与DeepSeek出口已实测；2026-11-04 网页小任务真实改文件/检查/归档/验证/接受，见[CA验证](../operations/coding-agent-verification.md) | 本地退出条件已满足；云端隔离与提供方费用硬封顶仍待验收，不能用本地冒烟替代 |
| C3 持续协作后端（契约/固定验证/薄FDE工具已落地） | 工程上下文/结果契约、工作区比对、固定源码验证已实现；CA02本地真实网页冒烟与接受已有证据，见[CA验证](../operations/coding-agent-verification.md)；P1新增`modules/fde`受控工具与`/delivery`详情API（无模型循环）；薄页面与报价业务后置 | 同Task控制多轮已有证据；CA02/CA04/CA05/CA07/CA10本地适用项通过；FDE工具白名单/跨项目拒绝有测试；未采用输入不混入快照；提交不自动完成Task |
| C4 单ECS部署适配（本地S1/S2完成，生产待实施） | 本地已实现Compose、ecs_shared、动态容器硬化、路径/离线网络/资源准入与恢复验证；生产镜像构建/在线模型出口及各角色按授权推进，不增四个常驻服务 | 按[单ECS计划](../operations/single-ecs-verification.md)完成S1—S3/E01—E07；实际云机购买/部署仍需后续明确授权 |
| D1 交付上下文 | 完善FDE诊断/能力取舍与Business交接；准备受控资料/资产检索，已有资料时连接最薄Knowledge咨询 | Business可用获准案例/能力依据，FDE/Engineering可直接咨询；资料权限和六组关系不被入口遗漏，无结果如实返回 |
| D2 报价交付 | 确认模拟字段、换算/精度与导出规则后，先本地开发独立浏览器端工具；连接实际前置产物依赖 | 本地构建/检查及固定产物可追溯，不以本地预览代替部署交付；不补猜业务规则 |
| D3 单ECS一体化与受控发布（待授权实施） | 网站/工作台与四角色按切片完成后，与Backend/PG/Worker/Sandbox和客户产品在同ECS部署；阶段/资源/域名/维护条件见[单ECS计划](../operations/single-ecs-verification.md)S4—S6 | E08—E11实际访问、认证/跨服务边界、回退/备份与资源检查通过；停止工程执行后产品可用。未购买/未发布时P08/V08保持未执行 |
| E 能力与再用 | 完成三角色知识支持/反馈、候选整理与版本；Business获准案例使用，FDE/Engineering在第二组需求采用 | 经营用途/公开授权及方案/工程复用分别有证据；再决定向量检索或复杂资产管理 |

首个 [OpenAPI](../architecture/openapi.yaml) 只覆盖 C 的工程纵向切片。C 尚未实现依赖时，对非空 dependencies 明确报错；D 实现后启用，不能静默忽略。`queue` 表示准备排队，不自动执行；由创始人或获授权的 FDE 显式 `start`。C 初期先由创始人代行，接角色工具后可在原授权范围内由 FDE 发起后续命令，不要求每个内部步骤都额外人工审批。自动事件唤醒与通用 DAG 调度后置。

协作契约已升为 0.2：包含输入、输入应用、轻量评审和任务事件；薄 FDE 的对话入口在 C3 实现前按选定交互补接口，不把当前 YAML 描述成完整四角色通信协议。先让创始人代行 FDE 检查持久闭环，再接角色化 Runtime，避免持久控制和模型效果混在一起排错。业务等待是 Task 的状态，不要求父 FDE 会话一直挂起。

本轮不引入 Redis/BullMQ、Temporal/LangGraph、SSE 或自研 ReAct；也不新建独立 Assignment/Decision/Opportunity 子系统。出现实际多消费者、并发或实时体验瓶颈时，以对应证据重访，不以图中出现概念作为安装依赖的理由。

### 后端第一项开发任务

先做 C0 + C1a：FastAPI/Pydantic 配置与启动、PostgreSQL/SQLAlchemy/Alembic、单账号 Cookie/CSRF、Engagement 和 draft 工程 Task 的创建/查询，以及相关幂等/输入校验。只迁移当前切片所需表，Run/输入/评审在下一项 C1b 中补齐，不要求首个任务实现整个数据模型。

首个完成标准：能按实际 README 命令启动和迁移；用HTTP创建项目及owner=fde/executor=engineering的草稿任务，重启后可查回；未认证/错误CSRF被拒绝；重复请求不重复创建；测试使用独立PostgreSQL测试库；Pydantic导出的已实现接口与当前契约范围一致，未来路径不得冒充已实现。不能以一个health接口或一批空模块算完成。

C1b 再补持续 TaskInput、版本/评审/Run与作业状态，用确定性执行适配检查自有事务、重复和失败路径；C2接真实OpenHands/DockerWorkspace；C3接最薄FDE与同Task多轮工作。确定性适配只作测试，不作为实际Engineering完成证据。没有模型账号不阻塞C0/C1。

Skill 是辅助当前开发 Agent 的工作流程，不是 OneFDE 产品内四角色 Runtime。现有 planning-with-files-zh 管进度，writing-for-agents 在修改仓库约定时使用；调试/完成检查类外部Skill按需选择，不把安装大套流程或前端Skill作为开工前置。

### 接入与针对性检查

复核上游官方源码、示例和真实模型集成测试后，将此前独立前置验证计划收窄。OpenHands 的工具执行、工作区和持久化属于已有能力，直接参考上游实现；只在实际接入时做一次短冒烟。OneFDE 自有功能的测试随开发进行，不要求在代码不存在时另做完整验证项目。C0+C1a 的实际运行见验证记录；下表的模型与执行检查均未执行。

| 编号 | 安排与范围 | 完成证据与失败处理 |
| --- | --- | --- |
| C01 | 与 C02 合并：实际接入选定模型时，采用官方示例跑一次含工具往返的小任务；仅对自定义适配或不兼容项追加检查 | 证明当前端点/凭据/配置可用即可，不重建厂商模型评测、全协议或所有模型的测试矩阵 |
| C02 | 复用官方 DockerWorkspace 示例，确认当前宿主和工作区能执行该小任务，并保存结果 | 直接采用上游工具；按实际配置核对挂载、凭据、持久路径和资源限制，不另写通用执行器测试平台 |
| C03 | 开发首个 Coordinator 切片时，检查自有幂等、当前 Run 归属、取消和失败记录 | 用针对性单元/集成测试覆盖自己新增的逻辑；非所有边界都依赖真实模型调用 |
| C04 | 首版保留基本持久化、失联不误报成功和恢复前核查；完整崩溃/网络故障注入后置 | 在持久化和恢复功能实现时检查实际配置；深度恢复不作为首次功能开发的前置门槛，涉及真实发布前检查副作用重复风险 |
| C05 | 在报价交付开发中检查实际需要的任务依赖与产物版本；复杂 DAG、并发与广泛失效传播按需后置 | 用真实业务切片的输入输出验证集成，不先建设通用编排器再做报价工具 |

首轮建议配额为一个活动工程 Run、每 Run 最多 15 分钟、最多 20 次模型请求、最多 2 次暂态自动重试且计入总调用数。这是小切片的推荐起点，不是完整开发任务的永久限制；实际验证前须在配置中落实、记录费用上限或可用额度，不能在无界限状态下调用收费服务。

应用框架和持久化方案可根据需求、官方支持与团队维护成本先确定，不必等所有验证完成。进入实现时先接入成熟能力并跑一个小任务，再边开发首个功能边检查自有逻辑。只有自定义协议适配、执行环境不受支持或成本/隔离存在关键未知时，才安排有明确退出条件的专项试验。没有可用账号或宿主时记录接入尚未执行，不把上游成熟能力重新标为技术未知。

参考 [OpenHands 集成测试说明](https://github.com/OpenHands/software-agent-sdk/blob/main/tests/integration/README.md)、[文件修改测试](https://github.com/OpenHands/software-agent-sdk/blob/main/tests/integration/tests/t01_fix_simple_typo.py)、[DockerWorkspace 官方示例](https://docs.openhands.dev/sdk/guides/agent-server/docker-sandbox)。上游存在测试不等于本项目的具体配置已经运行通过。

## 需求到证据的关联

下表直接关联需求与检查，不另建独立追踪矩阵。C0+C1a 仅提供 P02 项目基础持久化、P05 草稿与 P07 HTTP 幂等子集证据，见验证记录；下表完整需求仍未验收，后续添加具体任务/Run 与产物链接。

| 需求 | 首次验证阶段 | 检查场景 | 当前执行证据 |
| --- | --- | --- | --- |
| P01 | C/D | V01 线索与材料 | 未执行 |
| P02 | C | V02 项目持续上下文 | 未执行 |
| P03 | B/D | V03 方案与未知项 | 未执行 |
| P04 | D/E | V04 策略与资产版本 | 未执行 |
| P05 | B/C/D | V05 多任务交接 | 未执行 |
| P06 | C/D | V06 真实工程与比较检查 | 未执行 |
| P07 | C | V07 重复、取消与恢复 | 未执行 |
| P08 | D | V08 部署与访问 | 未执行 |
| P09 | D/E | V09 反馈与候选资产 | 未执行 |
| P10 | E | V10 第二次复用 | 未执行 |

检查定义见[测试与验收场景](../operations/testing.md)。研发任务复杂到需要独立上下文时才在 `tasks/` 拆文件；客户工程任务归对应 Engagement，不混入平台研发待办。

## 实际进度

| 日期 | 已完成事实 | 仍需处理 |
| --- | --- | --- |
| 2026年11月4日（Coding Agent设计） | 按用户要求参考OpenHands固定源码、Aider和mini-swe-agent，形成[执行细化设计](../architecture/coding-agent.md)及[上游依据](../architecture/coding-agent-research.md)，明确复用/自有适配/后置、上下文/工具/检查/结果与续作；补CA01—CA10 | 本轮仅编辑7份设计/关联文档，内部链接与锚点检查通过；新增运行条件全部未执行，C2真实模型工程仍未验收。检查期间后端另有并发修改，未纳入本轮实现或运行证据 |
| 2026年11月4日（最新） | 按用户最新指令重审单ECS+Compose：形成完整架构、服务/角色/Sandbox链路、发布/HTTPS/备份/资源估算与拆分条件；新ADR0009取代物理另机要求，PRD0.9及操作入口已同步 | 仅设计待审阅；无代码/云资源/部署变更，E01—E11均未执行；确认后先做本地Compose与安全适配，再按授权购买/上线 |
| 2026年11月4日 | 用户确认本地开发、后续单台阿里云托管公司网站和客户产品、工程执行分开的方向；已同步PRD/部署/架构及P08验证要求 | 仅文档同步；无服务器购买或部署。先完成C2真实模型工程，再推进客户产品与获授权的D3发布；公司网站页面范围、预算和域名等仍待确认 |
| 2026 年 11 月 3 日 | 完成文档体系调研与本地 Router 源码研究；用户要求按计划继续 | 研究候选需在阶段 B 转成明确设计，未完成技术选型 |
| 2026 年 11 月 3 日 | 用户确认首轮最小报价比较流程，排除运费、起订量和送货条件 | 样例字段、具体换算与导出格式待细化 |
| 2026 年 11 月 3 日 | 阶段 A 文档初稿完成；当轮 31 个内部链接有效，P01—P10 均关联到实施计划和检查场景 | 尚无实现与运行证据 |
| 2026 年 11 月 3 日 | 用户确认模型未选定、期望 API 兼容、执行部署由我们推荐，并更正使用 writing-for-agents；阶段 B 三份设计和三条 ADR 已形成 | 推荐路线未实测；实际验证前需落实账号、环境、固定版本与限额 |
| 2026 年 11 月 3 日 | 再次核对官方实现与集成测试，收窄此前 C01—C05 的前置验证安排 | 复用成熟组件；短接入冒烟和自有功能测试随开发进行，深度恢复/通用编排后置 |
| 2026 年 11 月 3 日 | 按用户授权确定推荐技术组合，补齐物理映射、OpenAPI、部署设计与 ADR 0004，并同步入口/实施/测试 | 仍未开发或接入；下一步从 C0—C3 最小工程纵向切片开始 |
| 2026 年 11 月 4 日 | 结合 A2A、Odoo、Temporal、OpenHands、LangGraph 与可靠消息资料独立复核建议；采用持续输入/轻量评审/有界 Run，保留现有栈 | 仅文档与静态契约；实际薄 FDE/工程闭环尚未实现，报价具体业务规则仍待确认 |
| 2026 年 11 月 4 日 | 用户认可四角色运行与协作说明，已在 PRD 记录确认，并在架构集中补齐各角色上下文/工具/Session 边界 | 确认协作方向不表示功能已实现，继续保留模型/资源和报价规则待确认项 |
| 2026 年 11 月 4 日 | 用户明确先后端、前端以后单独设计；已将C0/C3和首个C1a任务改为后端/API优先 | 本轮仍是开工指导与计划，尚未初始化、安装或编写业务代码 |

## 本轮 C0+C1a 完成事实

2026 年 11 月 4 日：已实现后端、五张切片所需表、Cookie/CSRF、项目和草稿工程任务、事务幂等与统一错误。已在空 PostgreSQL 开发库迁移，执行23项后端测试、19项真实 HTTP 检查（两个独立 API 进程），并导出/核对契约；详细命令、版本和证据见 [验证记录](../operations/c0-c1a-verification.md)。最小 CI 仅已配置，本地检查实际通过，远程未运行。完整 C 阶段未完成，下一项 C1b 不含真实模型调用。

## C1b 完成事实

2026年11月4日：在保留现有C1a数据与用户文档改动的基础上，迁移到4bf8db3c4ef3；补齐输入记录/采用、不可变规格版本、Run/待派发状态、轻量评审与有序事件接口。全量52项后端测试、35项真实HTTP控制检查通过；同Task三轮确定性Run、四个规格版本、两次评审和进程重启有证据，见 [C1b验证记录](../operations/c1b-verification.md)。这些是控制路径证据，没有模型调用、Worker、文件构建或真实Engineering成果。C2与C3执行/角色适配仍未完成，远程CI尚未运行。

## C1b后结构重构

2026年11月4日：按用户授权，仅重组src/onefde业务模块、入口、基础设施和测试辅助；保持原HTTP契约、数据库结构与业务行为。原52项测试与19/35项HTTP场景通过，新增6项架构检查，源码目录外wheel加载验证通过。文档/命令以 [代码组织](code-structure.md) 和 [重构验证](../operations/structure-refactor-verification.md) 为准；本轮未推进C2，未接模型/Worker/前端，远程CI未运行。

## C2本轮事实与未完成条件

2026年11月4日：已新增Worker短事务认领/租约/资源登记/停止确认/结果回填、私有不可变文件及固定OpenHands1.59.0接线，迁移head为d5454eda0523。完整95项测试零skip、原19/35项HTTP回归、新9项HTTP控制检查、空PG迁移/回退/重迁移、漂移、格式、构建及OpenAPI检查通过，见 [C2验证](../operations/c2-verification.md)。真实执行端未运行，当前个人Windows宿主及凭据/隔离配置不满足ADR0003；Worker check预期返回2。C2仍未达到“真实改文件/命令/保存结果”退出条件，下一项先补专用Linux/受限模型环境并运行一个小任务，不推进前端/公网部署。

## 维护方式

DeepSeek后续准备（用户指定.env入口）：已在Windows `backend/.env`准备Key/官方地址/模型项，用户只填写Key；新增仅按DeepSeek字段同步的受信任脚本、WSL私有600运行副本及Worker只读secret加载。模型继续关闭/standby，尚未导入真实DB模型修订、开放在线出口或调用推理；费用/提供方额度与真实C2待后续落实。旧终端输入仅作可选方式，S1/S2历史证据不因此改变。

### 本地WSL环境准备（2026年11月4日，已完成）

用户授权先配置WSL2+Docker，DeepSeek延后且禁止模型/付费资源调用。已建立专用Ubuntu发行版、独立Docker/演示控制库与受限Worker身份，关闭Windows自动挂载/互操作，配置离线工程网络及持久防火墙规则；真实SDK无模型文件/命令/网络/停止/归档6组检查通过，Linux全量100项零skip通过，本地API启动和认证检查通过。修复健康检查关键字调用及自动删除容器的停止确认竞态。约定见[ADR0007](../architecture/ADR/0007-local-wsl-development.md)，具体命令和证据见[C2验证](../operations/c2-verification.md)。

环境检查退出0；完整执行检查仍退出2。没有模型调用、业务Task/Run/评审或付费资源。下一步由用户配置DeepSeek及额度后核对受限模型出口，再执行真实网页小任务；云端单ECS安全/资源边界按新计划另行验证。C2真实模型工程退出条件仍未满足。

2026年11月4日角色补全：职责和六组关系以PRD0.7为准，资料分类/权限以能力库约定为准。新增验收覆盖三个Knowledge调用方、候选整理和来源继承、内部/复用/公开三种权限、公司级咨询不造Engagement、Business不绕过FDE派客户工程。沿用后端优先，不把完整知识服务或资料管理系统加入已完成的C0+C1a，不改当前已实现HTTP契约；角色/公司级长期任务入口到对应切片再扩展。

只细化当前及下一阶段所需工作。状态更新必须对应真实文档、任务或执行证据；“已提出方案”不计为“已实现”。发生业务范围或规则变化时，先修改 PRD 或具体 Engagement，再调整受影响任务和检查。需要额外能力时优先削减非核心范围，不通过省略真实运行、信息不足处理或部署检查来宣称完成。

## 本地单机S1/S2完成事实（2026年11月4日）

用户授权的前两步已完成：独立onefde-local Compose、锁定镜像/secret封装/受限DB身份、ecs_shared与不消费作业的standby、同名宿主路径及SDK私网认证、创建时安全/资源限制、2GiB整体持久盘硬边界与容量准入。真实SDK九组无模型检查、CPU/内存/PID触顶、HTTP四组控制/持久化与仅OneFDE WSL重启恢复有证据；Linux完整106项零skip通过，格式/OpenAPI/无漂移/包构建通过。具体命令与逐项证据以[单机验收](../operations/single-ecs-verification.md)和[操作手册](../../deploy/README.md)为准。

S1/S2完成仅限本地授权范围：当前没有真实模型Engineering提交/评审，C2/CA02/P06退出条件仍未满足；E07—E11、在线模型/依赖出口、生产每Task/Session配额/总工程cgroup、HTTPS/产品发布、异机备份和云端负载待实施。下一步由用户在本地配置DeepSeek的兼容API非秘密修订、secret与费用额度后，先验证受限出口，再跑原定真实网页小任务；不得提前消费队列或开通付费资源。

## Coding Agent契约本轮事实（2026年11月4日）

在保留未提交的本地Compose/WSL成果基础上，实现并验证：

- Run快照写入`engineering`清单（角色/上下文修订、派生检查、prior_source、prior_failures）；HTTP字段未变。
- Finish提案可信校验：登记自动检查须命令匹配；无关exit 0与自报passed不能submitted；证据在作业`proof`。
- 工作区与上次源码归档比对，未知漂移阻塞；空目录可受控恢复。
- 提交后无模型固定验证容器顺序执行登记检查；`runtime_ref.resources`可登记engineering+validation；源码排除`bash_events/`。
- 全量**113**项pytest、c1b/c2 HTTP冒烟、OpenAPI/ruff通过；`deploy/verify_coding_agent.py`五组真实无模型检查通过。

**本轮续作（Key 已配置）**：沙盒接入 `HTTPS_PROXY`；以 `max_cost_usd=1` 跑 `deploy/run_c2_webpage.py`。Task `a2d797a5-…` / Run `523cad22-…` 真实 DeepSeek 生成 `index.html`+`check.sh`，自动检查与固定验证通过，founder 接受至 `succeeded`。证据见[CA验证](../operations/coding-agent-verification.md)。云端 E 类与提供方账单级费用核对仍未做。

## 审查修复（2026年11月5日）

在已有未提交改动上直接修六项，没有新方案，也没有调用模型或重跑云端/整套沙盒：

- 验证初始化、执行或清理异常后汇总全部所属容器；停止无法确认时返回 interrupted，`stopped=false`，不释放名额。
- 归档成员名只去掉字面前缀 `./`，`.gitignore`、`.github` 保持原样，`../`、绝对路径和链接仍拒绝。
- `spec.inputs` 进入任务输入。新 Run 把 `spec_version` 写入持久化快照；旧排队快照缺少该键时，认领只在执行副本上补入 `Run.task_spec_version`，不回写原快照。
- 验证流程接收停止信号和 Run 总截止时间。已取消或已超时不创建验证容器；执行中的检查受控停止。
- `prior_source` 选用最近一次已确认停止的 completed 或 failed 源码归档。interrupted 不作基准，未知漂移仍阻塞。
- 源码一致性同时检查新增、删除和修改。只有 `bash_events/` 工具日志除外；未列名的构建输出不能放行。

证据：`uv run --locked pytest -q tests/unit` 为 57 passed；`uv run --locked pytest -q tests/integration/test_task_lifecycle.py tests/integration/test_worker.py tests/integration/test_task_boundaries.py tests/architecture` 为 53 passed。集成测试使用独立库 `onefde_test`。相关 ruff check 通过。未重跑 `deploy/verify_coding_agent.py`，也未做真实模型或云端验收。

旧排队 Run：`test_legacy_queued_snapshot_claims_trusted_spec_version` 通过，执行副本带上该 Run 的 `task_spec_version`，持久化快照仍无 `spec_version`。随后 `uv run --locked pytest -q tests/unit tests/integration/test_task_lifecycle.py tests/integration/test_worker.py tests/integration/test_task_boundaries.py tests/architecture` 为 111 passed；`dispatch.py` 与该测试的 ruff check 通过。

## 黑客松参赛研究候选（2026年11月4日，历史）

当时仅形成研究建议，用户尚未确认实施。原文主张以一个报价产品、原Task修改和第二项目固定资产复用展示四角色最小职责；赛事细则未知，不预设评分权重。该段落保留为当时事实；**现已确认方向以下节为准**。

## 已确认黑客松实施切片 P0—P4（2026年11月4日）

用户确认[黑客松实施方案](../product/hackathon-proposal.md)后，先同步文档。P0—P4是**参赛实施切片编号**，不是PRD的P01—P10。确认方案≠角色/报价/页面已实现；本轮文档同步不授权新的模型调用、业务代码或云部署。验收见[黑客松切片验收](../operations/testing.md#黑客松切片验收)。

当前基线（勿与更早阻塞表述混用）：C0+C1b控制底座已有；Engineering有SDK/契约/固定验证，并有Compose API+宿主venv Worker的真实网页冒烟（Task `a2d797a5-…` succeeded）；P1薄FDE受控工具已有；P2报价静态产品v1.1与S01—S05检查已通过（本案例平台Run为确定性回填）；P3资产检索与第二项目再检查已有；P4本地产品 Origin `http://127.0.0.1:8765` 与复现说明已有，见[P4演示](../operations/p4-demo.md)。Business/Knowledge尚无独立模型循环；工程Task仍固定`owner_role=fde`、`executor_role=engineering`；工作台薄页面未做；云端E类与提供方账单费用未核。

| 切片 | 当前状态 | 下一动作与依赖 | 退出条件 |
| --- | --- | --- | --- |
| P0 固定样例与规则 | **最小退出已满足**（2026-11-04）：CSV字段八列、S01/S02/S03/S05文件与预期已写入[报价案例](../../engagements/demo-supplier-quotes/brief.md)与[samples/](../../engagements/demo-supplier-quotes/samples/README.md)；换算表/重复无效/导出样式仍待确认，S04不造预期 | 下一动作进入P1薄FDE；待确认项不阻塞P1建Task，但阻塞S04与相关验收扩大 | 可比/缺失/不可比样例有明确预期✓；原始与假设分开✓；换算与边界扩展未完成（如实保留） |
| P1 薄FDE与最小交互 | **后端受控工具已落地**（2026-11-04）：`POST .../fde/tools` 八工具白名单、`GET .../delivery`；跨项目/未知工具拒绝；角色字段由程序注入。薄页面未做；无独立FDE模型循环 | 下一动作可进P2报价交付，或先补最薄三入口页面（HM03）；模型驱动FDE另授权 | 受控工具形成Task/采用/范围拒绝✓；薄页面与HM03界面未执行 |
| P2 报价交付与原Task修改 | **产品+平台控制链已落地**（2026-11-04）：静态产品v1.1与S01—S05检查；FDE工具完整控制路径（澄清→提交→要求修改→再提交→接受）见[p2-quote-control.json](../operations/evidence/p2-quote-control.json)与`test_p2_quote_fde_delivery.py`。**未调用模型/OpenHands**；云部署未授权 | 下一动作：获授权后可用真实Engineering Run替换确定性回填，或补薄页面/P3 | 可操作产品✓；同范围修改✓；平台FDE控制链✓；真实模型工程Run未做；部署未做 |
| P3 Knowledge与Business | **最小切片已落地**（2026-11-04）：资产`fresh-quote-compare-csv@1.1.0`；`modules/knowledge`检索/权限/Business交接；第二项目`demo-supplier-quotes-reuse`采用并再检查，见[p3-reuse-recheck.json](../operations/evidence/p3-reuse-recheck.json)、[p3-knowledge-tools.json](../operations/evidence/p3-knowledge-tools.json)。无模型、无向量库 | 下一动作进P4演示材料/独立Origin说明，或补薄页面 | 资产元数据与权限过滤✓；第二项目再检查✓；HM06/HM07子集通过；无独立Knowledge模型循环 |
| P4 演示稳定与材料 | **本地 Origin 与复现说明已落地**（2026-11-05）：`python deploy/verify_product_origin.py` 退出 0，证据[p4-product-origin.json](../operations/evidence/p4-product-origin.json)；步骤见[P4演示](../operations/p4-demo.md)。当时工作台 `8000`/`8002` 未监听。录像与云部署未做 | 下一动作可选：薄三入口页面，或获授权后用真实 Engineering Run 替换确定性回填。云上线仍待购买授权 | HM08 本地 Origin 通过；HM09 运行说明通过、录像未做 |

时间不足时优先P0—P2主链与实际产物，P3/P4按真实完成度标注。不增加第二台ECS、Kubernetes、Redis、LLM Router或复杂向量库；单ECS+Compose方向不变。

2026年11月5日：P4本地切片落地。新增`deploy/verify_product_origin.py`，产品只在`127.0.0.1:8765`提供；同次运行`node check.mjs`退出0。证据[p4-product-origin.json](../operations/evidence/p4-product-origin.json)，复现说明[p4-demo.md](../operations/p4-demo.md)。浏览器在该 Origin 导入 S01 得到可比较 2 行；产品 Origin 的 `/api/v1/engagements` 为 404。工作台端口未监听，未重跑平台 pytest，未录像，未调用模型，未公网部署。
