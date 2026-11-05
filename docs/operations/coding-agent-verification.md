# Coding Agent 工程契约与固定验证记录

2026年11月4日。本轮在既有 C2 Worker/SDK 与本地 S1/S2 沙盒之上，实现并验证 Engineering 上下文、类型化结果契约、工作区比对与固定源码验证；同日用户配置 DeepSeek Key 后完成**真实模型网页小任务（CA02）**。

## 环境与范围

| 项 | 事实 |
| --- | --- |
| 宿主 | OneFDE WSL2 + 本地 `onefde-local` Compose（ecs_shared） |
| SDK | openhands-sdk/workspace/tools **1.59.0**；未升级 |
| 模型 | DeepSeek `openai/deepseek-flash`；修订 `488fa83c-a2d7-410b-8981-b55cbb053c9d`；本轮 `max_cost_usd=1` |
| 出口 | Sandbox 经 `HTTPS_PROXY=http://172.29.241.3:3128`（仅 `api.deepseek.com`） |
| 业务数据 | 未清开发库；演示 Task 明确标注 DEMO |

## 本轮实现

| 能力 | 位置 | 说明 |
| --- | --- | --- |
| 检查派生与角色修订 | `core/engineering.py` | `[auto]`/`[check]` → 自动检查；其余为业务评审；`ROLE_REVISION`/`CONTEXT_REVISION` |
| 上下文装配与结果契约 | `infrastructure/runtime/engineering.py` | 清单、角色后缀、Finish JSON 校验；`spec.inputs` 为任务输入，`spec_version` 来自 Run 固定版本；无关 exit 0 / 自报 passed 不能 submitted |
| 工作区比对/恢复 | 同上 + `OpenHandsAdapter.execute` | prior source 含已确认停止的 completed/failed 归档；漂移 `WORKSPACE_DRIFT`；interrupted 不作基准；空目录可从归档受控恢复 |
| 多现场资源登记 | `modules/tasks/dispatch.py` | `runtime_ref.resources[]` 支持 engineering + validation；同角色换 ID 冲突 |
| Run 快照 engineering | `modules/tasks/commands/runs.py` | checks、prior_source、prior_failures、固定 `spec_version` 写入快照；无新 HTTP 字段 |
| 固定源码验证 | `OpenHandsAdapter._validate_fixed_source` | 无模型容器执行登记命令；服从停止信号与 Run 总截止；新增/删除/修改源码均拒绝；仅 `bash_events/` 工具日志除外；异常且停止未知则 interrupted |
| 真实无模型验收脚本 | `deploy/verify_coding_agent.py` | 五组 Docker 实测 |

## 实际命令与结果

从仓库根（OneFDE WSL）：

| 命令 | 结果 |
| --- | --- |
| `uv run --locked --extra worker pytest -q --junitxml=work/ca-tests.xml` | **113 passed，0 skipped**；见 [JUnit](evidence/coding-agent-tests.xml) |
| `ruff check` / `ruff format --check`；`scripts.export_openapi --check` | 通过；HTTP 契约字段未变 |
| `scripts.c2_smoke` / `scripts.c1b_smoke` | 9 / 35 项 HTTP 控制检查通过；无模型 |
| `worker check --environment-only` | 退出 0（local_wsl 演示配置） |
| `worker check`（完整执行预检） | 阻塞：模型未启用、缺费用上限 |
| `ONEFDE_WORKER_*=ecs_shared... python deploy/verify_coding_agent.py` | **5 组通过**，`model_called=false`；见 [JSON](evidence/coding-agent-no-model.json) |

无模型脚本覆盖：冻结归档、漂移阻塞、无关 exit 0 拒绝、验证容器命令+源码篡改检测、完整提交门槛与停止确认。归档 SHA256：`65e6d66fd262a9ac8f1a11e5910f8f748ad3e76c67c95935c532cb894a46f131`（环境前缀，非业务 Artifact 版本）。

## CA 场景状态

| 编号 | 状态 | 证据边界 |
| --- | --- | --- |
| CA01 | 部分通过（确定性） | 单元：pending 提醒不进授权；快照只含已采用输入 |
| CA02 | **通过** | 真实 DeepSeek 改文件/命令/归档/停止；见下方 C2 证据 |
| CA03 | 未专项执行 | 本轮一次通过，未注入失败修复循环 |
| CA04 | 通过 | 单元 + 无模型容器 + 首轮真实模型反例（格式失败未放行） |
| CA05 | 通过 | 真实 Run 含 validation 容器且 `source_unchanged` |
| CA06 | 控制路径 + 本轮单轮真实提交/接受 | 多轮续作仍以 c1b 确定性为主 |
| CA07 | 通过（确定性 + 脚本） | 漂移阻塞；空目录受控恢复 |
| CA08 | 控制路径保留 | 真实模型中途取消未测 |
| CA09 | 未执行 | 知识服务后置 |
| CA10 | **通过（本轮）** | submitted→review→founder accept；无发布 |

## 真实模型 C2 网页证据（2026-11-04）

命令：`ONEFDE_WORKER_MAX_COST_USD=1 backend/.venv/bin/python deploy/run_c2_webpage.py`（Compose API + 宿主 Worker once；密钥不入日志）。

| 项 | 值 |
| --- | --- |
| Task | `a2d797a5-ed37-4403-8645-46b26074b125` → **succeeded** |
| Run | `523cad22-acfd-40e7-9f84-9c739e34afe1` → completed/submitted |
| Review | `a3fbf2d6-c3ab-4aaf-842c-a0e1977ffeaa` accept |
| 产物 | `workspace.tar.gz` SHA256 `2e4c070bb9b8942933386f07dd6b4d3b5e5894e703aeca682404d52f95704ea1` |
| 现场 | engineering + validation 均停止；自动检查 `sh /workspace/check.sh` exit 0 |
| 耗时 | ~28s；费用上限 $1（SDK `accumulated_cost` 观测为 0.0，不能据此称提供方硬封顶） |
| 证据 | [c2-webpage-smoke.json](evidence/c2-webpage-smoke.json)、[c2-webpage-review.json](evidence/c2-webpage-review.json) |

首轮失败（`RESULT_FORMAT_INVALID`）因模型把 JSON 写进 MessageEvent 且检查命令被串联；已补 Finish/围栏 JSON 回退与复合命令段匹配后重跑成功。密钥未写入共享证据。

## 审查修复验证（2026年11月5日）

未调用模型，未重跑上面的五组 Docker 脚本，也未做云端验收。控制逻辑用替身覆盖原缺陷；数据库检查只连独立测试库 `onefde_test`。

| 命令 | 结果 |
| --- | --- |
| `uv run --locked pytest -q tests/unit` | 57 passed |
| `uv run --locked pytest -q tests/integration/test_task_lifecycle.py tests/integration/test_worker.py tests/integration/test_task_boundaries.py tests/architecture` | 53 passed，1 warning（既有 Starlette/httpx 弃用提示） |
| `uv run --locked ruff check`（本轮改过的运行时、Run 命令和对应测试） | 通过 |

替身覆盖：验证异常且停止未知、清理异常且停止未知、隐藏路径往返与逃逸拒绝、输入/规格版本映射、验证前取消或超时、执行中检查受控停止、失败归档续作、interrupted 不作基准、新增 `dist/app.js` 拒绝、`bash_events/` 不计入源码。停止不明的回填不释放全局名额。

## 明确未完成

1. 云端 E01—E11 / E07 费用与停止延迟的生产级验收不能由本地冒烟替代。
2. 薄 FDE 角色 Runtime / 工作台前端不在本轮。
3. Compose 内 standby Worker 镜像未含本轮源码；真实执行走宿主 venv Worker。
4. 提供方实际计费明细与硬配额仍待对照账单核对。
5. 本轮六项修复没有重跑真实验证容器。登记检查若写出 `bash_events/` 以外的文件，固定验证会拒绝；目前没有新的沙盒证据。真实模型中途取消仍未测。
