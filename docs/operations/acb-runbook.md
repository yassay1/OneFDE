# OneFDE 可运行 / 调试 / 演示手册（A→C→B 收口）

适用范围：本地 Windows 源码 + WSL `OneFDE` Compose（`127.0.0.1:8002`）。**不做公网部署。**

## 推荐日常入口（Compose，含 SPA）

可信 Origin：**http://127.0.0.1:8002**（不要用 `localhost` 混开，Cookie Origin 必须一致）。

```powershell
# Windows：同步已审阅源码（不含密钥）
Set-Location D:\proj\OneFDE
python backend\local-wsl\sync_source.py
# 如需更新工作台构建产物：先在 Windows frontend 执行 npm run build，再把 dist 打进 WSL（见阶段 C 做法）
```

```bash
# WSL OneFDE
cd /home/onefde/OneFDE
docker compose --env-file /srv/onefde-local/private/compose.env -f deploy/compose.yaml up -d --wait api worker egress postgres
docker compose --env-file /srv/onefde-local/private/compose.env -f deploy/compose.yaml --profile ops run --rm migrate
```

登录：用户名 `founder`；密码仅在 `/srv/onefde-local/private/owner_password`（勿写入 Git/证据）。

健康检查：`curl http://127.0.0.1:8002/health`

## Windows 开发 API（可选）

`http://localhost:8000` + `backend-postgres`（55432）。与 Compose **不同库**，密码也可能不同。F1–F6 UI 联调可用；真实 Worker 烟测以 Compose 为准。

```powershell
Set-Location D:\proj\OneFDE\backend
docker compose start   # 如 postgres 已停
uv run --locked alembic upgrade head
uv run --locked uvicorn onefde.entrypoints.api:create_app --factory --host 127.0.0.1 --port 8000
```

浏览器必须用 **localhost:8000**（`ONEFDE_TRUSTED_ORIGIN`）。

## 真实 Engineering 烟测（需费用授权）

默认 Compose Worker **关闭**模型执行。授权后在 WSL 仓库根：

```bash
export ONEFDE_SMOKE_PROVIDER=mimo
export ONEFDE_WORKER_MAX_COST_USD=1.40   # ≈¥10 硬顶；脚本上限 5 USD
export ONEFDE_WORKER_MAX_REQUESTS=20
backend/.venv/bin/python deploy/run_c2_webpage.py
```

- 成功证据：`work/c2-mimo-webpage-smoke.json`
- 达到费用/请求上限立即停止，**不要**自动加额度
- 密钥经环境注入，证据中不得出现

接受提交（有 artifacts 即可；缺 `review_material` 时证据面板可能仍空）：

```bash
backend/.venv/bin/python deploy/_tmp_accept_direct.py   # 或等价 reviews POST
```

## 调试清单

| 现象 | 检查 |
| --- | --- |
| 登录 403 | Origin 是否与 TRUSTED_ORIGIN 完全一致（`127.0.0.1:8002` 与 `localhost:8002` 不等价） |
| Business/FDE/Office 503 `DATABASE_UNAVAILABLE` | 先 `alembic upgrade head`；再确认 `onefde_app` 对新建表有 **SELECT**（迁移后须重跑 `deploy/ops/initialize.py` 或显式 GRANT）。Office 曾因 `fde_agent_work` 缺 SELECT 失败 |
| `/` 404 或办公室仍是 F6「有限摘要」文案 | API 镜像是否含最新 `frontend/dist`；`docker compose build api && up -d --force-recreate api`；浏览器禁用缓存硬刷新 |
| Worker 不认领 | `execution-check`：模型开关与费用上限 |
| Office 待办空 | 派生结果（无 open Case / 无 actionable Task）；看响应 `coverage`；勿与「项目摘要」混为一谈 |
| Engineering 证据面板空 | 可能缺 `review_material`；artifacts + reviews 仍可接受 |

## 演示路径（已验收样例 · 阶段 C + G6）

1. 打开 http://127.0.0.1:8002 → 登录 `founder`  
2. 办公室：coverage 应含「派生自当前库内…扫描上限…」；「需要你处理」与「近期动态」分列；点条目应进原对象  
3. Engineering 深链（C 次真实 MiMo）：

`http://127.0.0.1:8002/#/engineering?project=abf93076-50f7-4183-920e-1903c246d05a&task=65f13aad-fcac-4469-971c-45c7c94f68dd&run=a7fa3a12-e2de-4355-94eb-1f47c1e90caf&view=submission`

应看到 Task「已接受」、第 1 轮 completed/submitted、运行事件与评审「已接受」。

## 边界

- 常驻 Worker 保持 `model_execution_enabled=false`，仅 once 烟测显式开启  
- 无公网、无 CRM、无通知中心  
- G6 无 totalCount；扫描有 cap，见 API `coverage`
