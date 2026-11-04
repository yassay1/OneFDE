# OneFDE 后端与受控 Worker

已实现单创始人 Cookie 会话、Engagement、工程 Task、输入记录/采用、不可变规格版本、Run/待派发记录、轻量评审和有序事件。Task 创建为 draft，固定 `owner_role=fde`、`executor_role=engineering`。C2新增独立Worker认领/心跳/停止确认/回填及固定OpenHands接线；真实Linux/模型冒烟受环境阻塞。202仅表示持久接单。Worker操作与限制见 [专用节点手册](WORKER.md)，本轮证据见 [C2验证](../docs/operations/c2-verification.md)。

## 首次本地启动（PowerShell）

前提：Python 3.13、uv、运行中的 Docker Desktop Linux Engine。以下命令从 `D:\proj\OneFDE\backend` 执行；数据库端口只绑定本机。

```powershell
Set-Location D:\proj\OneFDE\backend
uv sync --locked
Copy-Item .env.example .env  # 仅首次；已有 .env 时直接编辑并保留数据库密码
uv run --locked python -m onefde.entrypoints.cli hash-password
```

该命令隐藏输入并要求至少12字符，输出 Argon2id 摘要。编辑 `.env`：用自己的数据库密码替换 `POSTGRES_PASSWORD` 和两个 URL 中的占位值；将密码摘要粘贴到 `ONEFDE_OWNER_PASSWORD_HASH` 的**单引号内**，避免 Compose 展开 `$`。数据库 URL 密码中的特殊字符需 URL 编码，推荐随机字母数字密码。`.env` 和 `work/` 被忽略，仅保存在本地受限目录；勿将摘要或真实凭据写入业务资料。

```powershell
docker compose up -d --wait
uv run --locked alembic upgrade head
uv run --locked alembic check
uv run --locked uvicorn onefde.entrypoints.api:create_app --factory --host 127.0.0.1 --port 8000
```

浏览器打开 [开发接口文档](http://localhost:8000/docs)。Swagger 提供已实现接口和字段说明；POST 要求可信 Origin、JSON、登录后的 X-CSRF-Token，创建另要求 Idempotency-Key。建议用下面的 HTTP 示例完整操作，尤其登出需显式 Content-Type。`/health` 仅代表进程存活，不检查数据库或未来执行环境。

Compose 首次在新卷内创建 `onefde_dev` 和 `onefde_test`。已有卷不会重新执行初始化 SQL，也不会随 `.env` 修改旧数据库密码。若自备 PostgreSQL，以管理身份创建两个独立库并调整 URL；测试库名必须以 `_test` 结尾，测试会清空这五张业务表。保留卷时可 `docker compose stop` / `docker compose start`，不需要删除数据。

## 用 HTTP 操作

另开 PowerShell，服务保持运行：

```powershell
$base = 'http://localhost:8000/api/v1'
$credential = Get-Credential -UserName founder -Message 'OneFDE 本地创始人账号'
$login = @{username=$credential.UserName; password=$credential.GetNetworkCredential().Password} | ConvertTo-Json
$identity = Invoke-RestMethod "$base/auth/login" -Method Post -ContentType 'application/json' -Headers @{Origin='http://localhost:8000'} -Body $login -SessionVariable browser
Remove-Variable login, credential
$headers = @{Origin='http://localhost:8000'; 'X-CSRF-Token'=$identity.csrf_token; 'Idempotency-Key'=[guid]::NewGuid().ToString()}
$body = @{title='模拟项目'; is_demo=$true; goal='检查后端草稿持久化'} | ConvertTo-Json
$engagement = Invoke-RestMethod "$base/engagements" -Method Post -WebSession $browser -Headers $headers -ContentType 'application/json' -Body $body
# 同键同请求可再次调用，返回相同 id；同键改内容返回409。
$headers['Idempotency-Key'] = [guid]::NewGuid().ToString()
$draft = @{
  request_id=[guid]::NewGuid().ToString(); task_key='first-engineering'; original_request='创建模拟工程草稿'
  owner_role='fde'; executor_role='engineering'
  spec=@{
    title='模拟草稿'; objective='验证持久化'; scope='只创建与查询'
    inputs=@('明确标注的模拟输入'); confirmed_rules=@(); completion_criteria=@('重启后可查回')
    dependencies=@(); capability_versions=@()
  }
} | ConvertTo-Json -Depth 10
$task = Invoke-RestMethod "$base/engagements/$($engagement.id)/tasks" -Method Post -WebSession $browser -Headers $headers -ContentType 'application/json' -Body $draft
Invoke-RestMethod "$base/engagements" -WebSession $browser
Invoke-RestMethod "$base/engagements/$($engagement.id)" -WebSession $browser
Invoke-RestMethod "$base/engagements/$($engagement.id)/tasks" -WebSession $browser
Invoke-RestMethod "$base/tasks/$($task.id)" -WebSession $browser
Invoke-RestMethod "$base/auth/session" -WebSession $browser
Invoke-RestMethod "$base/auth/logout" -Method Post -WebSession $browser -Headers $headers -ContentType 'application/json' -Body '{}'
```

在登出前停止/重启 API，再读取相同 ID，即可人工检查持久化。会话也保存在数据库中，可跨进程继续，绝对有效期默认8小时。

## 自动检查

```powershell
uv run --locked pytest -q --junitxml=work/pytest.xml
uv run --locked ruff check src tests scripts migrations
uv run --locked ruff format --check src tests scripts migrations
uv run --locked python -m scripts.export_openapi --check
uv run --locked python -m scripts.http_smoke
uv run --locked python -m scripts.c1b_smoke
```

pytest 从 `ONEFDE_TEST_DATABASE_URL` 读取独立 PostgreSQL 测试库，自动运行 Alembic 并在每项测试前清表；不会用 SQLite。HTTP 冒烟询问创始人密码，在随机本地端口启动两个独立 API 进程并创建标注的模拟记录，检查登录、CSRF、创建/查询、重放/冲突、重启持久化和登出；结束后关闭 API，开发数据库保留模拟记录。它使用开发库，不是测试清表流程。证据写入 `work/http-smoke.json`，不含密码、Cookie 或 CSRF 值。

变更 Pydantic/API 后执行 `uv run --locked python -m scripts.export_openapi` 并审阅 [契约差异](../docs/architecture/openapi-diff.md)。`openapi.implemented.json` 等同生产安全 Cookie 基线的运行字段；[openapi.yaml](../docs/architecture/openapi.yaml) 在同一路径保留未来设计，以 `x-onefde-status` 区分。`openapi.planned.yaml` 是实现前设计快照，非运行契约。CI 配置见 `../.github/workflows/backend.yml`，本轮仅本地执行，尚未在远程 CI 运行。

## 事务、认证与限制

- 每请求独立 SQLAlchemy Session；认证查询开启短事务，业务服务在响应前显式 commit；异常/请求结束关闭 Session 并 rollback。业务创建、JSON 响应快照及幂等记录同事务提交，无后台提交，也不跨外部执行持有事务。
- 幂等作用域为账号/方法/路径/key，正文按已校验模型规范化后摘要。事务级 advisory lock 串行同键并发；24小时内原成功状态（200/201/202）和正文重放，异内容409。Task 另受项目内 `(request_id, task_key)` 唯一约束，HTTP 键过期也不能重复同一 Task。一个 request_id 可拆多个不同 task_key。Engagement 没有永久业务去重键，24小时后重用 HTTP 键视为新创建。
- 单账号配置只有用户名和 Argon2id 摘要，无注册。数据库只存随机会话 token 的 SHA-256 摘要；CSRF 为服务端会话同步 token。重登轮换当前浏览器会话，登出删除会话；轮换用户名/摘要并重启进程使旧会话失效。登录全局每5分钟最多10次（含成功），持久化计数跨进程；失败不区分账号是否存在。
- 默认生产要求 HTTPS、`__Host-onefde_session`、Secure/HttpOnly/Path=/、SameSite=Lax、无 Domain。只有显式 development + cookie_secure=false 使用 `onefde_dev_session`。生产将环境改为 production，可信 Origin 设实际 HTTPS 源，cookie_secure=true；本轮无公网部署。无通配 CORS。
- 运行 `uv run --locked python -m onefde.entrypoints.cli prune-expired` 删除已过期会话和幂等正文。过期校验立即生效，不依赖清理；当前为人工维护命令，没有自动调度。
- 非空 dependencies 明确409；related_task_id 必须存在且同项目。capability_versions 仅保存引用，不提供能力检索或有效性认证。输入/错误不回显密码，统一包含 code/message/request_id，字段错误仅给 loc/type。
- TaskInput/Run/版本/评审/事件与待派发控制保持原契约；独立Worker按配置消费，不在API进程执行模型。尚无前端、报价规则、发布接口、下载签名或对象存储接入。

实际执行证据见 [C1b验证记录](../docs/operations/c1b-verification.md)；前轮固定参考版本和C1a证据保留在 [C0+C1a记录](../docs/operations/c0-c1a-verification.md)。

## C1b 的使用与边界

已有环境执行 `uv run --locked alembic upgrade head`，当前head为d5454eda0523。C1b的4bf8db3c4ef3保留旧项目/草稿并回填不可变版本1，C2只扩展作业认领/回填字段。已有相关历史时降级会明确拒绝，避免删掉事实；需要回退时使用审阅过的备份或前向迁移，不直接删除历史。

所有写命令沿用 Cookie、Origin、JSON、CSRF 和 Idempotency-Key。任务写入另带当前 `expected_revision`；同键重放先于版本/状态检查。不要用旧响应的 revision 继续新命令，先读当前 Task。新增接口：

| 接口 | 行为 |
| --- | --- |
| PATCH `/api/v1/tasks/{id}` | 无活动Run/待处理输入时替换完整spec，revision/spec_version各加1并回draft |
| POST/GET `/api/v1/tasks/{id}/inputs` | 保存pending输入/按sequence补读；保存只增revision，不改Run快照 |
| POST `/api/v1/tasks/{id}/apply-inputs` | 显式采用/拒绝与理由；非空采用增加一个spec_version，拒绝不增加；采用范围变更必须提交完整spec |
| GET `/api/v1/tasks/{id}/versions`、`/versions/{version}` | 查询不可变spec、已采用输入ID、处理者和依据 |
| POST `/api/v1/tasks/{id}/actions` | queue/start/continue/retry/cancel/stop_for_update；start等原子登记Run与作业，当前不执行 |
| GET `/api/v1/tasks/{id}/runs`、`/api/v1/runs/{id}` | 读取Run状态、固定版本与采用输入ID |
| POST/GET `/api/v1/tasks/{id}/reviews` | 固定当前submitted Run/版本/产物的轻量评审；request_changes追加pending变更输入，accept才使Task成功 |
| GET `/api/v1/tasks/{id}/events`、`/api/v1/runs/{id}/events` | 有序事件，支持after_sequence/limit断线补读 |
| GET `/api/v1/runs/{id}/artifacts`、`/api/v1/model-profiles` | 仅固定产物/配置修订元数据，不返回object_key或密钥 |

采用answer同时采用并解决对应question；不能单独采用未答question，也不能把拒绝问题当作已答来continue。采用期间有活动/现场不明Run会409；运行期间可以记录pending输入，已固定Run看不到新授权。等待回答时Task保持waiting_input，采用后显式continue创建新Run。

创始人从会话身份记录为操作者，客户端不能伪造author、reviewer、origin_run_id或Engineering身份。评审产物必须属于同一提交和当前规格；accept要求无pending输入、没有未答问题且有检查证据。工程结果仅进入review，不自动完成Task。输入正文、已处理采用依据、Run快照/结果、版本、评审、产物元数据和事件有数据库层历史保护。

一个全局活动Run由事务锁和PostgreSQL部分唯一索引约束；interrupted也占用。未认领的queued/pending作业在行锁下可证明未执行并立即撤销；已开始的cancel/stop_for_update只登记停止意图，必须经内部受控结果登记确认停止后释放。interrupted的受控运维恢复尚未接入，HTTP不能强行释放或直接retry。

模型修订是部署供给的不可变元数据，无模型配置编辑API；C2提供受信任CLI导入非秘密配置。当前开发库没有真实模型配置，start若未选择已存在的有效修订会409 MODEL_PROFILE_UNAVAILABLE。Run完成/问题/产物由内部 `onefde.modules.tasks.service` 受控边界登记，没有公共成功回报接口；只有另行启动且配置完备的Worker才消费作业，queued不能描述为已执行。

### 在HTTP中记录与采用输入

沿用上面登录示例的 `$base`、`$browser`、`$headers` 和 `$task`（须在登出前操作）；每个新写命令换一个键：

```powershell
$current = Invoke-RestMethod "$base/tasks/$($task.id)" -WebSession $browser
$headers['Idempotency-Key'] = [guid]::NewGuid().ToString()
$inputBody = @{expected_revision=$current.revision; kind='clarification'; text='明确标注的模拟范围补充'; evidence_artifact_ids=@()} | ConvertTo-Json
$saved = Invoke-RestMethod "$base/tasks/$($task.id)/inputs" -Method Post -WebSession $browser -Headers $headers -ContentType 'application/json' -Body $inputBody
$headers['Idempotency-Key'] = [guid]::NewGuid().ToString()
$applyBody = @{expected_revision=$saved.task.revision; apply_ids=@($saved.input.id); reject_ids=@(); reason='采用模拟范围'; spec=$saved.task.spec} | ConvertTo-Json -Depth 10
$adopted = Invoke-RestMethod "$base/tasks/$($task.id)/apply-inputs" -Method Post -WebSession $browser -Headers $headers -ContentType 'application/json' -Body $applyBody
Invoke-RestMethod "$base/tasks/$($task.id)/versions" -WebSession $browser
Invoke-RestMethod "$base/tasks/$($task.id)/events" -WebSession $browser
```

### 无模型的完整控制验证

运行 `uv run --locked python -m scripts.c1b_smoke`。脚本仅允许独立 `_test` PostgreSQL库，不改开发库配置/账号，不清空已有库；若测试库已有活动运行会要求先核查。它生成短期内存凭据和明确标注的测试配置，启动两个回环HTTP进程；内部确定性适配登记问题、提交和模拟产物元数据，再通过HTTP执行答复/采用/续作/要求修改/再采用/接受，重启后核对Run/版本/评审。没有模型调用、Worker、文件构建或真实产物执行证据。

测试会留下标注模拟的记录；之后pytest将清空指定测试库。结果为 `work/c1b-http.json`，服务日志为 `work/c1b-http-server.log`。这与使用开发库、交互式密码的C1a `scripts.http_smoke` 是两个明确分开的验证入口。

## 代码组织与重构

后端为正式安装包`src/onefde`，使用auth/engagements/tasks业务模块、入口装配与基础设施适配。修改代码前按 [代码组织与依赖规则](../docs/development/code-structure.md) 找到所属模块；C1b后的结构重构保持原业务和两份迁移不变，历史证据见 [结构重构验证](../docs/operations/structure-refactor-verification.md)。之后C2按该边界新增worker控制器、SDK/私有产物适配及第三份增量迁移，原测试继续保留。

`uv sync --locked`会可编辑安装当前包；无须设置PYTHONPATH或把src注入sys.path。需要分发检查时执行`uv build --out-dir work/dist`。仅验证纯规则和依赖可运行`uv run --locked pytest tests/unit tests/architecture -q`，不要求数据库；完整集成检查仍使用独立PostgreSQL测试库。
