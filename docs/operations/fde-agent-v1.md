# FDE Agent 首版运行与验收

MiMo 产品演练补充：FDE 与 Engineering 可选 MiMo；Chat 请求使用 MiMo 对应输出参数并关闭思考模式。派发或读取仍活跃的 Run 后结束本轮并等待，保存评审建议后结束当轮；Task 已接受或取消后直接报告，不再消耗模型。具体经过与边界见[果采报价台测试](testing.md#mimo-果采报价台产品全链路2026-11-07)。

适用于在现有项目启动 FDE 或继续已批准的 Business 交接。控制边界见 [ADR0001](../architecture/ADR/0001-coordination.md)，结果见[验收场景](testing.md#fde-agent-首版验收)。

## 启动与授权

1. 在独立 PostgreSQL 库执行 `uv run --locked alembic upgrade head`。自动演练库沿用 `_test` 后缀。按[后端说明](../../backend/README.md)启动工作台。项目页可以提交目标。Business 交接已关联 Task 时，原接手命令同事务登记 FDE 工作。交接还没有 Task 时，从原会话选择已核实项目并启动 FDE。
2. 为可信 FDE 进程注入 `ONEFDE_FDE_DATABASE_URL` 和模型修订引用的 secret 环境变量。模型修订按[现有 Worker 手册](../../backend/WORKER.md)供给。预算文件 `ModelBudget` 保存授权金额和保守费率上界，使用 nanoUSD。输入 token 上界按供应商单次请求的有效上限登记。请求前预留，收到合法用量后结算，缺失用量时保留预留额。
3. 只在隔离模拟库需要自动发送或派发时，为指定 Work 登记 `DemoPolicy`。固定有效期、澄清次数、FDE 请求和费用上限、Engineering Run 次数与单次费用上限，以及可信归档摘要、文件范围和检查命令。Worker 的 SDK 费用配置参与认领校验，提供方硬封顶由已授权的受控出口保证。
4. 在 `backend` 下运行以下命令。演练用 `--work-id` 限定单条工作。FDE 的 `--store` 和 Engineering Worker 的 `root/artifacts` 使用同一私有存储。

```text
uv run --locked python -m onefde.entrypoints.fde_agent enroll-demo --work-id WORK_UUID --profile-id PROFILE_UUID --store PRIVATE_ARTIFACTS --policy APPROVED_DEMO_POLICY_JSON --archive STARTER_TAR_GZ
uv run --locked python -m onefde.entrypoints.fde_agent run --work-id WORK_UUID --profile-id PROFILE_UUID --store PRIVATE_ARTIFACTS --budget APPROVED_MODEL_BUDGET_JSON --max-model-calls APPROVED_CALLS
uv run --locked --extra worker python -m onefde.entrypoints.worker check
uv run --locked --extra worker python -m onefde.entrypoints.worker once --run-id RUN_UUID
```

`enroll-demo` 是受信操作。普通项目由 FDE 整理方案、草拟澄清和保存 Task，负责人使用现有会话和 Task 命令发送与派发。首版每条工作关联一个 Task。Business 与 Knowledge 沿用现有服务，Knowledge 比较最多三个可见固定版本。

## 维修报价模拟项目

用[维修报价查看项目](../../engagements/demo-repair-quote-view/brief.md)作为基线。在原模拟会话提交「撤回报价后，希望客户能看懂下一步」。待 FDE 澄清后，由测试者在原会话回答，例如确认通用提示「此报价已不可用，请联系门店」并继续隐藏报价明细。受信方固定可改文件和回归命令。现有 `python -B -m unittest -v check_quote` 校验客户归属、店员控制与旧链接，文案单列在完成条件中。

真实退出证据同时包含 FDE 模型工具往返、原会话补答和已采用输入、真实 OpenHands Run、固定源码摘要及独立检查、现场停止、两种模型的请求和 token 用量。FDE 建议引用当前 Run 和产物，并给出需要人决定的事项。工程提交、业务接受和发布分别查对应记录。

现有 DeepSeek 密钥存在，WSL 环境预检通过。执行预检返回 2，Worker 模型开关关闭且缺少本轮费用上限及提供方配额。历史授权覆盖指定的单次 Engineering Run。本轮真实模型请求和费用均为零。兼容字段见 [DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)。

