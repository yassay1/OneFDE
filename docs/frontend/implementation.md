# 四工作区实施与验收

## 员工对话闭环（2026-11-08）

仍用现有对话列和工作区。新增只读/追加问答，不替代客户消息、Work、输入或 Run。

| 页面 | 问答 | 仍须员工确认 | 工作区 |
| --- | --- | --- | --- |
| Business | `GET/POST /business/cases/{id}/assistant` | 放入回复框后，原「发送回复」或「记下备注」才写 Case | 原 Case 消息、状态、处理人 |
| FDE | `GET/POST /engagements/{id}/fde/dialogue` | 「登记目标」才创建 Work | 原 Work、delivery |
| Engineering | `GET/POST /tasks/{id}/dialogue` | 保存输入、采用、拒绝、准备任务保持原按钮 | 原输入、Run、补丁、产物元数据 |
| Knowledge | `GET/POST /knowledge/dialogue` | 无自动写入资产 | 同一次提问仍调用 `search_assets` |

`GET /runtime/status` 读取 `fde_agent` 与 `engineering_worker` 心跳。默认替身。迁移 `a7c4e1b90d22`。浏览器截图在本机临时目录：`business-assistant.png`、`fde-dialogue.png`、`engineering-dialogue.png`、`knowledge-dialogue.png`。

## 回退基线上的真实闭环（2026-11-08）

页面文件已与 `OneFDE-20261107.zip` 中同名文件在换行归一后一致。晚间收尾写过的前端接线不在这批回退页面里。本轮保持对话区与工作区布局，只接已实现 API。计划与证据目录：`.planning/four-workspaces-20261108/`。

| 阶段 | 页面 | API（已实现，本轮不新造聊天接口） | 模型 / 迁移 | 验证 | 验收 |
| --- | --- | --- | --- | --- | --- |
| B | Business 首页对话 + 既有 Case 详情 | `GET /business/cases` 带 workflow/state/owner；`GET /business/cases/{id}`；`POST .../actions` 的 reply/note 及其他既有动作；候选 search/list/invite | 无新模型、无迁移 | 每页改完后 `npm run build`；详情动作沿用现有业务测试 | 选中 Case 能看到原话/回复/备注；不能回复时说明真实下一步；筛选走服务端分页 |
| F | FDE 对话列 + 右侧项目栏 | `GET/POST .../fde/work`；未命中时 `GET .../fde/work/{id}`；`GET .../delivery` | 无新模型。消费者未授权则保持 pending | 同上 | 一项 Work 的目标、等待、报告、错误分开；报告不在左右重复；Task 进入 Engineering |
| E | Engineering 对话列 + 补丁工作区 | inputs、apply-inputs、actions、reviews、runs、events、review-evidence、artifacts | 测试不新开付费 Run | 同上；生命周期仍以现有任务测试为准 | 可补充、采用、拒绝；命令按状态出现；Diff 摘录与产物元数据不伪装成源码或下载 |
| K | Knowledge 对话列 + 结果栏 | `POST /knowledge/tools` 的 search_assets / get_asset | 无检索模型 | 同上 | 关键词结果带来源、版本、验证和限制；切换用途清空临时反馈；返回保留 run/work |

不改全局导航和顶栏。不把 Case 做成客户档案，不把 Work 做成聊天历史，不把 Diff 做成文件树，不把清单检索做成语义 RAG。

本轮验证（同一演示库 `localhost:8003`，已有登录会话）：

| 检查 | 结果 |
| --- | --- |
| `frontend` 下 `npm run build` | 退出 0。最后产物 `index-BFyHlttI.js` |
| Business | 选中 Case 后出现客户原话、对外回复、内部备注。`POST .../actions` 记内部备注返回 200。整页刷新后备注仍在 |
| FDE | 鲜果报价项目显示一条 pending Work，文案为已登记、没有消费者不会生成报告。右侧未知项正常换行。Task 链到 Engineering |
| Engineering | 同一 Task 显示待处理 clarification、采用/拒绝、补丁摘录空态、产物元数据空态。未点准备任务 |
| Knowledge | 关键词「报价」返回 `fresh-quote-compare-csv@1.1.0`，详情含验证状态、输入输出和限制。返回链接回到原 project 与 task |
| 后端 | 未改 API 或迁移，未重跑 pytest，未新开模型请求 |

服务日志里上述 POST 为 200，未见本次操作的 5xx。客户公开入口的 note 隔离本轮没有在 8765 上重放。

## 产品实现收尾（2026-11-08）

上午审计写的“尚未开始页面整改”到同日晚间已经过时。六页接在 `frontend/src/features`，由 `http://localhost:8003` 提供构建结果；客户演示仍在 `http://127.0.0.1:8765`。本段只记录已经落地的行为和未完成项。上午的 W0 原文保留在下一节，当作当时的审计记录。

| 已落地 | 仍未完成 |
| --- | --- |
| Case 列表可按 workflow、state、owner、engagement_id 在服务端过滤，游标范围随过滤条件变化 | 全库经营指标、客户档案和外部渠道 |
| FDE `work-history` 分页和单条 `work/{id}` 读取；旧的最近 50 条列表仍可用 | 普通 Work 的模型执行。登记后保持 pending，直到有消费者、配置和费用授权 |
| Office 待办带项目、Case、Task 和深链；草稿待采用输入计入任务原因 | 全公司统计、在线状态 |
| Engineering 已接受或历史轮次只读；固定 Diff 来自 review-evidence；历史轮次按该 Run 的规格版本显示 | 把模型修订或配置成功说成 Worker 在线 |
| Knowledge 切换用途会清查询缓存和当前资产；公开用途只保留摘要投影；返回链接保留 project/case/task/run/work | 持久咨询记录、历史资产版本库 |

模型请求限额不在页面上显示为已合规。2026-11-08 的付费 Run 记录了 11 条响应，授权是 10。迭代额度不是逐请求上限。收尾改为在转发前计数，证据见[测试与验收](../operations/testing.md#产品工作台收尾2026-11-08)。

## 四工作区重新对齐（2026-11-08 上午审计）

状态：**以下是 2026-11-08 上午的调研记录。** 当时方案待确认，尚未开始页面整改。历史 F1—F6 和后续视觉验收保留在下文，不代表当时路由仍具备全部历史行为。同日晚间实现见上一节。

本轮完成证据：四域ORM/Pydantic/Router/Service/Queries、Agent入口与Tools/Runtime、Worker回填与停止、迁移链与相关测试断言、前端路由/Query/类型/组件实际阅读；运行JSON 44项操作与YAML 44 implemented+1 planned核对；五类成熟产品官方资料；四页线框、逐模块11项映射与A/B/C/D分类。详见[设计](design.md)、[映射](api-mapping.md)、[架构补充](architecture.md#四工作区状态与更新补充2026-11-08)。

仅更新既有前端文档、总实施计划及`.planning/workspaces-audit-20261108/`记录；未改业务代码/API/数据库/前端页面，未装依赖、调用模型或部署。静态审计不能证明当前运行环境可用；历史测试通过记录不作为本轮重跑结果。

### 建议实施顺序（需要后续确认）

| 阶段 | 范围与需求关联 | 验收标准/完成证据 | 后端依赖 |
| --- | --- | --- | --- |
| W0 本轮审阅 | 四角色职责、线框、语义、数据映射与待确认规则；P01—P10 | 用户可逐页确认默认对象、主要操作、A/B首批范围；文档链接/字段/API/确认状态检查完成 | 无；本轮到此停止 |
| W1 能力表达与闭环缺口修正 | Engineering输入采用/拒绝与规格/历史入口；去伪代码/伪完整日志；Knowledge用途切换清临时内容；Business首页去禁用通聊；FDE准确命名/不重复报告；P01/P02/P03/P07/P10 | 当前真实路由可保存→采用/拒绝→新版本；多问题答复明确；closed/历史只读；Diff/null/截断分开；公开用途无残留内部内容；无空Tab/伪统计；实际build和浏览器矩阵 | A/B，不新增API；接受硬门槛规则保持现状 |
| W2 数据完整与导航恢复 | sequence/cursor补页、采用状态重取、外部终态缓存失效、历史Run读取对应规格、Work/Case/Task/Run往返；P02/P05/P07 | >100事件/输入、>50Run跨页不丢；外部Worker终态出现产物/证据/新Run；两标签409保草稿；URL刷新/前进后退不串对象；无事件与API错误不回落样例 | A/B；Work>50深链列C2受限，不冒充可完成 |
| W3 四角色页面组织落地 | 按线框调整默认视图/主次信息/按需展开；P01—P07/P10 | Business收件箱与找店分入口；Case右栏有源事实与状态主操作；FDE以Work目标/报告/Task依据为主；Engineering活动与固定提交分开；Knowledge检索列表/详情；1600/1280/1024/360和200%缩放、键盘/焦点通过 | A/B；未落实C不出现操作入口 |
| W4 已确认后端增量 | 优先C1全库筛选、C2 Work完整读取、C4状态原因；真实受限资料前C8；P01/P02/P07/P09/P10 | 先确认各C条规则/契约，再加权限/迁移/服务测试；Pydantic导出运行JSON+YAML status一致，前端真实同源联调 | C独立审批范围；不默认一次全做 |
| W5 后续交付/资产能力 | 按需求选择C3事实台账、C5持久事件、C6交付记录、C7下载、C9资产版本；P02/P08/P09/P10 | 固定版本/权限/来源/字节/访问有真实证据；发布需实际访问及授权，资产验证不靠模型总结 | C；D项无本轮开发计划 |

W1优先解决当前可见错误，不以C类平台建设作为A/B整改前置。页面组织W3可在W1/W2边界稳定后逐页审阅，不能用视觉完成代替写路径验证。没有新的模型额度授权时使用明确标识的确定性夹具与受控HTTP，真实工程另行记录。

### 必须复演的交互矩阵

以下均为**后续验收要求，本轮未执行**。已存在后端测试是约束依据，网页必须独立验证挂载与交互；Storybook或等效状态夹具只证明组件，不能证明真实API/Worker。

| 场景 | 验收操作与预期 | 领域依据 | 所需证据 |
| --- | --- | --- | --- |
| Business内外隔离 | 预览澄清不发送；新客户消息到达使草稿过期；note不进公开View；员工Bearer与客户Cookie不混 | test_business的faq_scope、clarification_preview、public_preflight | 同源内部/产品Origin请求、页面与公开回读，不含token |
| Business交接/售后 | 无具体意愿不交接；Task接受后仍待客户；复试通过closed，失败回fde_queue并关联后续Task | test_candidate_sample_invitation_and_customer_consent、test_retest_keeps_fixed_version_and_customer_confirmation | Case/Task/Review/notice关联与客户回执；人工不能代通过 |
| FDE目标与报告 | 202仅登记；无消费者显示待处理；reported含error不成功；建议不新增TaskReview；普通Work不扩大grant | test_scope_stale_evidence_and_ordinary_work、test_restart_replay_dispatch_and_advisory_review | Work ID、Task revision、report/trace、正式Review计数；旧目标不串新项目 |
| Engineering补充/采用/续作 | running保存pending不改本轮；停确认后采用；回答引用原题；新Run固定新版本 | test_pending_input_never_changes_running_snapshot、test_three_runs_answers_changes_and_acceptance | 当前主路由截图+HTTP序列、spec_version/applied_input_ids，无后台脚本代替页面采用 |
| Engineering停止/故障 | stop_for_update与cancel分开；cancel_requested不称已停；interrupted不能retry/解锁 | test_claimed_stop_waits_for_confirmation、test_interrupted_holds_global_slot_and_retry_is_not_recovery | Run/Task/槽占用与可见操作；未启动模型也可用确定性控制验证 |
| Engineering评审/历史 | 当前固定提交accept/request_changes；陈旧Run/spec/Artifact或pending按真实规则处理；历史按TaskVersion读 | test_review_version_artifacts_pending_and_role、test_sequence_pagination_versions_auth_and_missing | Review固定引用，修改生成pending；历史不可写；新Run不抢选择 |
| 分页与缓存 | >100事件/输入、>50Run；外部结束/采用变更后证据与输入状态刷新；断线重连去重 | queries.sequence_page/page、前端Query；W2补新增前端验证 | 游标序列、完整数量与去重、null证据失效，不把首次页数量当总量 |
| Knowledge用途/回原工作 | 内部查询后切public仅摘要，临时lines/旧detail不泄漏；restricted列表无记录、get404；复制不是采用 | test_knowledge_search_get_and_permission、access.py | 三角色×三用途、站内返回project/case/task/run/work、页面无内部残留 |
| 通用交互与语义 | 加载/空/失败/过期/提交中/冲突/缺证/截断；键盘操作、关闭回焦点；刷新深链恢复 | 设计状态与真实Schema；官方Storybook交互实践 | 状态夹具+真实HTTP分列，尺寸/缩放检查；无模拟回退 |

### 检查与停止条件

后续实现使用实际package.json中的build命令，后端改动按backend/README.md执行锁定检查；不把尚未安装的test/e2e/Storybook脚本写成现成命令。涉及WSL/模型环境时先读ADR0007与local-wsl手册，分别记录环境就绪、真实工程成功、正式隔离验证。

完成一阶段记录：修改范围、实际命令/退出码、数据性质、页面操作与截图、请求/对象/版本关联、未完成项。只读和纯前端修正不运行无关模型；需要真实模型/外发/部署时单独明确授权范围。当前W0文档完成后停止，等待用户确认，不实施W1。

## 历史实施记录（2026-11-07及以前）

# 前端分阶段实施与验收

状态：2026-11-07 **F1–F6 UI** 已落地，同源阶段 A 和 Office 有限派生流已有本地验收；最新美术与只读回归见文末。模型阶段与完整覆盖范围仍以[总实施计划](../development/implementation-plan.md)和 API coverage 为准。本轮不调用模型或部署。对应 [PRD](../product/PRD.md) P01–P10 和[测试场景](../operations/testing.md) V02–V10、HM03/HM05/HM07/HM08。

## 阶段与依赖

下表保留设计时的分期基线；后续完成状态以文末证据与总实施计划为准。

F1→F2为首条前端交付主线；F3接项目组织，F4先补跨角色检索，F5再整理现有经营工作，F6最后做全局聚合。现有Business/FDE功能在迁移中保留，不因排序撤下。按验收门槛推进，不预先承诺日历工期或一次实现五页。

| 阶段 | 实施范围 | 后端依赖与新增API | 可检查的退出条件 | 阻塞/不纳入 |
| --- | --- | --- | --- | --- |
| F0 本轮设计准备 | 逐图观察、当前代码/契约审计、五页设计、架构与分期 | 仅读现有代码/文档和官方资料 | 四份前端文档、需求/接口来源、缺口与验收清楚，链接/文档边界检查通过 | **已确认**；进入 F1 |
| F1 基础框架与公共组件 | 在现有工程整理AppShell/六入口导航（Office+项目中心+四员工）、主题、上下文路径、认证反馈、AsyncState；先迁移一个真实项目只读工程视图，保留旧深链接。领域类型对齐已实现契约、收敛API Client/Query keys | 现有auth/engagement/task/run/evidence/artifacts即可；**不要求新增API**。G0文案整理可独立提交后端变更 | 同源登录/退出、刷新与前进后退可恢复项目/Task；真实提交可查看；401清私有缓存；无数据/失败/证据null清楚；mock不进真实适配；构建和桌面键盘/缩放检查通过 | **代码与 `npm run build` 已通过**；真实同源浏览器联调待有运行中的 API 时补证据。正式头像可后补；不做五页内容、不开放新命令/聊天/文件树；本阶段无需模型调用 |
| F2 Engineering真实闭环 | F1通过；补Run历史、独立事件流、Task输入/采用、queue/start/continue/retry/stop/cancel、固定提交/自测/复验/正式评审；先隔离库确定性控制，再真实Worker烟测 | 现有17项工程核心操作（见下文集合）及auth/项目即可，**闭环零新增API**；G1文件/下载、G2实时工具事件不作为门槛 | 同Task待答→保存→采用→新Run；要求修改→采用新spec→新提交→接受，旧证据可查；并发/重复/停止/失败边界通过。真实Worker步骤另记Task/Run/spec/产物摘要、实际文件/检查/接受证据 | **UI 与 `npm run build` 已落地**；同源浏览器确定性控制/真实 Worker 烟测仍待运行环境与授权。不新增强制恢复/发布 |
| F3 FDE与项目中心 | F2稳定；项目目标/Task索引、来源/未知项、Work登记与报告/trace、关联原Case与工程；方案建议和规格确认分开 | 现有delivery、fde/work、fde/tools、Task输入与reviews、Business关联；首发不新增。多轮chat/正式方案版本为G3另议 | 原Case→项目Work→原Task→固定提交→正式评审→原Case可往返；Work pending/processing/reported及错误/等待区分；报告不自动接受Task | **UI 与 `npm run build` 已落地**；缺消费者保持待处理文案；真实模型验收须有效授权。50条Work上限已标明；不做文档管理/估算排期 |
| F4 Knowledge只读支持 | F3上下文稳定；带用途检索、结果/资产详情、当前版本引用、限制和获准来源、返回原工作 | 现有knowledge/tools（search/get），无新增API；历史版本/业务资料/维护为G4 | 三角色来源入口均可查询；public_marketing无私有实现字段、restricted列表不出现/get404；无结果不编造；换用途不会串缓存；引用含实际版本且可回来源 | **UI 与 `npm run build` 已落地**；多用户/真实受限业务资料推广前先补实际身份/范围授权。无Knowledge模型也能完成只读检索，不造咨询记录 |
| F5 Business经营跟进 | 在现有Case/候选页换统一壳，优化原话/内部备注/待办/交接/复试与FDE反馈；不重新建设后端 | 现有cases/actions/clarification-draft/candidate系列，首发无新增；CRM为G5后置 | 一条咨询与一条售后从原Case推进，公开/内部不混；接管阻断自动回复按服务端事实验证；水位过期保留草稿；候选sample与真实来源区分；工程接受不自动关闭售后 | **UI 与 `npm run build` 已落地**；咨询/售后真实推进与高德配置仍待运行环境。外部消息渠道、客户档案、漏斗、商机/计划不在本期 |
| F6 Office全局动态化 | 五页数据适配稳定后做公司待办、近期动态和可溯源角色工作摘要，复用原对象入口 | 完整全局版需要G6聚合与统一覆盖范围/分页；此前只做有标记的有限摘要或静态角色入口 | 源状态与待办一致；聚合返回原Case/Task/Run引用可直接处理；刷新不会重新出现已处理事项；无N+1全项目轮询；无心跳不显示在线状态 | **有限摘要 UI 与 `npm run build` 已落地**；全公司待办/活动验收仍阻塞于 G6。营收/效率统计/通知系统后置 |

F2的17项核心操作：getTask、listRuns、getRun、listTaskInputs、appendTaskInput、applyTaskInputs、actOnTask、listModelProfiles、listTaskEvents、listRunEvents、listTaskVersions、getTaskVersion、getRunReviewEvidence、listArtifacts、listTaskReviews、reviewTask、updateTaskSpec。项目/创建另用已有入口；完整方法/字段在[API清单](api-mapping.md#engineering-真实接口清单)，不以操作数替代验收。

## F2验收矩阵

| 场景 | 数据与动作 | 必须观察到的结果 |
| --- | --- | --- |
| 真实只读与历史 | 使用已存在且获准的Task、多个Run和固定提交 | URL刷新恢复；历史只读；Run/Task/project归属一致；证据null或截断如实显示，不回退模拟Diff |
| 待答续作 | 隔离库准备needs_input，浏览器保存并采用对应answer，再continue | pending→applied明确；spec_version递增，新Run引用答案，原Run不变；未采用不允许继续 |
| 修改再提交 | request_changes→采用完整spec→queue/start→新提交→accept | 原Task延续，旧Run/产物/评审保留；没有把要求修改当聊天热更新；接受才succeeded |
| 输入并发与幂等 | 两标签持同revision提交；同意图重复请求；模拟响应丢失 | 409保留草稿、重读核对；相同键不重复写入；改正文不复用原键；结果未知先查询 |
| 轮询与断线 | 多页sequence、重连、后台/前台切换、Run终态 | 各流无漏重；同Run终态后证据重新读；历史不抢焦点；终态/隐藏页无持续高频轮询 |
| 停止/失败/未知 | 未认领取消、已认领停止、failed重试、interrupted保留占用 | 停止请求不算停止；cancel与stop_for_update区分；失败保留原因；不明现场无重试/强制恢复；全局工程槽冲突可解释 |
| 固定评审 | 旧Run、错spec/产物、pending输入、证据缺失/复验失败 | 错绑定服务端拒绝；当前check_evidence约束可见；缺失证据不标“通过”；UI不擅自新增服务器未定的硬性接受规则 |
| 真实Worker子验收 | 获准小任务由现有Worker/OpenHands执行 | 真实改文件/命令、受检归档与独立复验、Run结果和所有者接受一致；明确实际环境/模型/费用/访问范围，不算公网交付 |

确定性测试覆盖状态控制，fixture覆盖展示，两者不当作真实工程执行；真实Worker子验收不必为每条失败边界花费模型调用。已有本地MiMo/DeepSeek证据可作能力依据，新前端仍须有自己的实际HTTP与浏览器证据。

## 检查策略与证据格式

F1/F2按需增加少量开发测试依赖（当前未装Vitest/Testing Library/Playwright/Storybook）。优先验证游标、对象归属、终态失效、草稿隔离、409和评审绑定；不为纯视觉token和简单Ant Design包装编写镜像实现测试。组件状态至少包含加载/空/错误/过期、运行/待答/待评审/已接受、缺证据/截断、提交中/冲突。Storybook等独立组件库验收工具待真实复用需求出现再启用。

实际实现后使用[现有package脚本](../../frontend/package.json)的 `npm run build`（`tsc --noEmit && vite build`）；当前只有build，无dev/test/e2e脚本，不编造既有命令。后端受影响时用[后端README](../../backend/README.md)的锁定检查。新增测试/生成脚本随相应阶段提交并记录真实命令；实现变更执行实际构建，设计准备阶段未安装或构建。

浏览器主验收为1600×900、1280×800、1024×768、200%缩放；检查键盘可达、焦点不遮挡、长Diff局部滚动、证据面板关闭回焦点、慢网/无数据/错误。真实HTTP在可信Origin上验证Cookie/CSRF；开发localhost与Compose的127.0.0.1:8002以实际配置区分，不混用。操作WSL/Worker环境前按[ADR0007](../architecture/ADR/0007-local-wsl-development.md)和[WSL手册](../../backend/local-wsl/README.md)，分别记环境就绪、真实工程成功、正式隔离结果。

每阶段完成证据应记录：日期/提交或工作树范围、数据性质（fixture/确定性控制/真实模型）、实际命令和退出码、浏览器操作与截图、请求ID及Task/Run/spec/产物摘要、未满足条件。不记录凭据。状态摘要只更新[总实施计划](../development/implementation-plan.md)，实际运行验收维护在[测试与验收](../operations/testing.md)；无实际部署与访问证据不标已交付。

## F1 落地说明（2026-11-07）

用户已确认：任务活动主视图 + 按需提交面板；首发无文件树/下载；本轮只做 F1。

已交付：
- `AppShell` 六入口（办公室 / 项目中心 / Business / FDE / Engineering / Knowledge）与紫系主题。
- `#/engineering?project=&task=&run=&view=submission` 真实只读：任务列表、Run 活动/事件、固定证据 Drawer（检查/Diff/产物元数据）。
- 保留 `#/projects/:id`、`#/business` 深链接；项目详情暂留原评审写入口（F2 再迁入提交面板）。
- `src/api` 客户端、Query keys、与已实现契约对齐的领域类型（未新增 npm 依赖；`openapi-typescript` 生成器可在后续安装后替换）。
- 构建证据：`frontend` 下 `npm run build`（`tsc --noEmit && vite build`）通过。

未纳入 / 待补：真实同源浏览器联调截图、正式角色头像。

## F2 落地说明（2026-11-07）

用户确认按计划推进 F2 后实施。Engineering 页现支持：

- 输入 ledger：保存 clarification / answer / change_request（幂等键）；采用答复或沿用完整规格采用待处理项；409 保留说明并重读。
- 运行命令：queue / start / continue / retry / stop_for_update / cancel；模型修订选择；interrupted 不提供强制恢复。
- 提交面板内正式评审：accept / request_changes，绑定 Run/spec/产物；证据缺失或复验未通过醒目提示，不由前端新增硬性领域规则。
- 历史轮次锁定时禁用写操作；写成功后定向失效 Task/Run/inputs/delivery 等 Query。

构建证据：`frontend` 下 `npm run build` 通过。真实 Worker / 隔离库浏览器矩阵仍需有 API 与（如需）模型授权时补做。

## F3 落地说明（2026-11-07）

- 项目中心：`#/projects/:id` 展示来源/未知项、任务目标摘要、Run 摘要、按状态分组的 Task 索引；正式执行/评审深链到 Engineering；保留 `case`/`task` 参数。
- FDE：`#/fde?project=&case=&work=` 左栏 delivery 摘要，右栏异步 Work 登记与报告/trace；评审建议标明「非正式」并链到 Engineering 正式评审；报告不自动接受 Task。
- 项目详情不再内嵌完整评审表单，避免与 Engineering 双入口冲突。
- `npm run build` 通过；零新增 API。

## F4 落地说明（2026-11-07）

- `#/knowledge`：角色（business/fde/engineering）× 用途（delivery/internal_research/public_marketing）× 关键词检索；详情展示版本/限制/来源；复制 `id@version`；`from/project/task/case` 可返回原工作。
- Query key 按 role+purpose+query/asset 隔离；切换角色/用途清空 Knowledge 缓存。
- public_marketing 仅公开摘要；get 404/空结果如实显示；不提供图谱/上传/handoff 写入入口。
- Engineering/FDE/办公室提供入口链。`npm run build` 通过。

## F5 落地说明（2026-11-07）

- `#/business`：统一壳 + ContextTrail；Case 收件箱与找店候选分 Tab；当前页本地过滤 workflow/state/owner；列表突出 `next_step`。
- `#/business/:caseId`：当前下一步横幅；会话记录区分客户原话 / 对外回复 / 内部备注；售后标明「工程接受不自动关闭」；动作选项标注对外/内部。
- 交接与复试用现有 actions；链到 FDE / 项目中心 / Engineering / Knowledge；澄清草稿水位过期须重预览。
- 候选：模拟样例 vs 高德 POI 徽章；邀请链接标明「仅生成、未自动外发」。
- 零新增 API；`Business.tsx` 改为 re-export。`npm run build` 通过。

## Business 视觉精修第二轮（2026-11-07）

- 页头：狐狸/犬员工头像（`public/avatars/business.png` ← `紫光耳机萌犬头像.png`）、Business 名称、职责说明、本页状态胶囊。
- 收件箱：双栏（Case 列表 + 本页需跟进摘要）；Tab 仅「Case 收件箱 / 找店候选」；不做客户/商机/跟进日历假 Tab。
- 详情：会话记录为主栏；右侧当前 Case 事实、交接与处理动作；下一步横幅用暖橙辅助色。
- 延续 Office 紫系 + 圆角/阴影；橙色 `#E07A3A` 为 Business 辅色。零新增 API、无漏斗/CRM 假数据。

## Business 对照精修续（2026-11-07）

- 对照 `OneFDE客户经营助手仪表盘.png`：默认 Tab「对话工作台」为创始人↔Business 对话壳（输入禁用，**不接 LLM**）；回复区嵌入本页真实未关闭 Case 卡片。
- 右侧三块均来自本页 Case：当前关注、状态分布（非全库商机漏斗）、需跟进 next_step。
- Tab：对话工作台 / Case 收件箱 / 找店候选；不做客户档案/商机/跟进计划假入口。
- 英雄区：头像 + `business-hero-scene.png` 已安装（见文末美术接入记录）。

## Knowledge 视觉精修（2026-11-07）

- 对照 `知识工作台：售后换新智能检索.png`；延续四角色英雄区模式。
- 页头：猫头鹰头像 `public/avatars/knowledge.png` ← `紫色背景下的学者猫头鹰.png`；场景 `knowledge-hero-scene.png` 已安装。
- 主区：角色×用途检索、类型徽章结果卡、资产详情与复制引用；右侧为来源上下文、**本页检索**类型分布、选中摘要、能力边界说明。
- 不做知识图谱、虚构全库数量、最近沉淀流、空 Tab 对话、上传维护；零新增 API。
- `npm run build` 通过。其他角色页未改行为。

## Engineering 视觉精修（2026-11-07）

- 对照 `OneFDE 工程工作间界面.png`；延续 Office/Business/FDE 英雄区模式。
- 页头：熊猫头像 `public/avatars/engineering.png` ← `紫色霓虹耳机熊猫头像.png`；场景 `engineering-hero-scene.png` 已安装。
- 当前 Task 进度条由真实 Task/Run 状态派生；主区仍为任务活动流；「查看提交」加宽抽屉含 Diff/检查/产物/正式评审。
- 不做文件树、交互终端、假通过数、聊天快捷墙；零新增 API。
- `npm run build` 通过。其他角色页未改行为。

## FDE 视觉精修（2026-11-07）

- 对照 `OneFDE方案交付工作台.png`；延续 Office/Business 紫系壳与英雄区模式。
- 页头：白猫头像 `public/avatars/fde.png` ← `戴圆眼镜的白猫头像.png`；场景 `fde-hero-scene.png` 已安装。
- 布局：左主区交付工作区（Work 登记/报告气泡）+ 右栏项目方案工作台（阶段派生、目标与来源、Task/报告产出、关键事项）。
- 不做 需求/方案/交付/文档 空 Tab、假快捷动作、假方案版本或假进度勾选；零新增 API。
- `npm run build` 通过。Office / Business 未改行为。

## F6 落地说明（2026-11-07）

- `#/` 办公室：双栏「四员工 + 需要你处理」、项目摘要与本页近期动态；深链回 Case / Task / FDE Work，不在 Office 勾选完成。
- 有限范围硬顶：项目列表 ≤8；服务端 Office 派生流扫描上限见 coverage 文案。明示覆盖范围与最近读取时间。
- 角色 cue 只反映本页可见工作归属；无心跳、无在线/空闲、无营收/周统计。已关闭 Case / 已接受 Task / 无错 FDE 报告不进「需要你处理」。
- 零新增 API（G6 聚合未实现）；`npm run build` 通过。全公司待办验收仍待 G6。

## Office 状态气泡（2026-11-07，功能优先）

- 场景：`OfficeScene` + `public/office-scene.png`；四热区点击进工作台；胶囊气泡含状态点与短文案。
- 映射：`features/office/roleStatus.ts` ← `GET /api/v1/office/actionable` + `activity`（不扩覆盖、不新 API、不调模型）。
  - Business：`founder_queue` → 等待创始人；其它未关闭 Case → 跟进/澄清等；activity 关闭 Case → 最近完成；否则「暂无可确认动态」。
  - FDE：报告含错误优先；`processing`/`pending` → 方案设计/待处理；已完成 Work → 最近完成。
  - Engineering：`review`/`waiting_input` → 等待创始人；`running`/`queued`/`blocked` → 开发相关；Run/Review 动态 → 最近完成。
  - Knowledge：固定「暂无实时动态 · 待命」。
- 失败：双侧无数据且失败 → 气泡「状态读取失败」；单侧失败 → 用已读侧派生并提示部分失败。保留 coverage / read_at。
- 未做：角色动画、抠图、Rive/Three、扩大 F6 数据范围。

## Office 视觉精修第一轮（2026-11-07）

- 范围仅 Office（及共用 `AppShell` 品牌/导航文案）；不改 Business/FDE/Engineering/Knowledge 页内容。
- 视觉：时间问候、双栏（场景 + 待办/团队动态）、底部「在推进的项目」真实 Engagement 摘要；侧栏副标「AI 技术服务公司」、中文主导航。
- 气泡：HTML 叠加真实 `roleStatus`；场景已换干净底图 `温馨AI办公休闲空间.png` → `public/office-scene.png`（1600×900），已去掉 interim 遮罩。
- 边界：无假搜索/通知角标、无虚构进度步进/员工动态；零新增 API；未引入动画框架。
- 构建：`frontend` 下 `npm run build` 通过；浏览器对照 `localhost:8000` Office。
- 员工标准头像资产：已安装，沿用四角色现有头像。

## 预览 FE1

历史保留：2026-11-06已有独立 `frontend/engineering.html` 和 `src/engineering-preview`。它使用fixture和内存写入，刷新恢复样例；之前的构建/浏览器证据见[总计划历史节](../development/implementation-plan.md#web-工作台-下一阶段规划2026年11月6日)。本轮未启动或重新验证它；历史本地地址不保证仍在服务。后续查看按现有Vite配置启动，真实联调另走可信API Origin，不能把原型操作当后端结果。旧FE1/FE2/FE3编号只作历史，本轮后续执行按上方F1–F6重新确认范围。

## Web 回归与美术接入（2026-11-07）

本轮授权为现有 SPA 小完善：四张用户生成的场景已安装；头像移至右下，移除加载时的待替换文案。未新增后端 API、依赖或模型调用。

修复 401 会话查询清理导致登录加载不结束、项目/Case 非法 UUID 请求、侧栏/页头 Knowledge 链接丢项目、FDE 换项目残留 Case。Engineering 先确认项目/Task/Run 归属再读轮次，错误关联不再回退另一任务；提交状态不再显示固定检查已通过；Knowledge 关键词随浏览器历史同步。

构建与浏览器证据统一见[实际验收记录](../operations/frontend-art-verification-20261107.md)；已安装资产清单见[资产记录](../../.planning/ASSET_BACKLOG.md)。历史阶段结论保留，不代表本轮新增模型/工程/公网验收。

## Knowledge 页头单页预览（2026-11-07）

按用户参考图仅调整 Knowledge：面包屑与横向场景页头铺满内容列，标题/状态与短说明叠在图上。首次预览用矮横幅、图片左侧定高和渐变填充右侧，造成原图书架缺失；根据用户反馈改为按原图 5:2 比例完整铺满，去除遮罩和右侧填充。页头没有搜索框、通知或账户按钮；资产检索仍在下方工作区，能力限制说明也保留在那里。未改其他四页、后端接口或数据。`npm run build` 通过；浏览器在 `http://localhost:8000/#/knowledge` 检查 1280、1600 宽度，截图见[Knowledge 页头预览](knowledge-top-preview-20261107.jpg)。待用户验收后再决定是否推广。

## FDE 整页单页试稿（2026-11-07）

按用户提供的 `OneFDE方案交付工作台.png` 试改 FDE 一页。FDE 路由下的侧栏分为办公室/项目中心和四角色头像导航，账户留在左下；面包屑 56px、场景页头 170px，右上是现有真实项目选择，左主栏与右项目栏从约 236px 开始。场景由已安装的 FDE 图在 CSS 中分层展示人物与方案元素，去掉重复头像和页头多余链接。右栏四步从真实 Work/Task 派生并横排；没有 Work 时把“登记目标”表单移到空状态前，不伪造对话。此试稿的公共壳视觉仅在 FDE 路由启用，其他角色页未推广；无新 API、模型调用或虚构数据。

`frontend` 下 `npm run build` 通过；在 `http://localhost:8000/#/fde?project=…` 检查 [1600 首屏](fde-one-page-preview-1600-20261107.jpg)与 [1280 首屏](fde-one-page-preview-1280-20261107.jpg)。示例为本地已有的 C0+C1a 模拟项目；实际 FDE Work 为空，截图中如实显示登记表单与空状态。待用户验收设计方向。

用户随后指出 FDE 场景右侧也被视觉淡化。已移除右侧背景层的透明度，保留原素材右侧原色与场景细节；仅在两层同源图的交界处做融合，未用渐变填充右侧。重新构建并更新 1600 首屏截图。素材原图右端本身为浅紫背景。

## Business 整页单页试稿（2026-11-07）

按 FDE 试稿方向改 Business：侧栏在 Business/FDE 路由共用「AI 员工」头像导航（`shell-role-preview`）；面包屑 56px、黄昏办公室场景通栏 170px（`business-hero-scene.png` ← `黄昏时分的温暖办公时光.png`），去掉页头叠头像与多余链接；Knowledge/回办公室收到顶右工具条。下方仍为真实能力：对话工作台壳（输入禁用）+ 右侧本页 Case 展示，及 Case 收件箱 / 找店候选 Tab。无新 API、模型调用或虚构 CRM/漏斗数据。`frontend` 下 `npm run build` 通过。待用户浏览器验收。

## Knowledge 精简（2026-11-07）

Knowledge 改为与 FDE/Engineering 相同的 170px 横幅和左对话、右工作区。检索词从对话发送，仍调用 `search_assets` / `get_asset`；角色默认跟随来源入口，用途默认交付复用，两者收在对话标题旁。右侧只保留结果列表和选中资产详情（含复制固定版本引用）。去掉关键词大表单、图谱/管理/沉淀入口、结果分布、上下文卡和能力边界列表。没有对话历史接口，本页连续提问只留在当前页面。`npm run build` 通过。

## FDE 双栏工作间（2026-11-07）

FDE 与 Engineering 共用同一套左对话布局（`eng-chat-col`）。左侧把已有 FDE Work 的目标、排队/处理状态、报告、澄清和工具名显示成对话；底部输入仍 `POST /engagements/{id}/fde/work`，不再保留登记表单。右侧仍是项目方案工作台（目标、未知项、Task、关键事项）。没有新的多轮聊天接口，未造对话数据。

## Engineering 双栏工作间（2026-11-07）

按参考图把 Engineering 改成横幅 + 左对话 + 右代码区。左栏用真实 Task 输入和 Run 事件组成对话，发送走 `POST /tasks/{id}/inputs`；执行进度继续轮询 `GET /runs/{id}/events`（没有 SSE）。右栏文件树和代码只来自 `review-evidence.diff` 里的真实路径与补丁；没有文件目录/文件内容接口，未提交时显示空状态。检查结果用同一证据里的 `self_checks` / `validation_checks`。运行与正式验收收在「运行与验收」，不另造文件树或通过数。`npm run build` 通过。

## Engineering 整页单页试稿（2026-11-07）

同理按 FDE/Business 试稿改 Engineering：`shell-role-preview` 扩到 Engineering；霓虹熊猫场景通栏 170px（`engineering-hero-scene.png` ← `霓虹代码中的熊猫程序员.png`），去掉叠头像；**顶栏只放项目选择**（避免与面包屑叠字），Knowledge/FDE/项目中心放右栏。下方对齐「左任务活动 / 右工程工作区」：左为真实活动流与输入；右为进度、提交证据（原抽屉改嵌右栏）与评审记录。不做文件树、假 3/3、聊天快捷墙。无新 API/模型。`frontend` 下 `npm run build` 通过。待用户浏览器验收。
