# Business 首版本地操作与验收

使用模拟资料。开发 API 与报价产品分别绑定回环地址。工作台沿用创始人登录；在该登录中执行 FDE 操作时，系统按命令记录 FDE 角色和实际操作者。

## 启动

1. 按[后端说明](../../backend/README.md)配置 PostgreSQL、创始人账号及本地开发 Origin。先执行 `uv run --locked alembic upgrade head`。报价入口默认调用 `http://127.0.0.1:8000`，因此工作台信任 Origin 应与它一致。
2. 在 `frontend` 执行 `npm ci` 和 `npm run build`。启动或重启开发 API，打开 [Business 工作台](http://127.0.0.1:8000/#/business)。
3. 从仓库根目录执行 `python deploy/verify_product_origin.py --serve`，打开[报价产品](http://127.0.0.1:8765/)，找到「联系 Business」。

如调整端口，保持两个独立 Origin，分别修改 `ONEFDE_TRUSTED_ORIGIN`、`ONEFDE_BUSINESS_CUSTOMER_ORIGIN`、报价 HTML 中 `data-api-origin` 以及工作台构建变量 `VITE_QUOTE_PRODUCT_URL`。会话跟进链接包含本单凭证，仅交给本单客户。邀请链接只标记线索来源。

## 验收路径

| 流程 | 操作 | 完成证据 |
| --- | --- | --- |
| 被动咨询 | 发送「CSV 格式是什么？」。重新打开本单跟进链接并问「怎么导出？」。另发「请转人工」或询价，在工作台接管、记内部备注及回复。 | 即时 FAQ 回复，工作台记录 FAQ 与适用版本。接管后的客户消息留给接手人，客户能读对外回复。 |
| 故障及售后 | 发送「CSV 格式没问题，但今天导入报错」，再补「选择 CSV 后点击比较，提示缺少 unit_price」。在原待办核实项目和客户版本，关联或创建 Task。需要变更规格时，从客户消息登记 TaskInput，再经现有采用流程处理。 | 待办保留两条原话引用和复现描述，工作台可看到交接、负责人、项目、版本与 Task。 |
| 售后复试 | FDE 先在 Task 接受固定修复产物，验证发布地址可访问。在原会话选择「确认修复并通知复试」，填写产物 ID、固定版本、地址、步骤和访问检查证据。客户刷新原链接并选择复试结果。 | 「确认可以使用」关闭会话并保存客户确认。「仍然失败」回到 FDE 队列，保留同一待办及历史，后续 Task 关联前一修复 Task。 |
| 主动找店 | 输入区县代码 `440106`，勾选「使用模拟样例」。选店生成演示邀请，由创始人复制分享。打开邀请后发「希望增加供应商筛选」，补充具体操作并勾选愿意继续。 | 候选显示来源、查询时间与筛选理由，客户会话关联候选。取得具体需求及继续意愿后进入 FDE 队列。 |

真实高德查询需为本地 API 配置获准的 `ONEFDE_BUSINESS_AMAP_KEY`。真实搜索按区县 adcode 严格限制，最多读取两页，每页 10 条，最多保存 15 个不同候选。配额或授权错误在工作台显示。邀请链接由创始人自行分享。

## 自动检查

从 `backend` 执行下列命令。PostgreSQL 测试库须以 `_test` 结尾。

```powershell
uv run --locked pytest -q tests/integration/test_business.py tests/unit/test_business_amap.py
uv run --locked --extra worker pytest -q
uv run --locked python -m scripts.check_migrations
uv run --locked python -m scripts.export_openapi --check
```

验收状态与证据见[测试记录](testing.md#business-首版验收)。高德真实数据与授权额度、外部渠道、真实客户资料和公网发布分开验收。

## 外部参考

- 客户原话、带上下文交接和失败复测参考 [anker-go](https://github.com/xiaokekehaha/anker-haike)。本实现使用仓库现有模块。
- 人工接管保留原会话，Chatwoot 留作后续渠道候选。参见 [Chatwoot 部署要求](https://developers.chatwoot.com/self-hosted/deployment/requirements)。
- 区划、分页和返回状态依据 [高德 POI 2.0](https://lbs.amap.com/api/webservice/guide/api-advanced/newpoisearch)。

## 报价 CSV 自动售后试点

触发条件是受信本地操作者在故障交接前登记一个模拟报价会话。使用现有报价页先发「CSV 导入报错」，从工作台取得 Case UUID。准备一个私有暂存目录，保持仓库相对路径，仅复制 `products/demo-supplier-quotes/` 下的 `index.html`、`compare.js`、`app.js`、`business.js`、`check.mjs` 和四个报价样例 CSV。使用已获准的模拟 Engagement、模型配置和运行次数。从 `backend` 执行：

```text
uv run --locked python -m onefde.entrypoints.quote_support enroll --case <Case UUID> --engagement <Engagement UUID> --profile <Profile UUID> --minutes <授权分钟数> --max-runs <1至3> --seed <暂存目录> --store <Worker的artifacts目录>
uv run --locked python -m onefde.entrypoints.quote_support run
```

回到原会话发送「选择 CSV S01-unit-price-space 后点击比较，提示缺少 unit_price」。如收到确认样例的追问，在原会话回复「确认使用 S01-unit-price-space」。工作台可查看自动接单、固定提交待办和关联 Task，也可接管自动处理中的会话。创始人通过原 Task 评审入口接受固定提交。

在获准的内部回环入口复测时，先用以下命令准备一个尚不存在的测试目录，再从独立回环端口提供静态服务。原会话仍使用创建会话时的产品入口。复测者打开通知中的独立测试版本，回原会话填写反馈。

```text
uv run --locked python -m onefde.entrypoints.quote_support prepare-preview --case <Case UUID> --artifact <已接受源码产物UUID> --store <Worker的artifacts目录> --directory <新测试目录>
python -m http.server 8766 --bind 127.0.0.1 --directory <新测试目录>
uv run --locked python -m onefde.entrypoints.quote_support verify-preview --case <Case UUID> --artifact <已接受源码产物UUID> --store <Worker的artifacts目录> --url http://127.0.0.1:8766/
```

验证器比对四个公开文件与固定归档的内容，核验回执有效 60 秒。消费者只有在接受记录与回执均有效时才在原会话发通知。反馈通过关闭 Case。同模板失败可建立关联 Task，版本或范围存疑时进入创始人队列。试点部署与模型执行另见[实施状态](../development/implementation-plan.md#报价-csv-自动售后试点)。

2026 年 11 月 5 日，人工归档及后续真实 Engineering 修订归档均获创始人验收。真实归档完成独立回环复测，原会话反馈后已关闭。自动通知以当前 Task 的接受记录为入口。 [验收记录](testing.md#报价自动售后验收)

### 固定报价能力首次交付

在原交接 Task 规格中记录 `fresh-quote-compare-csv@1.1.0` 和 `[check] node products/demo-supplier-quotes/check.mjs`。可信操作者用批准的原始归档执行 `python -m onefde.entrypoints.reuse_delivery --store <私有产物目录> queue --task <Task ID> --revision <当前 revision> --asset fresh-quote-compare-csv --archive <原始固定归档>`。归档摘要须与能力清单匹配。

从 Worker 运行 `python -m onefde.entrypoints.worker verify-reuse --run-id <Run ID>`。使用共享宿主的 `onefde-engineering-offline` 桥，关闭模型和出口代理。Run 进入待评审后，从项目列表选择首交 Task 并接受。对该产物执行同一 `reuse_delivery` 入口的 `prepare --case <原邀请会话 ID> --artifact <已接受产物 ID> --directory <新目录>`，独立回环供给后用 `deliver --case <原邀请会话 ID> --artifact <已接受产物 ID> --url <独立回环入口>` 核验并登记回复。售后 Task 通过 Business 待办中的 Task 链接直达评审。 [复测记录](testing.md#双-task-工作台评审和首交收尾)

## Business Agent 模拟验收

先在独立 `_test` 库迁移到 head，启动现有回环工作台和报价页。受信进程从 `ONEFDE_BUSINESS_DATABASE_URL` 连接该库，复用已有兼容模型修订和 secret 环境变量。预登记一个固定 Case UUID、模型修订、可选的模拟 Engagement，以及批准的 `Policy` 文件。文件按 nanoUSD 记录费用上界和保守费率，并固定请求、回复和有效期。可选的 Engagement 由受信登记提供，未登记项目的交接留在 FDE 队列。

```text
uv run --locked python -m onefde.entrypoints.business_agent enroll-demo --case-id CASE_UUID --engagement-id DEMO_ENGAGEMENT_UUID --profile-id PROFILE_UUID --policy APPROVED_POLICY_JSON
uv run --locked python -m onefde.entrypoints.business_agent run --case-id CASE_UUID --profile-id PROFILE_UUID
uv run --locked python -m onefde.entrypoints.business_agent report --case-id CASE_UUID --profile-id PROFILE_UUID
```

1. 用现有样例找店与邀请操作得到邀请 ID。在原客户入口用已登记的 Case UUID 创建会话，保留同一个会话凭证。程序复跑可使用现有 `PUT /api/v1/public/business/conversations/{case_id}`，传邀请 ID 和新的请求 ID。
2. 客户先说「店里供应商报价每天都很乱，希望处理得省事一点」。等 Business 追问后在原会话补充目标和具体操作，提交当轮的「愿意继续」勾选。交接必须能查到原消息、当前意愿、逐字事实、未知项和适用版本。售后另查复现原话。
3. 查询已登记项目的 FDE Work，按 [FDE 启动说明](fde-agent-v1.md#启动与授权) 用 `once --work-id` 和已授权额度处理该 Work，核对 FDE 引用同一交接并给出下一步。咨询和邀约的对外方案反馈从原会话选择「批准 Business 转达 FDE 方案反馈」，核准文本后由 Business 原文转达。修复和复试使用本手册既有流程。
4. 在另一个已登记 Case 询问报价页导出方式，给出明确的 `1.1.0` 版本。核对答案来源 `faq:export`、修订 `quote-faq@1` 和产品版本。再用另一个 Case 请求人工或描述售后问题，核对负责人和状态。客户入口刷新原会话即可读取回复。

参考做法保留在 OneFDE 的现有服务边界内。Case 归属和接管决定谁能处理新消息，采用 Chatwoot 的会话事件和显式接管思路。模型选择工具和业务命令，采用 Rasa CALM 的对话理解与命令分离。对外回答使用授权原文，升级和后续由业务流程控制，参考 Fin。 [Chatwoot AgentBot](https://app.chatwoot.com/hc/user-guide/articles/1677497472-how-to-use-agent-bots) · [Rasa CALM 对话理解](https://learning.rasa.com/rasa-pro/dialogue-understanding/) · [Intercom Fin Procedures](https://www.intercom.com/help/en/articles/13449439-building-fin-procedures)

本轮验收使用确定性模型回复。DeepSeek 密钥已配置，未查到适用于本轮 Business 与 FDE 验证的现有调用额度，历史工程预算对应指定 Run。真实模型请求、计费 token 和费用均为零。 [验收记录](testing.md#business-agent-首版验收)
