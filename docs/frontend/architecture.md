# 前端架构与设计基线

当前阅读顺序：先读本段 2026-11-08 晚间事实，再读当日上午的审计补充。下方 2026-11-07 正文保留为历史基线，其中“当前绿系薄工作台”等已被 features 路由和紫系主题取代。

2026-11-08 晚间：FDE Work 已有独立分页和单条读取，Engineering 事件、输入和 Run 按各自水位补页。Knowledge 的查询键包含角色和用途，切换用途时清掉缓存和当前资产。模型修订接口只返回配置，不证明 Worker 进程在认领作业。工程请求硬限额在 Worker 转发层，不在浏览器。

## 四工作区状态与更新补充（2026-11-08）

### 事实与展示的边界

| 层级 | 当前事实源 | 页面承担的职责 |
| --- | --- | --- |
| 持续业务工作 | Case、Engagement、Task/TaskVersion/TaskInput、TaskReview | 引用原对象和版本，区分登记、采用、执行、业务接受、客户复试；不在四页各存一份状态 |
| 有界角色工作 | FDE AgentWork；Business指定Case的AgentGrant.progress | 展示已持久目标/报告/有限回执；不将Work登记或handler视作正在健康执行 |
| 工程运行 | Run+dispatch_jobs、RunEvent、固定blob/proof | 展示已接单/运行/停止待确认/现场不明；公开Schema没暴露的内部快照/路径/Tool日志不拼造 |
| 知识支持 | 文件Manifest、access用途投影 | Search/Get可重算，查询不自动保存业务采用；按当前版本与用途读，不能假设存在历史版本库 |
| 展示派生 | DeliveryDetail、前端状态分组/URL/提示 | 明确聚合覆盖范围，不把首Task目标叫方案、result_summary叫检查、已接受Task叫项目交付 |
| 临时状态 | 表单、选中对象、展开/复制提示，Knowledge.lines等 | 不当持久聊天；换对象清理，未提交正文默认不写localStorage；模型未提交文本不作为事实 |

实际入口为[App](../../frontend/src/App.tsx)的features，React/TanStack Query/Ant Design/HashRouter保持现有栈。本轮不引入新状态库、聊天服务或UI平台。`api/types.ts`仍手写，不宣称已生成；后续类型生成只读`openapi.implemented.json`，合并YAML中的planned不可产生可调用客户端。

### 分页、轮询与终态一致性

现状和目标分开：当前Engineering反复读取前100条RunEvent/Input、前50个Run，未循环has_more/next_cursor；Business详情已循环补消息；FDE只最近50Work且API本身无游标。不能用一个通用“已实现增量事件”描述这些差异。

建议实施：

1. 每个sequence流独立水位，TaskInput/TaskEvent/RunEvent分别从0或完整缓存开始；has_more时串行追平，按(parentId,sequence)去重，成功合并后推进水位。输入的status会更新，不能只追加新sequence：Task.revision/采用后重取受影响记录或全ledger，避免旧pending永远留缓存。
2. Run/TaskVersion/Artifact/Review列表各自next_cursor；显式历史Run可先GET /runs/R核对task_id，再读对应TaskVersion，不能因不在前50误判无权或不存在。工作/资产历史超出API能力时如实提示，不私自读取文件。
3. 当前Task/Run活动可见约2秒；waiting_input/review约10秒；interrupted可10秒核对但绝不自动释放；历史和终态停重复轮询。Case建议5—10秒可见读或手动；Work活动4秒，并在Case/Task写入、返回页/重连时重新发现pending。现有reported即停轮询不能保证外部新消息被发现。
4. 观察到Task.revision/active_run_id/latest_run_id、Run.state/outcome变化，失效相应runs/inputs/versions/events/artifacts/review-evidence/reviews/delivery/Work/Office索引；当前仅写后invalidate不足以发现外部Worker终态与新Run。证据null、产物空列表不可无限缓存；读到终态后重新取固定材料。
5. document.hidden时停止定时；请求用AbortSignal；返回/重连/手动刷新重读。当前main.tsx禁窗口聚焦自动刷新，需显式接线；不把架构建议写成已验证行为。写请求不自动重发，网络未知先核对事实，同一意图沿用冻结body+Key，409保留草稿重新核对。

没有工具级实时事件保证，也没有浏览器直连Agent Server/Worker。若未来需要订阅，先保证服务端事件持续生产、持久化与脱敏，再做SSE/WebSocket；传输本身不能生成不存在的Tool事实。

### 导航与权限隔离

URL保存合法project/case/task/run/work及检索purpose/role/asset/query；role是用途上下文，非登录身份。全局侧栏目前主要保留project，Knowledge返回缺run/work；本轮建议恢复精确来源，归属由GET事实验证，换项目清除旧子ID，不自动改绑。Office/项目中心只传合法关联并回原对象处理，不扩展成新的业务状态所有者。

Cookie内部API与客户Bearer使用独立客户端/Origin；公开View在后端过滤note/handoff和内部字段。Task命令固定revision/Run/spec/产物，历史只读。Knowledge Query key已有role+purpose，仍需换用途/来源同时清本地lines与详情，避免内部名称在公开模式残留。多用户或真实受限资料前，后端须完成可信角色/工作范围授权；缓存隔离与URL参数都不能代替授权。[访问实际实现](../../backend/src/onefde/modules/knowledge/access.py)。

### 组件与交互验收

只共享AppShell、ContextTrail、AsyncState、StatusBadge、来源引用及明确的写反馈；不创建万能聊天壳。输入采用、固定检查、正式评审按领域复用。FDE/Engineering系统事件须有来源标签，Knowledge检索结果直接呈现，无持久依据时不用模型对话外观。

状态验收覆盖加载/空/失败/旧数据、pending与applied、等待消费者/停止确认/现场不明、缺证/截断、历史版本、用途切换和409。采用Storybook的状态story与play断言思想；当前未安装时先在计划列场景，不声称已有stories/test脚本。真实同源HTTP与模型执行分别验收，详细矩阵见[实施](implementation.md#四工作区重新对齐2026-11-08)。

## 历史架构基线（2026-11-07）

状态：2026-11-07 设计已确认，现有桌面 Web SPA 已按阶段实施；本稿保存架构基线，实际进度与证据以实施记录为准。入口为[页面设计](design.md)、[能力与接口](api-mapping.md)、[实施与验收](implementation.md)。产品范围沿用 [PRD](../product/PRD.md) P01–P10；不因参考图增加 CRM、IDE 或知识平台范围。

## 产品与领域边界

OneFDE 是创始人经营一家 AI 技术服务公司的内部工作台。Office 回答“公司哪些工作需要我推进”，Business 管沟通与经营交接，FDE 管方案与交付组织，Engineering 管工程执行和固定提交，Knowledge 为前三者提供有来源、有用途限制的知识支持。客户使用独立交付软件，不登录内部工作台。

五页是同一公司事实的不同视角。共用 Engagement → Task → Run → Artifact/Review；Case 保存客户原话、跟进和反馈，FDE Work 保存项目目标的处理报告，两者引用同一 Task，不复制任务状态。Knowledge 的资产版本和业务来源引用回原工作，查询结果不自动变成资产、确认规则或执行授权。[数据模型](../architecture/data-model.md)和[能力库约定](../../capability-library/README.md)是权威定义。

```text
Office：待处理事项 ──深链接──┐
Business Case ──交接── FDE / 项目中心 ── Task ── Engineering
     ↑ 原单反馈             ↑                   Run → 固定产物 → 业务评审
     └──────────────────────┘
Business / FDE / Engineering ── 按工作归属和用途查询 Knowledge
```

必须保留四个区别：输入已记录/已采用、Run 结束/Task 接受、Task 接受/客户确认、固定成果/已发布可访问产品。四位员工按需工作；头像不是在线证明。

## 现有基础与技术决定

以[现有 package.json](../../frontend/package.json)和 lock 为准：React 19、TypeScript 5、Vite 7、Ant Design 5、React Router 7、TanStack Query 5 已存在；`HashRouter`、绿系主题的真实薄工作台和独立 `engineering.html` 模拟原型已存在。版本范围不等于精确安装版本。本次建议沿用，不另起应用。

| 决定 | 原因与实施边界 |
| --- | --- |
| React + TypeScript + Vite SPA | 延续 [ADR0004](../architecture/ADR/0004-platform-stack.md)，无 SSR/SEO 需求，不增加 Node 业务服务 |
| 保留 React Router 的 HashRouter | 当前 FastAPI StaticFiles 无通用 SPA 路径回退；Hash 深链接与原页面兼容。以后确认网关回退再评估 BrowserRouter，不为美化 URL 改部署 |
| TanStack Query 保存服务端状态 | 同一 Task 在各角色页共享查询，按对象和用途隔离缓存；明确刷新、分页、终态和错误策略 |
| Ant Design + 项目主题/CSS 变量 | 复用 Form/Table/Drawer/Alert/Select，保留品牌形象；不增加第二套组件库或管理台脚手架 |
| 现有 fetch 封装 + 生成类型 | 开发阶段新增 dev-only `openapi-typescript`，从已实现 JSON 生成静态类型；保留轻 API Client，不同时增加 Axios/另一套数据缓存 |
| npm 与现有 package-lock | 架构早期推荐 pnpm，实际已落 npm 锁；本轮规划不迁移包管理器 |
| Vitest + Testing Library、少量 Playwright | 后续按阶段引入开发依赖，当前未安装/未有脚本；只覆盖并发、游标、权限、状态和核心浏览器路径 |

React 官方明确 SPA 自建路线需补齐路由和数据获取，本项目已有对应库；[React](https://react.dev/learn/build-a-react-app-from-scratch)、[HashRouter](https://reactrouter.com/api/declarative-routers/HashRouter)、[Vite 静态构建](https://vite.dev/guide/build.html)支持上述取舍。网页文档最新版本不作为升级本仓库的理由。

## 代码边界与状态归属

后续在现有 `frontend/src` 渐进整理，以下为建议职责，不要求一次创建全部目录：

| 层 | 责任 |
| --- | --- |
| `app` | Router、认证边界、QueryClient、主题、AppShell；恢复原深链接 |
| `api` | 生成的运行契约类型、fetch/error/CSRF/幂等、按业务域的薄客户端；不含 UI |
| `features` | projects、engineering、fde、business、knowledge、office 的查询与页面组合；Office 场景 HTML 叠加；Business 页头复用 `public/avatars/business.png`；角色页不另建状态库 |
| `shared` | 状态、上下文路径、异步反馈、证据引用等有真实复用的组件；不创建万能聊天组件 |
| 独立原型/测试夹具 | 显示“模拟数据”；与真实数据适配和发布入口隔离，不能失败后回退到 fixture |

URL 保存项目/Case/Task/显式历史 Run、筛选和证据视图；Query 保存服务端对象；组件/Form 保存未提交草稿、展开态和选中产物。只用 React Context 放认证及外壳偏好，不引入 Redux/Zustand。Task/Run 状态不复制到 Context 或 localStorage。草稿按 Task/Run/版本隔离，切换对象不能串写；离开有未提交草稿时提供保留/放弃选择。私有业务内容默认仅内存，登出清除。

建议 Query key：`['task', T]`、`['run', R]`、`['run-events', R]`、`['delivery', E]`、`['knowledge', caller, purpose, queryOrId]`，未来加入实际授权范围。每次深链接先核对 `Task.engagement_id` 和 `Run.task_id`，禁止组合错位评审。旧路由和 `case` 参数继续可用，详见[导航](design.md#导航与项目上下文)。

## API Client、认证与并发

类型唯一生成源为 [openapi.implemented.json](../architecture/openapi.implemented.json)，不得从含规划操作的合并 YAML 生成可调用客户端。后端先执行既有 `python -m scripts.export_openapi --check`（从 backend 的锁定环境），前端再生成并检查差异。未来 CI 检查导出、生成、类型检查；本轮仅设计，不创建生成器脚本。`FdeToolResult.result`、Work `report/trace` 等仍是宽字典，生成 TS 不提供运行时校验，页面适配需做最小结构检查并保留未知结果提示。[openapi-typescript](https://openapi-ts.dev/introduction)支持 OpenAPI 3.0/3.1 静态类型。

- 工作台只访问同源 `/api/v1`，`credentials: include`。启动时 `GET /auth/session` 取内存 CSRF；401 回登录并清私有 Query/草稿，登录后恢复合法路径。Cookie 由服务端设置 HttpOnly；生产使用 Secure 的 `__Host-onefde_session`，不在 localStorage 存凭据。
- 写请求带 JSON Content-Type、可信 Origin 和 `X-CSRF-Token`；登录不带 CSRF，登出也须 JSON。按路由要求提供 `Idempotency-Key`；Knowledge 的查询虽是读业务语义，HTTP 是 POST，仍需上述头。候选邀请等路由没有 Key 参数，不假称所有写入都已实现同一种幂等。
- 一次意图冻结目标、正文、revision 和幂等键。同请求网络重试沿用键；修改正文/对象/版本使用新键。Task 命令提交 `expected_revision`，适用时绑定 Run/spec/Artifact。202 只显示“已接单”，后续从 Run 确认执行。
- 写入不自动重发。超时后先读回事实，结果未知时提示核对；同意图可重试。409 保留草稿、重读版本并让用户核对后操作，不能自动套新 revision 重发；403 区分 CSRF 与业务权限，404 不泄漏受限对象，422 定位字段，429 按服务端指示稍后重试。
- 扩展现有 ApiError 保存 `request_id`（正文或响应头）、`details`，缺字段用安全通用提示；日志不输出 Cookie、token、模型凭据或客户原文。

当前单创始人登录不是多租户/多角色 ACL。页面按能力和状态控制入口，后端仍是权限判定方；Knowledge 的现有用途投影不等于完整项目权限系统。客户 Bearer 会话与员工 Cookie 客户端分开，不能共享 token 或混用接口。

## 轮询、增量事件与未来 SSE

首发 REST。可见的活动工程页约 2 秒读 Task 和当前 Run；Task `running` 可能对应 Run `queued`，显示“等待派发”。Run 状态为 `queued/running/cancel_requested/interrupted` 时继续核对；`interrupted` 可降为 10 秒并给出人工核查入口说明，不能自行解锁。无活动 Run 的 waiting_input/review 页面约 10 秒核对 Task，便于发现外部答复/评审；succeeded/cancelled 停止定时，保留手动、重连和重新可见刷新。

Run Events、Task Events、Inputs 分别使用独立 `after_sequence` 水位，按 `(parentId, sequence)` 去重；`has_more=true` 时串行补页至追平，只在成功合并后推进水位。重新打开从零补齐或从仍保留的缓存水位继续；不因本地记住末序号而丢掉已清缓存的正文。历史 Run 无持续轮询，不被最新 Run 自动抢走。

当前 SDK callback 收集执行证据，Worker 结束回填时才写入部分检查事件；API 事件流有序可补读，不保证工具级实时进展。无新事件显示“执行中，暂无新增事件”和数据更新时间，不能渲染打字动画冒充模型输出。SSE 前必须先有受控、持久、脱敏的事件生产，再有鉴权订阅/游标补读/重连；首版留 transport 接口，未来消息用于补读或失效 Query，不维护第二套状态。断流降级轮询，终态仍重取证据。

Task revision、Run ID/state/outcome 变化或写入成功时，定向失效 Task、delivery、inputs、versions、runs、review-evidence、artifacts、reviews。证据首次为 null 后不能永远缓存空值。后台/卸载停止重复计时器，读取使用 AbortSignal；断网保留带“数据可能过期”的上次结果。GET 可有限退避重试，认证/权限/校验错误不重试。TanStack 默认 stale、重连和失败重试需明确配置，不能全依赖默认。[官方默认行为](https://tanstack.com/query/latest/docs/framework/react/guides/important-defaults)

## 部署、组件与检查

开发真实联调优先走已配置的可信 API Origin；Vite 独立预览不等于认证联调。当前 Vite 没有 API proxy；若以后启用 HMR，需明确代理与 Origin/Cookie 接线，不能只加代理就认定 CSRF 通过。现有 API 可服务 `frontend/dist`；正式拓扑沿用[单 ECS+Compose](../architecture/ADR/0009-single-ecs-mvp.md)及[部署设计](../operations/deployment.md)，无新增服务器前提。生成 HTML/JS 只在独立产品 Origin 或受控预览执行。

共用 AppShell、ContextTrail、AsyncState、StatusBadge；工程复用 TaskSelector、TaskActivity、RunTimeline、SubmissionPanel、CheckList、ReviewForm、InputDecision。先从实际调用抽取，避免按每个 API 建按钮。Diff 首发使用只读文本及增删标记，局部滚动；不引入 Monaco、xterm 或完整 IDE。文件/下载新能力见[缺口](api-mapping.md#后端增量候选与优先级)。

测试按风险：纯适配与游标合并用单测，评审/待答/冲突用组件交互测试，浏览器覆盖同 Task 多轮与两标签并发。Storybook 后置到共享组件需要独立验收时，优先状态 stories 和 `play`，不为交付一页先搭完整平台。[官方交互测试](https://storybook.js.org/docs/writing-tests/interaction-testing)。前端不重测 SDK 工具循环；后端已有领域测试是依据，浏览器验收单独记录，详见[实施计划](implementation.md)。

## 成熟项目取舍

2026-11-07 查看官方资料与公开源码；以下是本项目推导的建议，不声称原样复用上游。

| 来源 | 采纳 | OneFDE 的取舍 |
| --- | --- | --- |
| [OpenHands Canvas 架构源码](https://github.com/OpenHands/OpenHands/blob/main/docs/architecture.md) | 工程活动与文件/证据工作区分开，API、组件、查询与 mock 各有职责 | Canvas 可直连 Agent Server；OneFDE 浏览器只连自有 Backend，沿用已固定 SDK，不嵌整套 Canvas |
| [Linear Concepts](https://linear.app/docs/conceptual-model) | 以工作对象为主、项目归组、视图复用同一事实 | Task 增加 Run/固定评审语义；不引入团队、周期、积分等无当前需求对象 |
| [Plane Views](https://docs.plane.so/core-concepts/views)、[web 实际依赖](https://github.com/makeplane/plane/blob/preview/apps/web/package.json) | 列表/筛选/上下文深链接是同工作多视图；源码体现共享 services/types/ui 模块 | 只借职责拆分，保留 OneFDE Query 与 Ant Design，不跟随其 MobX/SWR 等依赖组合 |
| [Storybook Stories](https://storybook.js.org/docs/writing-stories) | 用真实领域状态和交互步骤评审复用组件 | 首阶段不用新增 Storybook 服务；夹具明确标模拟，真实联调单列 |
