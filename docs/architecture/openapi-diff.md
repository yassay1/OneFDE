# OneFDE OpenAPI 检查

生成命令：`uv run --locked python -m scripts.export_openapi`。输入为运行时 Pydantic 与原始设计快照 `openapi.planned.yaml`。
运行契约：`openapi.implemented.json`；同路径 `openapi.yaml` 合并后续设计并用 x-onefde-status 标记，不能用它推断未来接口可调用。

## 字段与成功状态检查

- EngagementCreate: 无缺失字段；原必填字段均保留。新增字段：[]。
- Engagement: 无缺失字段；原必填字段均保留。新增字段：[]。
- TaskSpec: 无缺失字段；原必填字段均保留。新增字段：[]。
- TaskCreate: 无缺失字段；原必填字段均保留。新增字段：[]。
- Task: 无缺失字段；原必填字段均保留。新增字段：[]。
- OwnerSession: 无缺失字段；原必填字段均保留。新增字段：[]。
- ApiError: 无缺失字段；原必填字段均保留。新增字段：[]。
- TaskAction: 无缺失字段；原必填字段均保留。新增字段：[]。
- ActionAccepted: 无缺失字段；原必填字段均保留。新增字段：[]。
- Run: 无缺失字段；原必填字段均保留。新增字段：[]。
- TaskInputCreate: 无缺失字段；原必填字段均保留。新增字段：[]。
- TaskInput: 无缺失字段；原必填字段均保留。新增字段：['processed_at', 'processed_by', 'processing_reason', 'resolved_by_input_id']。
- TaskInputsApply: 无缺失字段；原必填字段均保留。新增字段：[]。
- TaskReviewCreate: 无缺失字段；原必填字段均保留。新增字段：[]。
- TaskReview: 无缺失字段；原必填字段均保留。新增字段：[]。
- TaskEvent: 无缺失字段；原必填字段均保留。新增字段：[]。
- RunEvent: 无缺失字段；原必填字段均保留。新增字段：[]。
- Artifact: 无缺失字段；原必填字段均保留。新增字段：[]。
- ModelProfile: 无缺失字段；原必填字段均保留。新增字段：[]。
- 新增已实现接口：GET `/api/v1/runs/{run_id}/review-evidence`，用于读取当前固定产物的受控评审证据。
- 新增已实现接口：GET `/api/v1/tasks/{task_id}/versions`，用于读取不可变版本快照。
- 新增已实现接口：GET `/api/v1/tasks/{task_id}/versions/{spec_version}`，用于读取不可变版本快照。
- 新增已实现接口：GET `/api/v1/engagements/{engagement_id}/fde/work-history`，用于完整分页读取当前项目FDE工作，保留既有列表兼容。
- 新增已实现接口：GET `/api/v1/engagements/{engagement_id}/fde/work/{work_id}`，用于按固定Work ID核对项目归属并读取工作。
- 新增已实现接口：GET `/api/v1/engagements/{engagement_id}/fde/work`，用于登记目标或获准交接，并读取 FDE 进展和建议。
- 新增已实现接口：POST `/api/v1/engagements/{engagement_id}/fde/work`，用于登记目标或获准交接，并读取 FDE 进展和建议。
- 新增已实现接口：GET `/api/v1/engagements/{engagement_id}/delivery`，用于P1最小项目交付详情。
- 新增已实现接口：POST `/api/v1/engagements/{engagement_id}/fde/tools`，用于P1薄FDE受控工具调用。
- 新增已实现接口：POST `/api/v1/knowledge/tools`，用于P3 Knowledge受控工具调用。
- 新增已实现接口：GET `/api/v1/office/actionable`，用于G6 Office 派生待办（非通知中心）。
- 新增已实现接口：GET `/api/v1/office/activity`，用于G6 Office 派生近期动态。
- 新增已实现接口：PUT `/api/v1/public/business/conversations/{case_id}`，用于客户创建或凭单据凭证重读。
- 新增已实现接口：GET `/api/v1/public/business/conversations/{case_id}`，用于客户创建或凭单据凭证重读。
- 新增已实现接口：POST `/api/v1/public/business/conversations/{case_id}/messages`，用于客户在原会话追加原话。
- 新增已实现接口：POST `/api/v1/public/business/conversations/{case_id}/retest`，用于客户确认当前修复的复试结果。
- 新增已实现接口：GET `/api/v1/business/cases`，用于工作台 Business 待办。
- 新增已实现接口：GET `/api/v1/business/cases/{case_id}`，用于工作台会话与关联详情。
- 新增已实现接口：POST `/api/v1/business/cases/{case_id}/clarification-draft`，用于预览带原话引用的 FDE 澄清草稿。
- 新增已实现接口：POST `/api/v1/business/cases/{case_id}/actions`，用于接管、交接、回复和复试通知。
- 新增已实现接口：POST `/api/v1/business/candidate-search`，用于经授权的区县候选搜索。
- 新增已实现接口：GET `/api/v1/business/candidates`，用于读取已保存的区县候选。
- 新增已实现接口：POST `/api/v1/business/candidates/{candidate_id}/invite`，用于创始人选店并生成演示邀请。
- 新增已实现接口：GET `/api/v1/business/cases/{case_id}/assistant`，用于读取和追加员工侧 Case 问答，不写客户消息。
- 新增已实现接口：POST `/api/v1/business/cases/{case_id}/assistant`，用于读取和追加员工侧 Case 问答，不写客户消息。
- 新增已实现接口：GET `/api/v1/engagements/{engagement_id}/fde/dialogue`，用于读取和追加项目问答，不登记工作。
- 新增已实现接口：POST `/api/v1/engagements/{engagement_id}/fde/dialogue`，用于读取和追加项目问答，不登记工作。
- 新增已实现接口：GET `/api/v1/tasks/{task_id}/dialogue`，用于读取和追加任务问答，不写输入或运行。
- 新增已实现接口：POST `/api/v1/tasks/{task_id}/dialogue`，用于读取和追加任务问答，不写输入或运行。
- 新增已实现接口：GET `/api/v1/knowledge/dialogue`，用于按真实检索结果回答并保存问答。
- 新增已实现接口：POST `/api/v1/knowledge/dialogue`，用于按真实检索结果回答并保存问答。
- 新增已实现接口：GET `/api/v1/runtime/status`，用于读取消费者和 Worker 心跳。

所有已实现操作的 operationId、成功状态码、请求字段和原必填字段已自动核对。

## 已审阅适配差异

- Task/Run由持久控制层维护；C2独立Worker消费作业与回填，无公共认领/伪成功回调。工作台含薄项目与 Business 路径。
- 空白 title/goal/objective/scope/task_key/original_request/完成条件被拒绝；is_demo 不接受字符串布尔值。
- related_task_id 输入额外接受 null，等同未提供；跨项目409，不存在404。Task 输出该字段总是存在。
- X-CSRF-Token 保留必填/minLength=1；缺失/空值校验异常统一映射403，错误值同样403，不暴露框架错误正文。
- Cookie 安全方案运行导出名 APIKeyCookie，安全 Cookie 名仍为 __Host-onefde_session；显式本地 HTTP 配置改用 onefde_dev_session。
- Origin 与 JSON Content-Type 在依赖中校验；logout 无请求体，调用时仍应显式传 application/json。
- 错误按具体状态列出 ApiError，details 可省略；JSON Schema anyOf/const 是 Pydantic 对 nullable/单值枚举的等价输出。
- 列表游标按 created_at/id 升序，游标包含列表作用域；不是授权凭据，所有读取仍鉴权。
- 版本列表/详情为两项显式新增接口；TaskInput 增加 processed_by/processing_reason/processed_at/resolved_by_input_id 供核查采用依据。
- TaskAction/采用/评审等跨字段条件由Pydantic model_validator及领域服务检查，生成Schema不重复手写if/then。
- Run完成/产物元数据由内部受控领域服务登记，无公开伪造成功接口；确定性适配仅用于测试。模型修订元数据当前通过部署供给/测试fixture写入，无编辑接口，列表不含配置/密钥。
- Artifact只有元数据读取，无上传/签名下载；有原始证据时必须同项目，评审必须同Run。未认领作业可在事务内证明未执行并撤销；已开始的停止只记录意图，确认停止前保留占用。
- 非空 dependencies 返回409 DEPENDENCIES_NOT_SUPPORTED；capability_versions 仅保存引用文本，尚无能力库校验。

## 已实现（55 个操作）

- GET `/health`
- POST `/api/v1/auth/login`
- GET `/api/v1/auth/session`
- POST `/api/v1/auth/logout`
- GET `/api/v1/engagements`
- POST `/api/v1/engagements`
- GET `/api/v1/engagements/{engagement_id}`
- GET `/api/v1/engagements/{engagement_id}/tasks`
- POST `/api/v1/engagements/{engagement_id}/tasks`
- GET `/api/v1/tasks/{task_id}`
- PATCH `/api/v1/tasks/{task_id}`
- POST `/api/v1/tasks/{task_id}/actions`
- GET `/api/v1/tasks/{task_id}/runs`
- GET `/api/v1/runs/{run_id}`
- GET `/api/v1/runs/{run_id}/events`
- GET `/api/v1/runs/{run_id}/artifacts`
- GET `/api/v1/model-profiles`
- GET `/api/v1/tasks/{task_id}/inputs`
- POST `/api/v1/tasks/{task_id}/inputs`
- POST `/api/v1/tasks/{task_id}/apply-inputs`
- GET `/api/v1/tasks/{task_id}/reviews`
- POST `/api/v1/tasks/{task_id}/reviews`
- GET `/api/v1/tasks/{task_id}/events`
- GET `/api/v1/runs/{run_id}/review-evidence`
- GET `/api/v1/tasks/{task_id}/versions`
- GET `/api/v1/tasks/{task_id}/versions/{spec_version}`
- GET `/api/v1/engagements/{engagement_id}/fde/work-history`
- GET `/api/v1/engagements/{engagement_id}/fde/work/{work_id}`
- GET `/api/v1/engagements/{engagement_id}/fde/work`
- POST `/api/v1/engagements/{engagement_id}/fde/work`
- GET `/api/v1/engagements/{engagement_id}/delivery`
- POST `/api/v1/engagements/{engagement_id}/fde/tools`
- POST `/api/v1/knowledge/tools`
- GET `/api/v1/office/actionable`
- GET `/api/v1/office/activity`
- PUT `/api/v1/public/business/conversations/{case_id}`
- GET `/api/v1/public/business/conversations/{case_id}`
- POST `/api/v1/public/business/conversations/{case_id}/messages`
- POST `/api/v1/public/business/conversations/{case_id}/retest`
- GET `/api/v1/business/cases`
- GET `/api/v1/business/cases/{case_id}`
- POST `/api/v1/business/cases/{case_id}/clarification-draft`
- POST `/api/v1/business/cases/{case_id}/actions`
- POST `/api/v1/business/candidate-search`
- GET `/api/v1/business/candidates`
- POST `/api/v1/business/candidates/{candidate_id}/invite`
- GET `/api/v1/business/cases/{case_id}/assistant`
- POST `/api/v1/business/cases/{case_id}/assistant`
- GET `/api/v1/engagements/{engagement_id}/fde/dialogue`
- POST `/api/v1/engagements/{engagement_id}/fde/dialogue`
- GET `/api/v1/tasks/{task_id}/dialogue`
- POST `/api/v1/tasks/{task_id}/dialogue`
- GET `/api/v1/knowledge/dialogue`
- POST `/api/v1/knowledge/dialogue`
- GET `/api/v1/runtime/status`

## 规划中（1 个操作）

- GET `/api/v1/artifacts/{artifact_id}/download-url`
