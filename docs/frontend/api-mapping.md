# 前后端能力与接口映射

## 2026-11-08审计基线

本节及后续 2026-11-08 章节优先于文末历史表。范围为当前工作树，不是 Git HEAD。上午审计当时未调用模型、未启动 Worker，也不把测试文件存在写成“本轮测试通过”。晚间复核的契约数量见下段；当次检查结果写在[测试与验收](../operations/testing.md#产品工作台收尾2026-11-08)，不回写到上午记录里。

2026-11-08 员工对话后，[运行 JSON](../architecture/openapi.implemented.json) 为 **55** 项已实现 HTTP 操作。新增 Case 助手、FDE/Task/Knowledge 问答和 `GET /runtime/status`。这些问答不是客户消息、Work、输入或 Run。

2026-11-08 晚间复核：[运行 JSON](../architecture/openapi.implemented.json) 为 **46** 项已实现 HTTP 操作。[YAML](../architecture/openapi.yaml) 另有 1 项 `planned`：`GET /api/v1/artifacts/{artifact_id}/download-url`。上午审计写的 44 项未计入同日新增的 `GET /engagements/{id}/fde/work-history`（`pageFdeWork`）和 `GET /engagements/{id}/fde/work/{work_id}`（`getFdeWork`）。旧的最近 50 条 `listFdeWork` 仍保留。规划下载不在运行服务内，前端不可调用。部分 description 仍写“未接 Worker”，需结合真实 Worker 代码判断，不能把过期描述或模型配置当成 Worker 在线。

分类独立于前端实施状态：A现有后端直接支持；B前端适配/组合现有API；C必须新增后端能力；D当前不建议开发。A不等于页面已接或服务已在线。以下路径省略`/api/v1`；E/T/R/C为项目/任务/运行/Case ID，W为Work ID。

数据性质：**原始**=数据库/Manifest事实；**派生**=程序聚合/多API组合；**Agent持久**=已写report/trace/消息；**Agent临时**=模型循环里未提交的文本/工具上下文，HTTP不提供；**前端临时**=草稿/选择/折叠/提示，不冒充业务记录。服务端读取不代表正文可下载。

## 代码与测试证据索引

下表路径为映射行的共同证据；每行模块另注明具体字段与接口，避免重复长路径。

| 代号 | 实际模型、Schema、Router、Service/Queries与执行入口 | 测试/迁移依据 |
| --- | --- | --- |
| BIZ | [models](../../backend/src/onefde/modules/business/models.py)、[schemas](../../backend/src/onefde/modules/business/schemas.py)、[router](../../backend/src/onefde/modules/business/router.py)、[service](../../backend/src/onefde/modules/business/service.py)、[operations](../../backend/src/onefde/modules/business/operations.py)、[leads](../../backend/src/onefde/modules/business/leads.py) | [test_business](../../backend/tests/integration/test_business.py)：公开隔离、澄清过期、交接、pending输入、复试与候选意愿；迁移[f3afd](../../backend/migrations/versions/f3afd81339dd_business_conversations_and_candidates.py) |
| BA | [Business EntryPoint](../../backend/src/onefde/entrypoints/business_agent.py)、[agent_state](../../backend/src/onefde/modules/business/agent_state.py)、[agent_tools](../../backend/src/onefde/modules/business/agent_tools.py) | [test_business_agent](../../backend/tests/integration/test_business_agent.py)：有效来源/版本、承诺、接管/新消息竞争、超时；[f2ee迁移](../../backend/migrations/versions/f2ee3d9000b1_business_agent.py) |
| FDE | [Engagement模型](../../backend/src/onefde/modules/engagements/models.py)/[Schema](../../backend/src/onefde/modules/engagements/schemas.py)、[Work模型](../../backend/src/onefde/modules/fde/agent_models.py)/[Schema](../../backend/src/onefde/modules/fde/agent_schemas.py)、[router](../../backend/src/onefde/modules/fde/router.py)、[delivery查询](../../backend/src/onefde/modules/fde/queries.py)、[HTTP工具](../../backend/src/onefde/modules/fde/tools.py) | [test_fde_tools](../../backend/tests/integration/test_fde_tools.py)：建Task/采用/聚合/跨项目拒绝；[ce99迁移](../../backend/migrations/versions/ce99d539d71a_fde_agent.py) |
| FA | [FDE EntryPoint](../../backend/src/onefde/entrypoints/fde_agent.py)、[agent_work](../../backend/src/onefde/modules/fde/agent_work.py)、[agent_tools](../../backend/src/onefde/modules/fde/agent_tools.py)、[ChatModel](../../backend/src/onefde/infrastructure/runtime/fde_chat.py) | [test_fde_agent](../../backend/tests/integration/test_fde_agent.py)：普通Work、重启/重放、建议非评审、usage、到期/新消息派发守卫；[test_fde_chat](../../backend/tests/unit/test_fde_chat.py) |
| ENG | [models](../../backend/src/onefde/modules/tasks/models.py)、[schemas](../../backend/src/onefde/modules/tasks/schemas.py)、[router](../../backend/src/onefde/modules/tasks/router.py)、[queries](../../backend/src/onefde/modules/tasks/queries.py)、[commands](../../backend/src/onefde/modules/tasks/commands/runs.py)、[inputs](../../backend/src/onefde/modules/tasks/commands/inputs.py)、[reviews](../../backend/src/onefde/modules/tasks/commands/reviews.py) | [test_task_lifecycle](../../backend/tests/integration/test_task_lifecycle.py)：三轮/冻结快照/版本/停止/失联/迟到/评审/分页；[test_task_boundaries](../../backend/tests/integration/test_task_boundaries.py)；[4bf迁移](../../backend/migrations/versions/4bf8db3c4ef3_c1b_task_inputs_versions_runs_reviews_.py) |
| RUN | [Worker入口](../../backend/src/onefde/entrypoints/worker.py)、[controller](../../backend/src/onefde/worker/controller.py)、[dispatch](../../backend/src/onefde/modules/tasks/dispatch.py)、[Runtime](../../backend/src/onefde/infrastructure/runtime/engineering.py)、[OpenHands适配](../../backend/src/onefde/infrastructure/runtime/openhands.py) | [test_worker](../../backend/tests/integration/test_worker.py)、[test_engineering_run](../../backend/tests/integration/test_engineering_run.py)、[test_engineering_contract](../../backend/tests/unit/test_engineering_contract.py)；[d545迁移](../../backend/migrations/versions/d5454eda0523_c2_worker_claim_lease_and_durable_.py) |
| KNOW | [catalog](../../backend/src/onefde/modules/knowledge/catalog.py)、[access](../../backend/src/onefde/modules/knowledge/access.py)、[tools](../../backend/src/onefde/modules/knowledge/tools.py)、[schemas](../../backend/src/onefde/modules/knowledge/schemas.py)、[router](../../backend/src/onefde/modules/knowledge/router.py)、[Manifest样例](../../capability-library/fresh-quote-compare-csv/manifest.json) | [test_knowledge_tools](../../backend/tests/integration/test_knowledge_tools.py)：三角色/公开摘要/受限404/文件交接；[能力库约定](../../capability-library/README.md)；当前无能力库版本数据库迁移 |

迁移链：d3a→4bf→d545→f3afd→71e→b91→ce99→f2ee。71e为售后受控试点，b91允许无模型固定归档复用验证；它们不是通用聊天/发布/资产版本管理表。TaskVersion有不可变规格历史；Work.report/trace是当前累积/更新字段；Manifest当前文件不能推断完整历史。

## 映射的共同权限与状态约定

每个模块均应用本段，再叠加表中条件。**I**：创始人Cookie内部读，写另需CSRF/可信Origin/JSON；有Key参数的路由带Idempotency-Key，不能假设邀请/预览也受同种幂等包装。**P**：客户本Case Bearer，写限制产品Origin，不混用员工Cookie。**K**：I下Knowledge查询为POST，仍需写会话/CSRF/Key；caller_role/purpose由当前可信单创始人显式传入，并非多用户RBAC。**O**：Task所有者命令由创始人代行/FDE受控工具执行，Engineering不自验收。

**S**：区域加载；无对象/无结果明确下一步；失败保留旧数据标过期并可重读；写中防重复保草稿；等待解释实际等待对象；成功仅按持久回执命名；401清私有状态回登录、403不可越权、404不暴露存在性、409重读后核对、422字段纠正。无业务updated_at时只显示客户端最近读取时间。每行“状态”补充S以外的领域含义。

更新频率为设计目标，非当前全部已实现：活动Task/Run可见时2秒、waiting_input/review约10秒、interrupted约10秒仅核查；Case详情可见时约5—10秒或手动、Work有pending/processing约4秒。终态停定时、写后定向失效；后台停止、重连/返回重读。没有SSE/完整工具流承诺。分页补全规则见[架构](architecture.md#四工作区状态与更新补充2026-11-08)。

## Business模块映射

| 模块/展示内容 | 业务意义 | 模型/字段与性质 | 真实API | 生成机制 | 持久化/刷新恢复 | 更新机制 | 点击操作/真实写接口 | 权限 | 状态（另加S） | 分级/缺口 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B1 Case收件箱：工作流、状态、处理人、下一步、创建时间 | 找待跟进会话，不冒充客户档案 | BIZ CaseSummary.workflow/state/owner/handler/next_step/created_at，原始 | GET /business/cases?cursor=&limit= | 规则/人工/Agent动作写Case，DB读 | DB可恢复；筛选入URL | 首屏/翻页/写后/手动；当前无定时 | 打开Case GET详情；本页筛选纯前端 | I | 无匹配≠全库无Case；失败≠待命 | A列表/B过滤与反馈；全库筛选C1 |
| B2 客户会话与内部备注：正文、作者、时间、来源引用 | 保留原话与公开/内部边界 | Message.kind/author/text/reference/created_at；原始+Agent持久 | GET /business/cases/C?after=，has_more/last_message_id | 客户输入/规则/Agent/员工追加Message | DB恢复；未发草稿前端临时 | 按after补页；写后/手动，建议可见轮询 | POST /business/cases/C/actions：reply/note；take_over先接管 | I；reply须handling且handler=当前人；closed禁写 | 等客户补答；发送回执与草稿分开 | A/B；当前详情已补消息分页，无需新聊天API |
| B3 Case依据栏：交接事实/未知项/版本/项目Task | 确认归属与依据，避免重复资料卡 | CaseDetail.handoff（含fact/consent/reproduction消息引用）、reported_version、engagement_id/task_id/invitation_id；原始 | GET Case详情；必要时GET /tasks/T及项目 | handoff动作/受控Agent记录，客户原文引用 | JSONB/外键恢复；展示是派生组合 | Case写后；Task变更定向重读 | POST actions handoff；accept_handoff带E+task_id或spec；到FDE可POST /engagements/E/fde/work {case_id} | I；具体需求/意愿/售后版本/项目归属守卫 | 未交接/版本待核实明确；已绑不改绑别项目 | A数据/B按对象选取，减少手输UUID；AgentGrant状态不可从此推断 |
| B4 澄清预览：公开正文与内部摘要 | 发送前核对，防旧消息误发 | ClarificationDraft.source_message_id/last_public_message_id/public_reply/internal_summary；程序派生 | POST /business/cases/C/clarification-draft | 模板+员工understanding/question；非模型、非自动发送 | **预览不落库**，刷新丢；发送后Message恢复 | 原public水位变化作废，重新预览 | POST actions send_clarification，绑定source及expected_last_public_message_id | I，接手本Case的FDE | 预览/过期/发送中/已发送分开 | A/B，无持久草稿库 |
| B5 FDE反馈核准 | 让获准反馈回原会话 | Work.report.summary/error/state + Case当前Task/水位；核准后Message.note.reference | GET /engagements/E/fde/work + Case详情 | Agent报告持久，人工批准写note，Business消费者转达 | note持久；未批准编辑临时 | Work/Case变更重读 | POST actions approve_fde_feedback {fde_work_id,text,expected_last_public_message_id} | I；非support、有效模拟grant、当前handling/归属/handler等校验 | 已核准待转达≠已向客户发；以reply回读确认 | B；不是通用自动客户反馈功能 |
| B6 售后复试：修复版本、入口、步骤、客户结果 | 工程接受和客户可用分开 | Case.retest中的artifact_id/version/access_url/steps/access_evidence/run_id/spec_version/review_id/sha256/notice_id/passed；原始 | GET Case详情；GET Task/reviews/artifacts供选择 | 人工记录访问证据；服务端核对accepted_artifact；客户反馈 | JSONB+公开通知/结果Message恢复 | 关联接受后重读；待复试读Case | POST actions notify_retest；**客户**POST /public/business/conversations/C/retest | I发通知；P提交结果；FDE handler/版本/Task守卫 | 等客户；通过closed，失败fde_queue，不能旧artifact重复通知 | A/B；访问证据是人工登记，不自动探测部署 |
| B7 区县候选列表：来源、名称、地址、推荐原因、查询时间 | 主动找店有来源且不虚构经营判断 | Candidate.source/adcode/poi_id/name/address/reason/queried_at；原始 | POST /business/candidate-search；GET /business/candidates?adcode= | 高德POI或明确sample，搜索即DB保存 | DB持久，URL需保留adcode方易恢复；当前结果内存 | 显式搜索/读已保存；不定时调用外部搜索 | POST搜索{adcode,sample}；无独立保存接口 | I；无Key配置真实搜索失败，不回退sample | 未搜索/无结果/外部错误/模拟徽章 | A/B；读取仅最近50，无翻页；重复不同搜索可有重复POI，合并去重需C1 |
| B8 邀请登记与分享链接 | 选择候选并追溯后续Case来源 | Candidate.invited_at/invited_by、Case.invitation_id；原始+URL派生 | POST /business/candidates/ID/invite；GET候选 | 程序登记；前端用productUrl+#invite组链接 | 登记DB恢复，链接重算；不保存外发回执 | 操作回读 | invite {}；复制链接无后端写 | I；客户由P发起会话 | 已生成≠已发送/触达 | A/B；外部消息渠道D，不假设营销自动化 |

BA授权事实：AgentGrant含profile_id/expires_at/policy/progress/lease。`agent_state.active/enroll`仅隔离`_test`库、指定模拟Case/项目等条件；EntryPoint工具循环可读本会话、匹配FAQ版本、查公开知识、发送获准原文、澄清/升级/交接；接管/新消息使旧轮次失效。没有grant状态HTTP投影，也无创始人通用目标会话。Case页handler只可显示“服务接手”，不能承诺“Agent正健康运行”。

## FDE模块映射

| 模块/展示内容 | 业务意义 | 模型/字段与性质 | 真实API | 生成机制 | 持久化/刷新恢复 | 更新机制 | 点击操作/真实写接口 | 权限 | 状态（另加S） | 分级/缺口 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F1 项目目标/来源/模拟标记 | 保持本次交付上下文 | Engagement.id/title/goal/is_demo/created_at；Case.handoff；原始。sources_note为程序通用文案 | GET /engagements/E；GET /engagements/E/delivery；GET原Case | 用户建项目；Case来源记录；聚合读DB | DB恢复；无Engagement.context和独立方案文档 | 进入/切项目/写后 | 导航项目/Case；项目创建POST /engagements，非本页重设计 | I，校验Case归属 | 无项目选项目；sources_note不是已验来源清单 | A基础/B组合；独立项目事实维护C3 |
| F2 Work选择与目标登记 | 清楚追踪每项FDE目标 | AgentWork.id/goal/case_id/task_id；WorkView.state为水位/有效租约派生 | GET/POST /engagements/E/fde/work | 用户goal或批准handoff→DB；消费者处理 | Work持久；草稿临时；GET只最近50，无单W读取/游标 | 活动4秒；reported也在外部输入/返回时重读，不能永久停止发现 | POST {goal,case_id}，202登记，不直接执行；按W选择前端状态 | I；项目/Case/Task范围守卫；grant不在此授予 | pending等待消费者；processing租约；reported可含error，非完成 | A/B；超50/按W深链接C2 |
| F3 报告/澄清/评审建议 | 区分建议、错误和正式接受 | Work.report.summary/error/clarification/review_suggestion；Agent持久；无历史版本 | GET Work列表 | EntryPoint/agent_tools写当前report，可再次覆盖/合并 | DB当前报告恢复；未持久模型输出不展示 | Work重新pending/processing和返回时重读 | 去Case核准/预览；去Engineering正式评审POST /tasks/T/reviews | I/O；suggest_review只是建议；HTTP propose_review确为正式写 | 有error突出；无摘要不写成功；不同版本建议标陈旧 | A数据/B语义；持久聊天/报告版本D |
| F4 项目规则/待处理问题 | 让范围与未知有执行版本 | Task.spec.confirmed_rules/inputs/scope/completion_criteria；Case.handoff.confirmed_facts/unknowns；delivery.unknowns是pending question/clarification文本聚合 | GET delivery；按需GET Task、/inputs、原Case | 用户/Agent建议先保存输入，再所有者采用；聚合程序读DB | 规则/输入持久；组合视图可重建 | revision/输入变化/写后 | POST /tasks/T/inputs、/apply-inputs或FDE tools save_input/adopt_inputs | I/O；无active才采用，变更需完整spec | 空unknowns≠所有规则已确认；pending不能当执行规则 | B；项目级独立决策/未知项台账C3 |
| F5 Task索引与交付摘要 | 从组织工作走到工程对象 | DeliveryTaskSummary.id/title/objective/scope/state/pending_input_count/latest_run_id/revision/spec_version；scheme_summary=首Task objective；latest_checks=Run.result_summary；fixed_version_hint为提示 | GET delivery；按需GET Task/Run/证据 | 后端Queries聚合，非Agent方案版本 | 底层DB恢复；聚合无独立存储 | 写后/可见刷新；不合成项目完成率 | 跳Engineering；建Task可POST /engagements/E/tasks或fde/tools create_task | I/O；角色固定fde/engineering | 多Task各自状态；有succeeded≠项目交付，hint≠部署入口 | A聚合/B准确命名与跳转；完整交付登记C6 |
| F6 工具回执/调用量/usage（折叠） | 解释做过什么，辅助核查 | Work.trace/calls/usage，Agent持久；trace最多保留约120条，schema为宽字典 | GET Work列表 | EntryPoint.fact脱敏回执；模型usage及收费/预留计数 | DB当前累积恢复；非完整工具日志/账单 | 随Work刷新 | 展开/复制受控引用，无新写接口 | I；不展示原prompt/secret | 无usage写未记录；预留费用不叫实际账单 | A/B，完整Trace时间树/日志C5或D |

FA能力：真实ChatModel工具循环，不是仅静态工具；模型上下文由业务记录和recent receipts重建。Agent工具清单含read_project/read_conversation/search_knowledge/get_knowledge/consult_knowledge/draft_clarification/send_clarification/create_task/read_task/record_customer_input/adopt_inputs/delegate_engineering/read_run/suggest_review。普通Work与受信grant授权不同：自动发送/派发须grant；adopt_inputs本身不要求grant，但核对Case归属、Task状态draft/waiting_input、revision及既有采用守卫，有grant时附登记检查。EntryPoint须实际运行才消费pending。`WorkView`没有created_at/updated_at、消费者健康、租约到期原因，不能用浏览器等待秒数推断失败。

## Engineering模块映射

| 模块/展示内容 | 业务意义 | 模型/字段与性质 | 真实API | 生成机制 | 持久化/刷新恢复 | 更新机制 | 点击操作/真实写接口 | 权限 | 状态（另加S） | 分级/缺口 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E1 当前Task与规格 | 知道被授权做什么 | Task.id/state/revision/spec_version/owner_role/executor_role/related_task_id/block_reason/spec全部字段；原始 | GET /tasks/T；项目Task列表或delivery | 用户/FDE建spec，所有者采用/更新；角色固定 | DB+TaskVersion恢复；original_request在ORM有、Task响应无 | 当前2秒/待答评审10秒/写后 | PATCH /tasks/T更新spec；或FDE入口建任务；一般补充优先TaskInput | I/O；closed禁写，revision守卫 | draft/等待/阻塞理由；不把运行状态代任务状态 | A/B；显示原请求全文若需新增HTTP投影C3 |
| E2 输入ledger：原问题/答复/采用状态与理由 | 防“发送即已执行”，保持问题闭环 | TaskInput.kind/text/sequence/status/reply_to_input_id/origin_run_id/author/created_at/applied_spec_version/processed_by/processing_reason/processed_at/resolved_by_input_id/evidence_artifact_ids；原始 | GET /tasks/T/inputs?after_sequence=&limit= | 用户/工程结构化问题追加；所有者处理 | DB恢复；草稿临时，按Task/版本隔离 | 独立输入水位补页；写后/待答刷新 | POST /inputs；POST /apply-inputs {apply_ids,reject_ids,reason,spec?} | I/O；无active可处理；answer绑定同Task原题 | pending/applied/rejected文字；可多问题，不能默认全采用 | A能力/B当前缺挂载，优先恢复；无新API |
| E3 当前Run状态/等待/错误/模型修订 | 判断执行还是等待，允许真实命令 | Run.id/task_id/task_spec_version/attempt/state/outcome/result_summary/error_code/model_profile_revision_id/applied_input_ids/created_at；Task.active_run_id；原始 | GET /runs/R；GET /model-profiles（数组） | owner actions登记Run/dispatch_jobs，Worker认领/回填 | DB恢复；选择Run入URL | 活动2秒、interrupted降频，终态重取相关证据 | POST /tasks/T/actions queue/start/continue/retry/stop_for_update/cancel，expected_revision/run_id | I/O；start类需profile，全局唯一活动槽，unknown现场不重启 | queued待派发、cancel_requested待停、interrupted现场不明 | A/B；Worker健康/排队原因HTTP C4 |
| E4 运行活动摘要与任务变更 | 有序查看实际记录 | RunEvent.sequence/kind/summary/created_at；TaskEvent同类独立sequence，原始 | GET /runs/R/events；GET /tasks/T/events，after_sequence | Task事务/Worker受控事件；SDK callback不是全量实时转发 | DB恢复；不是终端/完整Tool日志 | 分别补页/水位去重；没有事件写“暂无新增” | 查看/重读，无浏览器回填Run结果接口 | I | 加载/追平/过期/无新增；不展示假的typing | A事件/B补页与来源；真正实时工具级事件C5 |
| E5 固定评审证据：设计说明/检查/Diff/限制 | 基于同一归档评审，而非模型自称成功 | RunReviewEvidence.artifact_id/artifact_sha256/baseline_sha256/mode/design/diff/diff_truncated/self_checks/validation_checks/validation_passed/assembly_revision/baseline_origin/known_differences等；派生 | GET /runs/R/review-evidence | Runtime固定源码与登记检查→DispatchJob.result_payload.proof；Queries校验归档/版本后投影 | 私有固定blob+DB proof，重读可恢复；旧Run可能null | 首次终态/Run变化/手动；null缓存终态后失效 | 展开检查命令/exit_code/timeout/Diff，无源文件GET | I，completed/submitted及归档关联守卫 | null缺证、空Diff无差异、truncated不完整；null检查未验证 | A/B；Diff不是源码，现有code视图需纠正 |
| E6 固定产物元数据 | 追溯提交身份/完整性 | Artifact.id/engagement_id/run_id/name/kind/sha256/size_bytes；原始；object_key不向客户端暴露 | GET /runs/R/artifacts?cursor= | Worker固定/校验blob，程序登记元数据 | DB元数据恢复，不保证字节可HTTP获取 | 终态/写后/翻页 | 选择评审artifact_ids；复制摘要，无下载接口 | I，项目/Run匹配 | 无产物/缺证各自提示；不生成失效下载链接 | A/B；下载C7（YAML规划） |
| E7 历史Run与规格版本 | 不覆盖失败，按当时规格读证据 | Run.task_spec_version、TaskVersion.spec/applied_input_ids/actor/reason/created_at；原始 | GET /tasks/T/runs?cursor=；GET /tasks/T/versions；GET /tasks/T/versions/V；GET /runs/R | 每轮新Run，每次采用规格存版本 | DB恢复，显式R锁定历史 | 首次/翻页/新Run提示；历史停止轮询 | 选择历史只读，返回当前；无重开历史写入口 | I，先核对Run.task_id及Task.engagement_id | 旧Run不在前50不能当404；新Run不抢选择 | A/B；当前无可见历史选择器与完整分页，非后端缺口 |
| E8 正式评审与评审历史 | 工程提交到业务接受有证据 | TaskReview.run_id/task_spec_version/artifact_ids/verdict/reason/check_evidence/reviewer/created_at；原始 | GET/POST /tasks/T/reviews | 负责人命令，TaskReview与状态/修改输入同事务 | 不可变历史DB恢复；表单临时 | 写后失效Task/Run/inputs/delivery/reviews/证据 | accept/request_changes；带revision/Run/spec/产物 | I/O；当前latest submitted且版本匹配；accept无pending | 待评审/提交中/冲突/已接受；缺证突出但不新增硬门槛 | A/B；当前canReview给两种verdict同套pending限制，比后端request_changes更窄 |

RUN边界：dispatch_jobs是持久作业/租约，Worker短事务认领并在事务外调用SDK；资源和停止证明核查后回填。失败、取消、interrupted区分；interrupted保留active_run_id/全局槽。指定模拟授权下还有持久自动续办分支，可能在前Run失败后登记后续Run；UI应发现新的latest_run_id，不能把它当原Run复活或所有任务默认自动重试。自测与固定复验是两类证据，TaskReview是第三类业务判断。模型tool call、SDK session、私有源码归档存在，不意味着浏览器已有文件树/终端/工具流/自动部署API。

## Knowledge模块映射

| 模块/展示内容 | 业务意义 | 模型/字段与性质 | 真实API | 生成机制 | 持久化/刷新恢复 | 更新机制 | 点击操作/真实写接口 | 权限 | 状态（另加S） | 分级/缺口 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| K1 来源角色/用途/原工作与关键词 | 让检索为当前工作服务 | KnowledgeToolCall.caller_role/purpose/arguments.query；URL from/project/task/case，前端状态 | POST /knowledge/tools tool=search_assets | 用户输入/来源页面带入；后端校验枚举并投影 | URL可恢复query/用途；无独立查询历史；idempotency非知识会话 | 提交/用途变化/返回重读；无轮询 | 检索；切用途清缓存和临时气泡；返回站内合法来源 | K；工作ID当前未作为服务端知识范围过滤参数 | 未输入/检索中/失败/无可见结果；不叫Agent思考 | A查询/B导航；真实工作范围授权C8 |
| K2 检索结果：名称/版本/验证状态/获准来源与复用范围 | 快速选候选而不虚构语义相关分 | Manifest.id/name/version/type/verification_status/visibility/reuse_scope/source_engagement/implementation_ref/keywords；public仅摘要投影；原始→投影 | 同POST search_assets，result.items/count/query/purpose | tools._match对id/name/problem/keywords大小写归一、空格分词全部包含；无embedding/相关度分数 | Manifest文件持久，结果可重算；lru_cache进程内缓存 | 显式检索/刷新；改文件需进程重载/clear_cache，无自动索引事件 | 选中后POST get_asset | K；restricted不列；public_marketing仅public_summary字段集合 | count仅本次可见命中；无结果不区分受限资产存在性 | A/B；语义RAG/全库统计D |
| K3 资产详情：问题/条件/限制/输入输出/来源/验证 | 决定能否在本项目使用 | Manifest.updated_at/problem/applicable_when/not_applicable_when/inputs/outputs/evidence/verified_samples/implementation_ref/implementation_archive_sha256/verification_status/reuse_scope等；原始投影 | POST /knowledge/tools tool=get_asset {asset_id} | 读取当前Manifest，服务端access过滤 | 文件恢复；只按ID取当前版本，无version选择HTTP | 选中/用途变化重读；不从旧结果补内部字段 | 展开证据引用/条件；不是源码/文件下载 | K；内部两用途同字段集；公开详情仍仅摘要 | 404=不存在或不可见；缺元数据写未记录，验证仅列样例范围 | A/B；版本历史可读C9，资产写入/审核C9 |
| K4 复制版本引用/返回 | 将知识支持带回原工作 | id@version，from+合法ID派生；不是采用事实 | 无新API，读取K3已获准投影 | 前端字符串与clipboard | 引用本身只有手动粘回原对象才持久；copied提示临时 | 点击后反馈，返回保留具体选择 | clipboard；回Task由POST inputs/apply-inputs或规格保存capability_versions | K/O；公开摘要不得携内部实现 | 已复制≠已采用；无历史版本读取保证 | B；自动采用/咨询留存C8/C9，当前不做隐式写 |

角色/用途实情：access.can_list/project_for_get主要按visibility+purpose过滤；search/get没有caller_role差异化过滤。`record_business_handoff`只允许business、写受控目录文件，不派工程，也不是Case状态交接，更不是资产入库。`consult_delivery`是读取最多候选并给条件比较的确定性服务，无独立Knowledge模型循环。Manifest有version字段不代表版本不可变存储或历史管理已实现。

## 当前前端实际情况

入口[App.tsx](../../frontend/src/App.tsx)使用features页面；[Business.tsx](../../frontend/src/Business.tsx)及旧[FdeWork.tsx](../../frontend/src/FdeWork.tsx)不能代替当前路由检查。[types.ts](../../frontend/src/api/types.ts)为手写类型，非已接生成流水线；[client](../../frontend/src/api/client.ts)已有Cookie/CSRF/requestId/details；[keys](../../frontend/src/api/keys.ts)共享对象与Knowledge角色用途key；[write](../../frontend/src/api/write.ts)有幂等和失效工具。Query默认retry=false、refetchOnWindowFocus=false，返回即刷新需显式落实。

| 页面 | 当前真实已接 | 尚未实现/路由不可达 | 错误或容易误解的表达（修正建议） |
| --- | --- | --- | --- |
| [BusinessPages](../../frontend/src/features/business/BusinessPages.tsx) | Case分页/当前页过滤；详情补齐消息；reply/note/接管/交接/澄清/复试；找店/已存候选/邀请；原对象链接 | 通用Business目标聊天无API；Case无轮询；区县/候选选择刷新恢复不完整；grant状态不可查 | 禁用聊天占首页；focusItems仅过滤页仍说当前N个未关闭；handler以service前缀称自动化处理中但不证明健康；操作统一“保存”不区分核准/发送；部分表单手输UUID |
| [FdePage](../../frontend/src/features/fde/FdePage.tsx)/[FdeWorkPanel](../../frontend/src/features/fde/FdeWorkPanel.tsx) | delivery+Work列表/登记/报告/错误/建议；活动4秒、delivery8秒；Task深链 | 无持久聊天/方案文档/版本；calls/usage未呈现；只最近50Work，W未命中回退全列表；FDE无所有者输入处理UI | “发送/与FDE对话”实际新Work；首Task目标在当前需求与方案；空unknowns说没有未知项；报告左右重复；已报告后外部唤醒不保证及时发现；每次fetch滚到底 |
| [EngineeringPage](../../frontend/src/features/engineering/EngineeringPage.tsx) | 当前Task/Run；2秒活动读；RunEvent前100；固定证据；actions及正式评审；run URL有限历史只读 | **InputPanel未挂载**，当前路由只有EngineerChat追加输入，无法采用/拒绝；TaskVersion/TaskEvent未接；runs仅前50且无可见历史选择器；artifacts/reviews分页未补齐；后台终态相关缓存刷新不足 | [CodeWorkspace](../../frontend/src/features/engineering/CodeWorkspace.tsx)把Diff删掉删除行称代码，把RunEvent称执行日志，目录仅是Diff路径分组；[EngineerChat](../../frontend/src/features/engineering/EngineerChat.tsx)把全部输入/事件归成两方发言且不显示采用状态，历史套当前spec，默认答首个pending问题；succeeded/cancelled未显式禁composer |
| [KnowledgePage](../../frontend/src/features/knowledge/KnowledgePage.tsx) | 角色用途key；search/get；公开摘要；详情来源/条件/证据；复制版本；部分返回上下文 | 无语义RAG、持久咨询/采用历史、资产写入/历史版本；输入输出与updated_at/归档摘要可接但未展示完整 | 搜索用“发送”且气泡是内存程序提示；切角色用途清Query但未清lines，旧内部名称可能留在公开用途聊天；schema异常asSearch回落空结果会掩盖契约错误；returnPath丢Run/Work |

Engineering里[InputPanel](../../frontend/src/features/engineering/InputPanel.tsx)、[EvidencePanel](../../frontend/src/features/engineering/EvidencePanel.tsx)虽存在，不能算当前主路由已具备。旧F1/F2/F3“完成”是历史时点记录，本次发现为当前审计差异，不抹去历史验证。独立engineering-preview仍为模拟，不用它证明真实闭环。

## 后端能力缺口与优先级（2026-11-08）

优先级为设计建议，不构成新增API/表授权。**首轮A/B整改没有必须新增后端的前置项**；以下C仅在对应增强被确认后必需。

| 编号/级别 | 必须新增能力的触发条件 | 当前不足与建议最小边界 | 优先级/验收条件 |
| --- | --- | --- | --- |
| C1 | 要全量Case筛选/搜索，或长期管理候选 | Case Router仅分页无过滤，Candidate最近50且不同搜索可重复；增加服务端过滤/可追溯分页与候选去重语义 | P1；跨页过滤不漏，候选重复/来源时间保留，需确认去重规则 |
| C2 | 要稳定Work深链接/完整历史 | GET最近50，无按ID/游标/业务更新时间；增加范围受控单Work读取/分页和必要时间投影 | P1；第51条可定位、跨项目拒绝、错误可见；无“永久聊天”扩张 |
| C3 | 要独立项目事实/未知项/方案维护或原请求展示 | Engagement无context/确认记录，Task响应不含original_request；先确认粒度/来源/所有者，再做最小读写 | P2；事实/建议/未知与来源分离，版本采用可追溯；不盲建文档版本系统 |
| C4 | 要显示Agent授权有效性/消费者健康/等待原因 | grant和租约在DB但不暴露，pending不能区别未启动/失权/等待；设计脱敏能力/原因投影 | P1（正式自动化前）；已过期/未消费不显示运行，不能回显配置密钥或提供无限扩权 |
| C5 | 要实时工具活动 | 当前RunEvent与Work.trace非完整及时工具流；先持久脱敏事件、来源/时间/状态/保留策略，再订阅 | P2；游标补读/断线去重/权限撤回/停止终态；仅SSE前端不算实现 |
| C6 | 要正式交付记录/自动访问校验 | fixed_version_hint非部署，Case.retest只含指定售后人工登记；需要固定版本、环境/URL、访问检查与发布授权 | P2，按P08；实际访问及发布回执，不以Task接受替代 |
| C7 | 要下载固定产物 | download-url仅YAML planned；字节获取、权限/摘要/保留/过期控制未公开 | P2；认证访问同一固定字节，过期/清理明确；不提供宿主路径 |
| C8 | 要真实资料的角色×工作范围×用途授权/咨询审计 | 当前可信单创始人传角色，access无项目ACL，URL ID不参与过滤；需可信身份和工作归属绑定、来源授权/撤回 | P0条件门槛：多用户/真实受限资料前；改role/用途/工作不可扩大可见，不泄漏派生结果；单演示A/B不因此阻塞 |
| C9 | 要资产历史版本/维护/自动留存采用 | 当前每ID一份Manifest，查询不记业务采用；需不可变版本读取/来源权限、候选维护与状态提升证据 | P2；历史引用可读、撤权仍过滤、采用回原对象，模型不自验 |
| D | 通用Business创始人Agent、完整CRM/漏斗、通用方案/文档聊天、IDE文件树/终端、任意源码浏览、自动部署、语义RAG/图谱/全库假统计 | 当前本轮目标不需要，缺数据/流程不补静态演示伪装 | 本轮不建议；有独立需求再评估 |

待确认规则和六组交接见[设计](design.md)，按风险分期见[实施](implementation.md#四工作区重新对齐2026-11-08)。

## 历史映射（2026-11-07）

保留当时记录；计数、入口、能力和前端状态以以上当前审计为准。下表G编号为历史候选，不作为本轮C编号的别名。

核对日期：2026-11-07，依据当前工作树而非仅 Git HEAD。运行契约有 42 个 HTTP 操作，含 health/认证和客户公开接口；[已实现 JSON](../architecture/openapi.implemented.json)可用于生成类型，[合并 YAML](../architecture/openapi.yaml)包含规划项，须看 `x-onefde-status`。以下能力判断同时检查路由、Pydantic、服务、Worker 和测试；未在本轮执行模型/浏览器业务或重跑集成测试。

分类：**A 可直接接**＝现有接口已表达该行为，仍需 UI 实施；**B 适配**＝现有事实需组合、裁剪或小幅契约整理；**C 缺能力**＝须新增后端能力才可承诺；**D 后置**＝当前不建议开发。路径除 health 外省略 `/api/v1`，E/T/R 分别指 Engagement/Task/Run ID。新增 API 只列需求候选，本轮不定义生效契约。

## 现有前端和后端基线

- [App.tsx](../../frontend/src/App.tsx)已接登录、项目、URL 选 Task、最近 Run、固定评审证据/产物元数据/接受和修改；[Business](../../frontend/src/Business.tsx)接 Case/候选与原单操作，[FdeWork](../../frontend/src/FdeWork.tsx)接项目 Work。当前真实 UI 为绿系薄工作台，不是五图成品。
- [engineering-preview](../../frontend/src/engineering-preview/main.tsx)是独立模拟入口，内存操作不调用真实 Task API。普通 Vite 构建以 `index.html` 为入口；本轮不构建或变更入口。[api.ts](../../frontend/src/api.ts)已有 Cookie/CSRF/基础错误，尚需生成类型、错误 request_id 与领域查询封装。
- 当前 Task 固定 owner=fde/executor=engineering，非空 dependencies 明确拒绝；四角色共用业务事实，不宣称已有四类通用 Task 引擎。

## 五页功能分级

| 页面/功能 | 分类 | 实际能力及页面裁剪 |
| --- | --- | --- |
| Office 项目入口 | A | `GET /engagements`、`GET /engagements/{E}`，分页项目；无项目整体业务阶段字段 |
| Office 有限待办与摘要 | A/B | `GET /office/actionable`、`GET /office/activity`（coverage、read_at、深链）；办公室气泡文案由此派生。完整全局聚合仍见下行 C/G6 |
| Office 全局动态/完整待办/角色活动 | C | 没有统一聚合、水位、员工心跳或全局最近活动接口；`GET /health`只是API存活，model profile也不是在线状态 |
| Office 营收、效率、周趋势、通知已读、搜索 | D | 无统一事实源和当前业务需求；不展示模拟数字/角标 |
| Business 原 Case 跟进 | A | 员工 Case 列表/详情/动作、澄清草稿、候选搜索/读取/邀请、客户复试链；有实际客户消息与内部备注 |
| Business 专业工作台 | B | 按 state/owner/workflow做加载范围筛选；展示原消息水位、交接和关联 Task，使用现有动作守卫；列表暂无服务端筛选参数，不能把前端过滤叫全局过滤 |
| Business 客户/商机/计划实体 | C | 有 Case、Candidate、AgentGrant，没有独立 Customer/Opportunity/FollowUp 实体及 CRUD/漏斗口径；Case不能直接当客户档案 |
| Business 完整 CRM/自动外呼/创始人通用聊天 | D | 超出当前最小范围；Business Agent处理获准Case不等于可在员工页自由安排任何经营工作 |
| FDE 异步 Agent 工作与项目交付摘要 | A | `GET/POST /engagements/{E}/fde/work`、`GET .../delivery`、`POST .../fde/tools`；真实 ChatModel 循环和受控工具存在 |
| FDE 方案/问题工作区 | B | 用 Work goal/report/trace 与 Task spec/input拼装。`scheme_summary`取首 Task objective；`latest_checks`取 Run.result_summary，不能当独立方案或结构化检查 |
| FDE 创始人多轮对话/方案版本 | C | 无持久 Founder Message/Conversation API、方案修订/采用实体、通用附件接口；Work最多返回50条，无分页/时间字段，扩展历史需契约调整 |
| FDE 完整文档管理/估算排期 | D | 暂用 Task 范围/验收及受控报告，不从图中推导自动估算或正式项目阶段 |
| Engineering Task/Run/输入/评审 | A | 读写路由见下表；已支持同 Task 多轮、命令、固定提交和正式业务接受 |
| Engineering Diff/检查/产物视图 | B | 固定 review-evidence和Artifact元数据可渲染；不是完整代码仓库/文件树，也不是每轮都存在证据 |
| Engineering 文件树/源码/下载/细粒度实时日志 | C | 无对应浏览器接口。SDK能读写文件不代表平台已安全开放文件服务；RunEvent不是完整SDK事件流 |
| Engineering Web IDE/交互终端/逐行接受/自动部署 | D | 首发只读证据与任务闭环；无需 Monaco、终端Socket或浏览器直连Sandbox |
| Knowledge 搜索与资产详情 | A | `POST /knowledge/tools` 的 `search_assets` / `get_asset`；关键词匹配manifest，不是语义检索，无向量库/独立模型循环 |
| Knowledge 有用途的结果与引用 | B | 显示返回版本、适用限制、验证与来源投影；`public_marketing`只有公开摘要，不从别的缓存补齐私有字段 |
| Knowledge 历史版本/业务资料/候选维护 | C | 只有当前manifest版本，没历史列表/按版本读取；无通用受控业务资料检索、资产修改/接受API。内部consult_delivery是确定性比较，不是独立HTTP咨询聊天 |
| Knowledge 图谱/大规模统计/通用RAG/上传后台 | D | 当前不建议做；图中SOP/充电宝示例不是仓库业务资产 |

证据入口：[Business 路由/Schema](../../backend/src/onefde/modules/business/router.py)、[领域模型](../../backend/src/onefde/modules/business/models.py)、[FDE 路由](../../backend/src/onefde/modules/fde/router.py)、[Work](../../backend/src/onefde/modules/fde/agent_work.py)、[ChatModel](../../backend/src/onefde/infrastructure/runtime/fde_chat.py)、[交付聚合实现](../../backend/src/onefde/modules/fde/queries.py)、[Knowledge工具](../../backend/src/onefde/modules/knowledge/tools.py)/[权限投影](../../backend/src/onefde/modules/knowledge/access.py)。

## Engineering 真实接口清单

| 页面行为 | 已实现方法与路径 | 关键字段/约束 |
| --- | --- | --- |
| 项目与任务 | `GET /engagements`、`GET /engagements/{E}`；`GET/POST /engagements/{E}/tasks`；`GET /tasks/{T}` | 创建Task固定角色，完整TaskSpec含目标/范围/规则/输入/验收/能力版本；Task.revision是并发版本，spec_version是规格版本 |
| 规格查看/更新 | `PATCH /tasks/{T}`；`GET /tasks/{T}/versions`；`GET /tasks/{T}/versions/{spec_version}` | PATCH提交完整spec及expected_revision；无活动Run/待处理输入，更新回draft；历史规格不可覆盖 |
| Task输入流 | `GET/POST /tasks/{T}/inputs` | 写kind/text/evidence_artifact_ids/expected_revision；answer必须引用同Task的reply_to_input_id，非answer省略该字段；保存为pending，不热更新Run |
| 采用或拒绝 | `POST /tasks/{T}/apply-inputs` | apply_ids/reject_ids互斥、去重且至少一项，必填reason/revision；采用clarification/change_request须完整新spec，answer可沿用；采用回答同时解决原question，无活动/不明Run才可采用 |
| 运行列表/详情 | `GET /tasks/{T}/runs`、`GET /runs/{R}` | Run.task_id/task_spec_version/attempt/state/outcome/model_profile_revision_id/result_summary/error_code；没有公开workspace_path、完整snapshot/finish时间/预算余量字段 |
| 模型修订 | `GET /model-profiles` | revision_id、provider/model、integration_status；configured不等于真实冒烟通过，smoke_passed不等于当前Worker可执行；不读取/编辑secret |
| 命令 | `POST /tasks/{T}/actions` | command、expected_revision、expected_run_id，start/retry/continue还需model_profile_revision_id；queue/start的expected_run_id为null，retry/continue/stop_for_update须引用对应Run |
| 停止与取消 | 同actions，用`stop_for_update` / `cancel` | 前者只停本轮处理修改，后者取消Task；有活动Run需匹配ID，可能先cancel_requested；未认领可事务撤销，未知现场不可重试 |
| 有序事件 | `GET /tasks/{T}/events`、`GET /runs/{R}/events` | after_sequence/limit→items/last_sequence/has_more。RunEvent只有kind=`state/progress/check/artifact/error`、summary、created_at和ID/sequence，无完整stdout/工具参数/token |
| 固定提交证据 | `GET /runs/{R}/review-evidence` | 可为null；artifact_id/sha256/baseline_sha256/mode/design/diff/diff_truncated/self_checks/validation_checks/validation_passed，以及可空基线/装配修订等。Diff仅获准路径，不是全仓库 |
| 固定产物列表 | `GET /runs/{R}/artifacts` | id/engagement_id/run_id/name/kind/sha256/size_bytes；无URL、下载token或可用文件内容 |
| 正式业务评审 | `GET/POST /tasks/{T}/reviews` | 写expected_revision/run_id/task_spec_version/artifact_ids/verdict/reason/check_evidence；只评最新有效submitted Run及所属产物。accept要求非空check_evidence、无pending；request_changes追加pending变更输入并回draft |

普通列表用 `limit/cursor → items/next_cursor`，输入/事件用独立sequence。评审/动作成功后须读取新Task revision，不用旧响应继续串命令。查询/命令行为详见 [router](../../backend/src/onefde/modules/tasks/router.py)、[schemas](../../backend/src/onefde/modules/tasks/schemas.py)、[queries](../../backend/src/onefde/modules/tasks/queries.py)、[运行命令](../../backend/src/onefde/modules/tasks/commands/runs.py)、[评审命令](../../backend/src/onefde/modules/tasks/commands/reviews.py)。

### Worker、事件、固定证据的真实边界

[Worker](../../backend/src/onefde/worker/controller.py)短事务认领/心跳/停止/回填，[OpenHands适配](../../backend/src/onefde/infrastructure/runtime/openhands.py)运行SDK/文件与终端工具，私有blob保存受检归档。[工程证据构造](../../backend/src/onefde/infrastructure/runtime/engineering.py)只投影获准文本路径，单文件超过32KiB或非UTF-8可遗漏，Diff合并有截断标识。

SDK callback主要收集内存证据；[complete_claim](../../backend/src/onefde/modules/tasks/dispatch.py)在结束回填时登记部分检查诊断。运行期间可读派发/开始/停止状态，不保证每条工具活动已入run_events。把轮询间隔缩短或直接接SSE不能补造缺失事实。

review-evidence只在completed/submitted且找到匹配归档等校验通过时返回；老Run缺证据返回null。它不是任意Run的源码预览。accept服务并未强制检查validation_passed，当前结构化复验结果、模型总结、人工check_evidence应分开显示。自动修复/续办仅有特定模拟授权和恢复策略；HTTP无强制恢复interrupted入口。

[本地Engineering最新证据](../operations/testing.md#coding-agent细化验收)包括11月7日MiMo真实链路和所有者接受；不能据此声称Compose常驻Worker当前已开启执行、五页已联调或公网已交付。路由actions旧description仍写“未接Worker”，已与实际实现不符；以前述代码和验收事实为准，另列契约文案修正候选。

## Business、FDE 与 Knowledge 调用约束

Business：`GET /business/cases`分页，详情`GET /business/cases/{case_id}?after=…`补读消息，响应有last_message_id/has_more。消息区分customer/reply/note。`POST .../clarification-draft`只是预览；`POST .../actions`用discriminator action执行take_over、reply、note、send_clarification、handoff、accept_handoff、record_input、approve_fde_feedback、notify_retest。水位约束是特定动作字段，不是全Case通用revision。候选沿`POST /business/candidate-search`、`GET /business/candidates?adcode=…`、`POST /business/candidates/{candidate_id}/invite`；无高德凭据时可用明确sample，不能把样例当真实门店。邀请本身不等于已向外发送。

客户只在独立产品Origin用`/public/business/conversations/{case_id}`的PUT/GET/messages/retest和本单Bearer；与工作台Cookie不同。公开消息不包含note。自动Business模型入口在[entrypoint](../../backend/src/onefde/entrypoints/business_agent.py)，grant限定预登记Case/模拟范围/费用/租约；无创始人通用会话路由。

FDE：`POST /engagements/{E}/fde/work`传goal或已批准case_id，202返回WorkView；GET列表返回id/engagement_id/case_id/task_id/goal/state/report/trace/calls/usage。state为pending/processing/reported，由水位和租约计算，reported不是业务完成。真实循环见[fde_agent](../../backend/src/onefde/entrypoints/fde_agent.py)，普通工作可诊断/保存Task，自动发送/工程派发另受模拟grant约束。`POST .../fde/tools`八个工具复用Task命令，`propose_review`是建议，正式评审走reviews；不能做一排八工具按钮。

Knowledge：`POST /knowledge/tools`传tool/caller_role/purpose/arguments。search用query，get用asset_id，返回宽字典；可读当前manifest内容，正文文档/源码URL并未因此变成可浏览API。purpose为delivery/internal_research/public_marketing；restricted不列表/读取，公开用途仅public_summary投影。角色/用途来自当前受信创始人输入，未将真实多用户身份/项目ACL绑定到完整资料层。`record_business_handoff`只写有来源的经营交接文件，不是知识维护或工程派发；页面优先使用原Case交接，避免双份事实。

## 后端增量候选与优先级

下表是**建议新增能力**，不是已有API，也未授予本轮实施权限。首发Engineering闭环无需新增HTTP接口；“必须补”指若要承诺对应增强体验时必须补齐。

| 候选/阶段 | 最小契约需求与权限 | 验收与首版降级 |
| --- | --- | --- |
| G0 小整理，F1/F2 | 修正actions旧description；如要显示动作能力/Worker阻塞原因，可增加服务端能力投影，不能暴露内部主机/secret | 运行字段由Pydantic导出；无接口时用现有状态和真实错误，不显示Worker在线/启动必成功 |
| G1 固定文件浏览/下载，F2之后按需 | 按Run/Artifact ID读取固定归档manifest、受限文本文件、受控下载；校验身份/归属/摘要/留存和可用性，路径规范化、大小/类型限制；同源仅以附件或纯文本返回，不执行生成HTML | 跨项目、路径穿越、符号链接、超大/二进制、失效归档被拒绝；下载SHA匹配。首发仅Diff+产物元数据，浏览器不解包沙盒、不访问Worker路径/端口 |
| G2 工具级事件/日志，后置 | Worker在执行期间持久写脱敏、有限长、带顺序/时间/Run归属的活动；分页补读，内容权限/截断/保留；有需求再加SSE | 断线补读无漏重、取消后状态一致、不泄露凭据/客户正文；当前只显示已有摘要事件 |
| G3 FDE对话/方案版本，F3之后 | 若确需自由多轮，定义Work与持久消息关系、幂等/顺序/失败及预算；若确需正式方案，定义版本/建议/采用与Task规格关联 | 刷新可继续、旧输入不改变活动Run、建议不能自动确认；F3用现有异步Work不受此阻塞。Work分页/时间是可单独调整的小契约 |
| G4 Knowledge增强，F4之后 | 若承诺历史复用，需固定版本读取/不可见处理；若扩资料或多用户，先绑定实际身份/范围/用途再装配；候选维护需来源/修订/接受规则 | 撤权/公开投影/越项目无泄漏、历史固定引用可核对；F4只读当前资产可先做，不能用前端缓存冒充版本库 |
| G5 CRM，F5之后 | 只有确认客户经营需求后才增加Customer/Opportunity/FollowUp和状态/漏斗口径，与Case/项目关联 | 一个客户多Case不重复计商机、承诺由创始人确认；当前Case/候选首版不受阻塞，完整CRM保留设计空间 |
| G6 Office聚合，F6 | 全局受权限过滤的actionable items、最近业务动态、按角色归属的活动摘要；稳定对象引用/去重/分页/发生时间/读取时间及覆盖范围 | 无全项目N+1轮询、跳回同对象、状态与源对象一致；无心跳则不叫在线。F6完整全局页受此阻塞，前期仅有限摘要或角色入口 |

正式发布/预览管理、上传、通知、全局搜索和资产写入均后置。正式公网TLS、Caddy、发布/访问/回退依[部署设计](../operations/deployment.md)单独验收，前端规划不扩大部署授权。

## 验证依据与限制

本轮阅读而未重跑：[生命周期测试](../../backend/tests/integration/test_task_lifecycle.py)覆盖三轮/输入/采用/评审、幂等、停止、interrupted槽、并发和历史；[边界测试](../../backend/tests/integration/test_task_boundaries.py)覆盖回答/版本/跨项目；[FDE Agent测试](../../backend/tests/integration/test_fde_agent.py)覆盖工具结果、报告、过期授权和新消息；[Business测试](../../backend/tests/integration/test_business.py)/[Agent测试](../../backend/tests/integration/test_business_agent.py)覆盖原会话、接管、水位和复试；[Knowledge测试](../../backend/tests/integration/test_knowledge_tools.py)覆盖公开投影及受限404。测试存在与既有验收记录不是本轮实测通过声明。
