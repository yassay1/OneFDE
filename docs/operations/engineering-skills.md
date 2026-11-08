# Coding Agent 技能接入与验证

适用：OneFDE 的 OpenHands Engineering executor，SDK 固定 1.59.0。首批为 systematic-debugging、verification-before-completion、webapp-testing、frontend-design、onefde-engineering-closeout。四个上游技能经缩写与适配，第五个为本项目编写。具体来源提交、原文摘要、适配版本、许可证和文件摘要以[打包清单](../../backend/src/onefde/infrastructure/runtime/engineering_skills/manifest.json)为准。

## 生效方式

技能随后端源码和 wheel 打包，通过可信装配传入 AgentContext。五个技能先呈现摘要，由 OpenHands 原生 invoke_skill 按需取正文；开始引导调用 closeout，提交前引导调用 verification。调试、网页测试和设计由任务需要触发；不保证每轮调用全部技能。提交收尾阶段只保留 verification 与 closeout。技能调用计入原 Run 限额。

继续关闭宿主用户、公共目录和客户项目技能自动发现；不从网络更新、执行技能内的动态命令或加载 MCP 配置。正文直接序列化到远程 Agent Server，不向工程容器暴露宿主技能路径。技能不增加网络、预算、数据库、发布或所有者权限，不改变 Task/Input/Run/接受流程。

每轮在使用模型前验证打包文件摘要；缺失或不符即阻塞。`<Worker root>/private/<Run ID>/engineering-skills.json` 保存本轮清单及实际提供的正文。作业结果 `proof.skills` 保存清单版本、摘要、可用技能和 `invoked`。后者只采集成功的 SDK InvokeSkillObservation，模型自称使用不算调用证据。记录可用与成功调用，不推断技能被正确遵循。

## 无模型复核

Windows 仓库根目录执行，检查本地 WSL 后端打包清单；无需 key、不消费作业：

```powershell
wsl -d OneFDE -u onefde --cd /home/onefde/OneFDE/backend -- .venv/bin/python -m onefde.infrastructure.runtime.skills
```

预期退出 0，`valid=true`、`model_calls=0`，revision 为 `engineering-skills-v1`，skills 恰好五项。检查正在运行的 Compose Worker 可执行：

```powershell
wsl -d OneFDE -u onefde -- docker exec onefde-local-worker-1 python -m onefde.infrastructure.runtime.skills
```

核对原生技能调用、JSON 传输、篡改/缺失拒绝及 Worker 装配，运行确定性替身测试；不会创建真实 LLM 请求或工程作业：

```powershell
wsl -d OneFDE -u onefde --cd /home/onefde/OneFDE/backend -- env LITELLM_LOCAL_MODEL_COST_MAP=True OPENHANDS_SUPPRESS_BANNER=1 .venv/bin/python -m pytest tests/unit/test_engineering_skills.py tests/unit/test_openhands_binding.py -q
```

测试中的临时源码模拟 SDK 行为；SDK 类型、技能解析和 InvokeSkillExecutor 使用真实固定版本。该检查证明接线与隔离，不证明模型主动选择和遵循技能，也不替代真实工程验收。

## 后续真实验证

2026-11-07 已通过 OneFDE 工作台完成一次 MiMo 筛选修复：五项均有真实成功调用，工程自测与独立 Playwright 复验通过，负责人已正式接受。FDE 前置检索达到轮次上限后采用环境说明继续；工程只使用一轮。结果与费用见[测试事实](testing.md#playwright-与-mimo-技能实测2026-11-07)。这证明当前接线与本次任务行为，不证明长期成本或成功率改善。

另行指定一次模型预算后，从 OneFDE 创建小型网页修改任务：要求沿用已接受源码，改善一个交互并实测；提供可信起点和固定检查。成功证据应包含相关 invoke_skill 工具观察、实现差异、固定归档独立复验及实际浏览器结果。按需求观察是否调用对应技能；未发生错误时不要求调用调试技能。比较费用、重试和完成情况，不能只检查模型总结。

webapp-testing 复用工程项目已有工具。当前本地 Compose 已选择[预装 Playwright 的受检镜像](../../deploy/agent-browser/README.md)，工程上下文提供 `/usr/bin/chromium` 和显式启动参数；原基础镜像仍可选择，不能假定它具有 Playwright。缺依赖时保留具体环境缺口，浏览器项维持未验证，继续可运行的检查，不把一次技能调用当作浏览器通过。
