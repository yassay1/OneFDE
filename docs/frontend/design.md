# 四个 AI 员工工作区设计

状态：2026-11-08 调研与设计建议，待用户确认；本轮只改文档。新方案优先于下方历史页面组织描述；职责和能力边界来自当前工作树，布局与交互调整尚未实施。逐模块契约见[能力映射](api-mapping.md)，问题与验收见[实施](implementation.md#四工作区重新对齐2026-11-08)。需求来源为[PRD](../product/PRD.md) P01—P10、六组关系及本轮用户要求。

## 职责决定工作区

| 员工 | 实际职责与核心对象 | 首屏应该回答 | 输出与责任边界 |
| --- | --- | --- | --- |
| Business 客户与经营 | Case+Message处理咨询/售后/邀请回复；Candidate组织区县找店；AgentGrant约束指定模拟会话 | 哪个会话需要处理、原话是什么、谁接手、下一步是什么 | 有来源的交接与获准回复；Case不是Customer，无通用创始人聊天、CRM或销售漏斗 |
| FDE 方案与交付 | Engagement下AgentWork，关联Case/Task；诊断、澄清、组织工程、给评审建议 | 项目目标和依据、工作目标、报告建议、未知项、下一项Task | Task规格/输入、报告与评审建议；reported只是当前水位已报告，业务接受另走TaskReview |
| Engineering 软件开发 | 持续Task/TaskVersion/TaskInput，每轮Run/RunEvent，固定证据/Artifact/TaskReview | 当前范围与版本、运行还是等待、未采用输入、提交依据与下一步 | 实际工程结果与证据；执行者不接受自己提交，停止本轮和取消任务分开 |
| Knowledge 知识与能力 | 有角色/用途的Search/Get，读取Capability Manifest | 为谁/什么用途查、哪个版本可用、来源/条件/限制是什么 | 可见投影与版本引用；横向服务三角色，查询不授予复用/公开权限，不自动采用 |

证据：[Business模型](../../backend/src/onefde/modules/business/models.py)、[Work模型](../../backend/src/onefde/modules/fde/agent_models.py)、[任务模型](../../backend/src/onefde/modules/tasks/models.py)、[Knowledge工具](../../backend/src/onefde/modules/knowledge/tools.py)。Engagement实际仅含title/goal/is_demo/created_at等字段，无context持久字段。已采用规则看Task.spec.confirmed_rules，交接事实看Case及原消息，不能拼成没有来源的“项目事实库”。

## 四页线框与核心交互

统一全局导航、紧凑身份横幅、上下文路径和异步状态；工作内容左对齐。取消四页固定“左聊右工作”的要求。Office/项目中心仅检查上下文与导航，保持当前范围。

### Business：收件箱与找店入口，具体Case才展示对话

```text
全局导航 | Business 客户与经营        [Case收件箱] [主动找店]
首页     | 会话列表：工作流/处理人/状态/下一步/分页
Case详情 | 当前下一步 / 状态 / 处理人 / 最近读取时间
         | 客户会话（原话、对外回复） | 当前Case依据
         | 对外回复输入：客户可见     | 来源/版本/交接事实/未知项
         | 内部备注另入口             | 项目→Task→复试固定版本
         |                            | 一个主操作，其余按需展开
找店     | 区县+模拟/真实来源 → 候选 → 生成邀请 → 创始人自行分享
```

首页不放不可发送的通用聊天框。列表过滤目前仅作用当前分页，须说明覆盖范围；全库筛选属后端缺口。搜索即保存候选，不再设计虚假的“保存候选”操作。邀请登记不证明外发/触达。右侧围绕当前Case，不展示客户档案、营收或全局销售待办。备注默认折叠，保留来源与时间；公开发送预览只含客户可见正文。客户入口只返回customer/reply、公开状态与复试通知，不返回note/handoff/内部处理人与工程证据。

| Case状态/条件 | 主操作与反馈 | 附加限制 |
| --- | --- | --- |
| open/clarifying | 等补充或创始人接管；有具体需求才交接 | 邀请非售后交接要求具体需求与继续意愿，不能替客户填写意愿 |
| founder_queue | 创始人接管 | 承诺/报价/交期人工确认 |
| fde_queue且有handoff | 选择项目，交FDE处理 | Work登记可绑定交接；传统accept_handoff需现有Task或完整spec；售后核实版本 |
| handling且当前handler为本人 | 对外回复，FDE可预览澄清 | 预览不落库，发送核对来源消息与public水位；内部备注单列 |
| handling且FDE有Task | 登记客户消息为pending TaskInput | 不是采用；support在当前修复产物被接受并记录访问检查后通知复试 |
| handling且service接手 | 看结果或接管 | handler不证明在线/健康；Case API不暴露grant有效性 |
| awaiting_retest | 等客户原会话确认 | 员工不能代填通过；失败回fde_queue，不重复旧修复产物 |
| closed | 只读 | 当前接口拒绝写入；不自行规定后续业务重开流程 |

完整守卫见[operations.py](../../backend/src/onefde/modules/business/operations.py)。state只是提示，还要核对owner/handler/归属/消息水位。`approve_fde_feedback`仅适用于有效模拟授权、handling的非support Case及当前已报告Work；保存核准备注后由消费者转达，不能提示“已发送”。

核心路径：客户消息→原Case收证→交接→FDE绑定项目/Task→工程正式接受→固定修复与访问检查→通知复试→客户通过才关闭。失败沿原Case关联后续Task。主动找店→邀请→客户回复→具体需求与继续意愿→同一交接路径。

### FDE：项目目标与Work报告为主，项目依据为辅

```text
全局导航 | FDE 方案与交付   项目选择 / 原Case / 项目中心
         | 项目目标 + 模拟标记（常驻一行）
         | Work列表/选中工作              | 项目依据
         | 目标/状态/报告                 | Case交接事实与来源
         | 建议、错误、待决定分别标识     | Task已采用规则/待处理问题
         | [登记项目目标]（新Work）        | Task范围/版本/状态索引
         | 回执、calls/usage折叠           | [去Engineering正式评审]
```

左侧是有Work边界的工作记录，不把多个Work拼成持续聊天。Work随Case消息/Task版本变化再次pending，当前report/trace会更新，不是不可变报告版本库。报告仅在选中Work显示一次，右侧只保留引用和状态。普通Work可读、建草稿、在draft/waiting_input按归属与revision采用输入、给建议；自动发澄清和派工程须有效模拟grant，无网页扩权入口。

依据分组：Case.handoff.confirmed_facts是交接事实；Task.spec.confirmed_rules是已采用执行规则，带spec_version；delivery.unknowns只是pending question/clarification聚合，不是完整项目未知项。空态写“当前聚合未发现待处理问题，不代表资料已齐”。scheme_summary只称“首个任务目标摘要”，latest_checks只称“最近执行摘要”。

核心路径：选项目→核对来源/缺口→登记goal或已批准Case（202仅登记）→消费者保存报告→查看建议/错误/澄清→Task规格及输入采用→Engineering→FDE评审建议→负责人正式评审。Agent的`suggest_review`更新report；认证HTTP `fde/tools`的`propose_review`实际写正式TaskReview，两者不可混同。建议FDE页面只给正式评审深链接。[HTTP工具](../../backend/src/onefde/modules/fde/tools.py)、[Agent工具](../../backend/src/onefde/modules/fde/agent_tools.py)。

### Engineering：任务活动与输入采用常驻，固定提交按需打开

```text
全局导航 | Engineering 软件开发   项目 / Task / 当前状态
         | Task列表 | 范围、规则、完成条件、spec版本
         |          | 当前Run与等待原因 / 输入ledger / 运行活动摘要
         |          | 问题 → 保存答复 → 所有者采用/拒绝 → 续作
         |          | [查看固定提交] → 检查/限制 → Diff/元数据 → 正式评审
         |          | 历史Run选择（只读） / 规格版本历史（按需）
```

不常驻四个空Tab；证据缺失不能合成源码。活动标TaskInput/RunEvent/结果来源，不全改写成模型发言，同一事件不在聊天与日志重复出现。多问题逐项选择答复，每项显示pending/applied/rejected与处理依据。

| 当前事实 | 现有API动作 | 操作结果与限制 |
| --- | --- | --- |
| draft或无活动blocked，无pending | queue | 仅就绪，下一步start |
| queued，无pending/活动占用 | start+可用模型修订 | Run queued等待Worker；configured不证明可执行 |
| active Run queued/running | 记录补充；stop_for_update/cancel按需 | pending不进当前快照；停止待确认，未认领作业可直接确认撤销 |
| waiting_input，原Run completed/needs_input | 原question下保存answer，再采用 | 问题有已采用答案且无pending后continue创建新Run |
| 未关闭，无active Run | 采用/拒绝指定输入，记录理由 | 范围/规则变更需完整新spec；reject-only不升spec_version；不自动执行 |
| review且Run/spec/产物匹配 | accept/request_changes | accept需无pending及检查依据；修改保存评审+pending change_request，回draft |
| blocked、无active、最近Run failed/cancelled | retry，无pending | 新Run，保留失败；不承诺从原模型指令继续 |
| cancel_requested/interrupted | 等待/核对状态 | 不重复停止、不强制解锁；interrupted保留占用 |
| succeeded/cancelled | 只读，后续关联新Task | 原Task不重开，接受不等于复试/发布 |

取消适用于未关闭任务，但cancel_requested/interrupted拒绝再次改变停止意图。按钮须同时核对Task与Run。当前accept不强制validation_passed=true；缺证突出显示并填写实际评审依据，如要硬性禁止，须确认后端规则。

历史Run按task_spec_version读TaskVersion，不能套最新Task.spec；本轮applied_input_ids与当前pending分开。Diff带基线/归档摘要、截断和known_differences；空Diff、null证据、失败区分。Artifact只展示元数据，不给下载；RunEvent叫“运行活动摘要”，不是实时工具日志。

### Knowledge：检索与详情为主，返回原工作

```text
全局导航 | Knowledge 知识与能力          返回原工作
         | 来源角色 / 用途 / 项目或Case或Task（带入时常驻）
         | [关键词________________] [检索]
         | 结果：名称/版本/验证状态 | 资产详情
         | 获准来源/复用范围        | 问题/条件/限制/输入输出
         | 仅本次可见命中数         | 来源/实现/验证样例/版本
         |                          | [复制引用] → 原工作明确采用
```

无需左侧聊天。现有检索气泡是程序拼接且仅内存，改为结果反馈。深链接带入的角色和用途始终可见；public_marketing仅公开摘要，不能从旧缓存补内部字段。delivery/internal_research当前同投影，三角色search/get未形成差异字段ACL；角色选择不是切换账号/权限。

核心路径：原工作带来源→核对用途→关键词检索→get→核对版本/条件/证据→复制id@version→返回。复制不保存采用，Task选用仍走spec/输入采用。Manifest按ID取当前文件，id@version不是任意历史版本可读API。

## 共享上下文与六组关系

共享对象引用：Case→engagement_id/task_id；Work→case_id/task_id；Task→engagement_id/related_task_id；Run→task_id/task_spec_version；Review→Run/spec/Artifact。URL传ID与用途，不传原文/凭据；链接不授予权限，Query复用事实而非复制聊天。

| 关系 | 交接与返回 | 当前边界 |
| --- | --- | --- |
| Business↔FDE | 原话/交接→项目Work；获准反馈回Case | A/B，核准记录不证明外发，承诺人工负责 |
| FDE↔Engineering | Task规格/输入→Run证据→建议/正式评审 | A/B，采用/执行、建议/接受分开 |
| Business↔Knowledge | Case或经营来源+用途查询，返回Case | A/B检索；通用咨询历史/自动资产整理无API |
| FDE↔Knowledge | 项目查条件/版本，Agent有界比较 | A/B，consult为确定性资产比较，无独立Knowledge模型会话 |
| Engineering↔Knowledge | Task查实现/限制，固定版本后重新检查 | A/B网页查询；运行期工具以Runtime白名单为准，不等于当前Run已读取网页结果 |
| Business↔Engineering | 沿Case查固定成果与接受修复 | A/B事实查看；开发仍经FDE/Task授权 |

全局侧栏目前主要保留project，会丢Case/Task/Run/Work；目标是合法关联才传，换项目清理子对象。Knowledge返回路径补work/run及精确来源；归属错误停止写入，不静默选择别的对象。[导航](../../frontend/src/app/AppShell.tsx)、[路由](../../frontend/src/App.tsx)。

## 统一规范与角色差异

沿用[theme.ts](../../frontend/src/app/theme.ts)与现有素材：画布#F6F5FB、工作区#FFFFFF、正文#23223B、次文#5E5875、主动作#6148CF、边线#E5E2F0。字体Segoe UI/Microsoft YaHei，正文14px/1.5、重要阅读可16px，标题22—28px，代码Consolas。页头建议120—140px优先留出对象与下一步。角色色用于身份，状态用语义色+文字；无假统计/百分比。

Business以列表/会话为主；FDE以目标/报告为主；Engineering以Task活动/证据为主；Knowledge以检索/详情为主。1280可收索引，1024纵排，360与200%缩放保证操作可达，长Diff局部滚动。现有控件36px，触控主目标建议44px或足够命中区。对比度≥4.5:1、焦点可见、面板关闭回焦点、尊重减少动效；长文本约80字宽以内。

加载用区域骨架；空态说清缺对象/结果/证据及下一步；失败保留旧内容并标过期/最近成功读取；等待说明谁处理什么；成功按回执叫“已登记/已采用/已接受”。读取时间不是业务更新时间；读取失败不显示待命，缺字段不当0/通过。写入防重复、保草稿，409重读核对，不自动换revision重发。[状态与更新](architecture.md#四工作区状态与更新补充2026-11-08)。

设计方法：frontend-design用于按对象安排阅读顺序、把视觉记忆限于员工身份；ui-ux-pro-max两次design-system检索均返回偏营销/不合本工作台的组合，未采纳其配色/字体；此处使用既有主题及通用可访问规范，不声称获得匹配的工作台模板。

## 成熟产品调研与取舍

2026-11-08实际打开一手资料；以下OneFDE取舍为设计推导，不引入其技术栈。

| 来源 | 观察 | OneFDE取舍 |
| --- | --- | --- |
| [OpenHands Canvas架构](https://github.com/OpenHands/OpenHands/blob/main/docs/architecture.md) | 前端组织会话/工作区，执行由Agent Server承担，API/组件/查询/mock分层 | 活动与成果分开，浏览器只连自有Backend；不照搬上游终端/文件/浏览器能力 |
| [Linear Concepts](https://linear.app/docs/conceptual-model) | 视图复用同一工作，项目组织工作 | 四角色共享对象，不复制项目资料，不引入周期/积分/CRM |
| [OpenAI Sessions](https://developers.openai.com/api/docs/guides/agents-api/sessions)、[Tracing](https://developers.openai.com/api/docs/guides/agents-api/tracing) | Session保留上下文，Turn有完成/失败/取消，Trace区分生成和工具结果 | 借阅读层级：持续Task/每轮Run/受控证据；会话空闲不等于成功，无span数据不画完整工具树 |
| [LangGraph Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)、[Persistence](https://docs.langchain.com/oss/python/langgraph/persistence) | 持久化支持中断/恢复，恢复可能重跑节点 | 保存问题/采用答案/新Run，不承诺工具中间续跑，不替换现有Worker |
| [Storybook交互测试](https://storybook.js.org/docs/writing-tests/interaction-testing) | story表达状态，play执行交互断言 | 覆盖缺证/冲突/历史/公开用途；模拟与真实HTTP分列，不为本轮安装工具 |

## 待确认规则

1. 是否硬性要求固定复验通过才能accept；历史/缺证Run如何处理。当前不变更接受契约。
2. 非演示Business/FDE模型授权、费用、范围、操作者和状态可见协议未形成通用产品能力，不设计自动处理所有客户开关。
3. 项目级事实/未知项/方案是否需要独立维护与版本；确认前用Case/Task现有事实视图。
4. Knowledge真实角色授权、公开摘要审定/撤回与历史版本留存，需在真实资料阶段确定。

这些不阻塞A/B信息结构修正，C类实施须等具体规则确认。[分期验收](implementation.md#四工作区重新对齐2026-11-08)。

## 历史设计与视觉记录（2026-11-07）

以下保留当时叙述，不证明当前路由仍挂载相同功能。当前代码以[审计](api-mapping.md#当前前端实际情况)为准。

状态：2026-11-07 设计已确认，五页视觉与四张英雄场景已落地。改页面时读本稿，接数据时读[能力映射](api-mapping.md)，开发边界和技术决定见[架构](architecture.md)，分期见[实施](implementation.md)。既有独立模拟原型属于历史成果；实际 SPA 进度与验收见实施记录。

## 图像核对与设计取舍

设计准备阶段曾扫描 `D:\proj\one-picture`，当时共 7 个 PNG；后续新增的独立场景与头像以本页文末美术接入记录为准。全部逐张打开观察：6 张 UI 图（Office 两张及四角色各一张），1 张后端架构图。`01_office.png` 为 1600×900，其余角色图和 Office 补图为 1672×941；尺寸是参考画布，不是固定网页宽度。

| 实际文件 | 观察到的构图与品牌 | 采纳和删减 |
| --- | --- | --- |
| `01_office.png` | 深紫侧栏、白顶栏、暖色四员工办公室，右上需要你处理/概况，下方项目/贴士 | Office 主要依据，保留角色形象和待办优先；缩短大图，去掉贴士、周统计和假进度 |
| `OneFDE智能协作办公室.dashboard.png` | 四角色气泡、右侧今日重点/团队动态、底部项目阶段；原文件名不是 `_dashboard` | 借鉴清楚的角色分区和单项目摘要；不用无存储的待办复选框，去重复业务/员工导航 |
| `OneFDE客户经营助手仪表盘.png` | 橙色耳机柴犬、暖色横幅；左对话/客户/商机/跟进，右客户/漏斗/待办 | 保留客户与下一步工作线索；用 Case 收件箱，CRM 与成交漏斗后置 |
| `OneFDE方案交付工作台.png` | 戴眼镜白猫、蓝紫方案插画；左需求/方案/交付/文档，右阶段/产出/关键事项 | **FDE 视觉精修已落地**：英雄区+左 Work 右工作台；以真实 Work 报告、未知项和 Task 展示，不预建五个空 Tab；场景插画已安装 |
| `OneFDE 工程工作间界面.png` | 熊猫工程师、Task 标题与阶段；左对话右宽 Diff/文件树/日志/检查，底部修改/验收 | **Engineering 视觉精修已落地**：英雄区+任务进度条+活动主列；提交时加宽证据抽屉（暗底 Diff/检查/评审）；无文件树/假聊天；场景插画已安装 |
| `知识工作台：售后换新智能检索.png` | 眼镜耳机猫头鹰、书架横幅；左检索结果，右资产数量/图谱/最近沉淀 | **Knowledge 视觉精修已落地**：英雄区+结果卡+详情+右侧真实上下文；去图谱/虚构全库数量/沉淀流；售后换新仅为示例文案；场景插画已安装 |
| `后端架构.png` | Task Service→Dispatcher→Runtime→四角色，Engineering 连接独立沙盒 | 用作逻辑关系参考，不当 UI、当前部署或能力验收证据 |

目标风格为安静的专业工作台，品牌记忆集中在四角色和 Office 办公室。角色页采用紧凑页头（场景框高 120px、叠加头像 64px），工作区域优先。图中状态、数量、Excel 支持、单位规则、自动标准化等不能当实现事实；具体报价规则仍以[项目记录](../../engagements/demo-supplier-quotes/brief.md)为准。

## 导航与项目上下文

左栏只放一套主导航：办公室、项目中心、Business 客户与经营、FDE 方案与交付、Engineering 软件开发、Knowledge 知识与能力。角色图标用对应头像，避免第二组同名员工入口。能力资产是 Knowledge 的目录视图，不另建数据体系。首发不放全局搜索、通知角标和无实际内容的设置。

| 建议 Hash 路由 | 上下文与兼容要求 |
| --- | --- |
| `#/` | Office 公司视角；聚合未完成前明确“部分项目摘要”或仅导航入口 |
| `#/projects`、`#/projects/:engagementId?task=…&case=…` | 保留现有项目入口和参数；项目中心是跨角色的目标、任务、结果索引 |
| `#/business`、`#/business/:caseId` | 保留原会话深链接；未交接 Case 可不属于项目，不强造 Engagement |
| `#/fde?project=…&work=…&case=…` | 同项目 FDE Work，按归属打开关联 Task/原 Case |
| `#/engineering?project=…&task=…&run=…` | 无 run 参数跟随当前活动/最近 Run；有参数锁定历史，证据视图可加 `view=submission` |
| `#/knowledge?project=…&task=…&from=…&purpose=…` | 只传有效关联 ID/用途，保留返回原工作的链接；URL 不传客户原文或 token |

角色切换沿当前项目，只有确有相同 Task 才传 Task；切换项目清除不属于新项目的 Task/Run/Case。来源 URL 必须站内且归属校验通过；错误组合显示“对象不属于当前项目”，不自动选择另一个对象继续写入。项目中心的阶段暂用 Task 状态分组摘要，不能从“有已接受 Task”推断项目已交付。刷新、浏览器前进后退和复制链接恢复选择；草稿规则见[架构](architecture.md)。

## 五页首屏与主要操作

| 页面/主要场景 | 默认展示与核心区域 | 最重要操作 | 按需展开/不首发 |
| --- | --- | --- | --- |
| Office：创始人开始工作、处理例外 | 约 60/40 双栏：静态办公室场景 + 四员工状态气泡与热区；需要你处理；少量项目摘要。待办含对象标题、原因、真实状态与更新时间 | 点击气泡/角色进入对应工作台；或打开待办原对象 | 项目历史动态展开；不显示营收、员工在线率、周增长和推测百分比 |
| Business：处理咨询、售后及交接 | 英雄区 + 对话工作台壳（待 LLM）；本页真实 Case 卡片；右侧关注/状态分布/跟进；Case 收件箱与找店 Tab；详情会话主栏 | 打开 Case 处理、接管/回复/交接 FDE | 内部备注与澄清展开；不首发客户档案、全库商机漏斗、跟进日历；对话输入本轮禁用 |
| FDE：明确方案、组织同项目交付 | 英雄区（白猫头像 + 蓝紫场景）+ 左主区 Work 目标/报告气泡 + 右栏项目方案工作台（真实阶段派生、产出、未知项） | 选项目后登记 FDE Work；报告后链到 Engineering 正式评审 | Work 工具回执/澄清/评审建议展开；不预建需求/方案/交付/文档空 Tab；无方案版本实体 |
| Engineering：持续工程与业务验收 | 英雄区（熊猫头像 + 青紫场景）+ 真实进度条 + 任务侧栏 + 活动主列；证据按需右开加宽抽屉 | 按状态答复/采用、启动/续作或打开固定提交评审 | 历史轮次、检查/Diff/产物展开；不做文件树、假 3/3、聊天快捷墙 |
| Knowledge：为当前工作查证据和可复用能力 | 英雄区（猫头鹰 + 书架场景）+ 检索栏 + 结果卡/详情；右侧上下文、本页结果分布、选中摘要与能力边界 | 检索并查看/复制固定版本引用，返回原工作 | 验证样例展开；不做对话五 Tab、图谱、虚构全库数量、沉淀流、上传 |

五页的主工作对象不同：Office 是待办，Business 是 Case，FDE 是项目 Work/方案判断，Engineering 是 Task 的运行与提交，Knowledge 是有用途的查询结果。对话外观可用于真实原话或工作记录，但不能把所有内容改写成“员工说”。

### Office 数据和状态

待办的动作必须回原对象处理，不能在 Office 勾选即算业务完成。受限摘要阶段标覆盖范围/最近读取时间/部分失败，不显示完整待办总数。

**状态气泡（已实现；Office 第一轮视觉精修）**：静态场景图 `frontend/public/office-scene.png`（自设计图裁切办公室区域，非整页 UI 截图）上叠加四枚胶囊气泡、角色名签与热区。文案由 `deriveRoleStatuses` 从本页已读的 `/office/actionable` 与 `/office/activity` 派生，优先级为：等待创始人处理 → 真实进行中工作 → 最近可确认完成 → 暂无可确认动态。Business 看 Case；FDE 看 Work；Engineering 看 Task/Run/Review。Knowledge **无常驻活动接口**，固定展示「暂无实时动态 · 待命」，不得写成持续运行。加载中显示「读取中…」；双侧失败显示「状态读取失败」；部分失败保留已读事实并提示。无心跳，不展示在线/空闲。点击气泡或角色热区进入 `/business`、`/fde`、`/engineering`、`/knowledge`。场景底图已换为干净办公室插画（源自 `温馨AI办公休闲空间.png`，安装为 `frontend/public/office-scene.png`）；状态与角色名签仍由 HTML 叠加，无烘焙业务文案。

### Business 公开与内部边界

把“对客户回复”和“内部备注”分成明确入口，发送前可检查本单对象、公开正文和引用。澄清草稿预览不等于已发送；发送带原消息水位，过期后回看新原话重新核对。接管后显示真实 handler，自动化是否暂停以服务端事实为准。交接保留来源、继续意愿、未知项及核实版本；FDE 接手关联原 Task。售后通知绑定已接受固定产物和真实访问检查；客户复试通过才关闭 Case，失败回原会话续办。工作台不能代客户填写通过。

### FDE 能力表达

FDE 已有真实 ChatModel 工具循环及持久 Work，不应写成“仅工具、没有 Agent”。但当前 HTTP 是一次目标/已批准 Case→异步 Work→报告/trace，不是持续创始人聊天协议。输入区标“给 FDE 一个项目目标”，提交后显示“已登记工作”；报告标“建议/需要决定/关联任务”，缺消费者时保持待处理，不伪造回答。`reported` 可能包含错误或等待工程，不当作方案已确认。

`delivery.scheme_summary` 实际来自首个 Task objective，显示为“任务目标摘要”；`latest_checks` 是 Run 摘要，不当结构化检查通过；`fixed_version_hint` 是提示，不是部署链接。正式规则更新仍经 Task 输入采用或规格更新。普通 Work 与隔离模拟自动授权分开，前端不提供扩大 grant 的按钮。

**视觉精修（2026-11-07）**：页头对齐 Business——`avatars/fde.png`（戴眼镜白猫）、职责说明、由真实 Work 派生的状态胶囊；英雄场景 `fde-hero-scene.png` 已安装；加载期间保留场景框，实际失败才提示场景暂不可用。主栏为工作记录气泡（登记目标 / FDE 报告），右栏为项目方案工作台：阶段条由 Work/Task 状态派生（不伪造完成勾）、产出为真实 Task 与 Work 报告、关键事项为 unknowns / 处理中 Work / 非正式评审建议。辅色蓝紫区分 Business 橙。不展示搜索/通知、不造方案文档版本卡。

## Engineering 核心闭环

```text
+ 全局侧栏 + 项目 / Engineering / 当前任务                 状态 + 历史
+ 任务列表   + FDE交接与范围、输入采用、真实执行/提问/提交记录
+            + 本轮执行中 / 待答 / 待评审 及一个当前动作
+            + [查看提交] → 右侧固定提交证据（检查 → Diff → 产物）
+            + 按状态出现的补充/答复输入区       证据面板内业务评审
```

默认证据面板关闭；待评审可一击打开。宽屏面板约占可用内容 60%，使 Diff 可读；1280px 下可收起任务列表，1024px 下证据全宽覆盖但保留返回与焦点。不得同时出现常驻角色横幅、项目卡、Run 下拉、重复事件流和四个空证据 Tab。

| 用户所处状态 | 主操作与反馈 | 成功后应看到 |
| --- | --- | --- |
| 无 Task / 草稿 | 去项目/FDE 明确范围；已具备规格时“准备任务”，再“开始执行” | queue 仅就绪；start 202 是已登记 Run，Run queued 显示等待派发 |
| Run 执行中 | 默认看最近事件；可“记录补充”，详情菜单提供“停止本轮处理修改”/“取消任务” | 补充为 pending，原 Run 规格不变；停止请求显示待确认，不立刻变为已停止 |
| completed/needs_input | 原问题下答复，引用 question；先保存，再明确采用 | answer 从 pending 进入已采用规格后，“继续执行”创建原 Task 的新 Run |
| completed/submitted | 打开固定提交，先看检查与限制，再按需 Diff/产物 | 由 Task 的 review 决定是否可评审；有 pending 输入时可能回 draft，不能仅看 Run 提交就接受 |
| 要求修改 | 面板内填具体修改理由，保留当前提交引用 | 原 Task 回 draft，产生 pending change_request；明确采用完整新 spec 后准备/再启动 |
| 接受提交 | 核对最新提交、规格、所选固定产物，填写意见与检查依据 | 服务端确认 Task succeeded，旧 Run/产物/评审可查；不能显示“已上线” |
| 技术失败 / 确认停止后的 blocked | 展示真实 error_code/summary、证据和最后更新时间；允许时“重试” | retry 创建新 Run，可选可用模型修订，旧配置和失败保留；不承诺恢复同一模型指令 |
| cancel_requested / interrupted | 显示等待停止确认/现场不明及核查说明 | 不显示强制解锁、重开或“点击恢复”；现有 HTTP 无运维核查 API，运维确认后再读事实 |
| succeeded / cancelled | 只读历史，后续工作从项目建立有关联的新 Task | 原 Task 不重开，业务关联和固定版本可追溯 |

运行活动按轮次展开，不把 TaskEvent 和 RunEvent 生硬拼成一条全局 sequence；同轮按各流顺序及真实时间展示来源，不能保证不同流时间相同时有全局先后。默认跟随当前活动/最近 Run；用户选历史后锁定，标题清楚标“历史轮次，只读”。新 Run 出现时提示可返回当前，不能抢走阅读位置。

证据细节：

- 文件区首发是**固定产物列表**，不是沙盒文件树。Diff 来自服务端固定评审范围，只读并标基线/受检归档、截断和遗漏；不可把路径行构造成完整源码目录。暂无差异与证据缺失分开。
- 检查分“工程自测”“固定归档独立复验”，命令、退出码、timeout 按需查看；空数组/`validation_passed=null` 显示未验证，不能合成 `3/3`。二者与业务接受是三层事实。
- 当前 accept 接口检查非空依据、版本和 pending，不强制 `validation_passed=true`。建议 UI 对缺失/未通过证据先显示醒目缺口，评审需显式说明依据；若要硬性禁止接受，需要另行确认后端规则，不能只靠隐藏按钮新增领域规则。
- 表单内部绑定 Run/spec/Artifact/revision，无需用户手输 UUID/哈希。提交前重读，出现 409 保留草稿并解释哪项已变化；历史评审草稿不得沿新 Run 复用。
- 断网保留旧内容并标过期；重连按独立水位补读。已离开底部阅读时不自动滚屏，给“有新活动”；不持有模型 token 流、终端连接或 Worker 路径。

## 视觉与通用状态规范

| 设计项 | 建议值/约束 |
| --- | --- |
| 颜色 | 侧栏 `#1C1A35`，画布 `#F6F5FB`，白工作区 `#FFFFFF`，主动作 `#6148CF`，正文 `#23223B`，次文 `#5E5875`，边线 `#E5E2F0`；状态另有语义色并配文字 |
| 字体 | 系统中文字体 `Segoe UI / Microsoft YaHei / sans-serif`。页面标题 28px/600，模块标题 16px/600，正文 14px/1.5，辅助 12px。控件高 36px。代码用 Consolas 等宽，不下载字体 |
| 空间 | 侧栏 228px，内容左右 24px，模块间距 16px，卡片内边距 16px，圆角 12px。员工横幅 168px，视口不超过 1366px 时为 140px。场景图铺满横幅，标题在右侧浅底上。员工页左 38% 沟通、右 62% 工作 |
| 桌面适配 | 验收视口 1366×768、1440×900、1920×1080。1024 以下允许收栏与纵向排布；桌面主路径保持左聊右工作 |
| 品牌 | 保留六边形 OneFDE 标识及柴犬/白猫/熊猫/猫头鹰；角色身份用头像，业务状态用可访问组件；Office 原图裁切不能把四个角色裁掉 |
| 动效/可访问性 | 正文对比度≥4.5:1、键盘焦点可见，状态不只靠颜色；Drawer关闭回触发点，错误定位字段；150–200ms轻反馈，尊重减少动效 |

加载用区域骨架，不替换整页；真空数据显示可执行的下一步；读取失败给重试和最近成功时间；提交中禁重复但不抹草稿；取消中保持待确认；待验收写“等待业务评审”。不可用能力首发隐藏入口，确有必要解释时展示具体缺口，避免大量灰按钮。

需在实现前取得独立头像/办公室插画及可使用范围，参考图整页截图不能当交互背景。素材未齐可先用名称和已有合法图形验证布局；保留原型历史资产，正式素材不以临时生成角色替换。视觉稿与真实数据分别验收。

## Engineering 对话式改版提案

历史说明：2026-11-06 已做独立模拟原型，当前源码位于 `frontend/src/engineering-preview`，以 Task 活动主列、按需提交面板替代常驻复杂面板。本次保留这个减法方向，并补足真实数据、状态与能力边界；不是本轮重新实现或验证原型的声明。[历史预览说明](implementation.md#预览-fe1)

## 英雄场景接入（2026-11-07）

四角色使用用户提供的独立场景图，完整来源/尺寸见[美术验收](../operations/frontend-art-verification-20261107.md)。2026-11-07 质量治理把四套页头收成同一横幅：高 168px（窄桌面 140px），场景图铺满横幅，标题放在右侧约 280px 的浅底上：标题 22px，副标题 13px，状态单独一行并用圆点区分进行、等待和阻塞。Engineering 用半透明深色底。Business 是收件箱里的真实 Case，对话不能发送。FDE 右侧只保留需求与方案、任务拆解、交付状态。Engineering 没有 diff 时用浅色空态。Knowledge 默认按来源身份做关键词匹配。办公室待办不展示扫描上限和原始枚举。Engineering 的提交状态不作为固定检查通过依据。
