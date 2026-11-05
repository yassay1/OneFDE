# OneFDE本地WSL开发环境

适用范围以[ADR0007](../../docs/architecture/ADR/0007-local-wsl-development.md)为准。只用于自有授权演示；后续单ECS目标见[部署设计](../../docs/operations/deployment.md)，当前可执行命令仍按[Worker手册](../WORKER.md)。环境就绪不等于C2真实模型工程成功。

## 本机布局与启动

Windows源码`D:\proj\OneFDE`仍是Git维护入口。专用发行版`OneFDE`的50GB动态盘位于`D:\WSL\OneFDE`；Linux源码`/home/onefde/OneFDE`、私有Worker根`/home/onefde/runtime`。本发行版关闭Windows磁盘自动挂载/程序互操作，使用独立Docker Engine，不启用Docker Desktop集成，不改全局`.wslconfig`。

独立Compose项目`onefde-wsl`的开发/测试库为`onefde_wsl_dev`/`onefde_wsl_test`；PostgreSQL只发布`127.0.0.1:55433`。既有Windows开发数据库与凭据保持原样。Linux用户onefde固定UID10001，与当前Agent Server用户一致，私有挂载保持700。所有者临时密码在`/home/onefde/private/owner-password`；Linux backend内的`.env`/`.env.worker`分别保存控制配置和受限Worker连接，权限600，不提交/挂载工程容器。

PowerShell进入环境：

```powershell
wsl -d OneFDE --cd /home/onefde/OneFDE/backend
```

Linux中启动数据库并验证环境：

```bash
docker compose --env-file .env -f local-wsl/compose.yaml up -d --wait
uv run --locked --extra worker python -m onefde.entrypoints.worker check --environment-only
uv run --locked --extra worker python local-wsl/check_environment.py
```

环境检查应退出0；真实SDK容器检查结果为`work/wsl-environment.json`。它不创建Agent/LLM/业务Task/Run。完整`worker check`和`once/run`当前应退出2：模型开关关闭、费用未配置。不要填虚假额度或把专用节点确认设为true。

需手工操作本地控制API时前台运行：

```bash
uv run --locked uvicorn onefde.entrypoints.api:create_app --factory --host 127.0.0.1 --port 8001
```

接口入口`http://127.0.0.1:8001/docs`；认证/CSRF/幂等沿用[后端README](../README.md)。这是新的演示库，不会自动看到Windows原数据库的Task。同机使用时为该实例使用独立浏览器配置文件：不同端口不能隔离同名Cookie。本轮不安装常驻API/Worker服务。

## 同步与首次配置

Windows编辑后同步源码，保留Linux配置/工作区、不删除旧文件：

```powershell
Set-Location D:\proj\OneFDE
python backend\local-wsl\sync_source.py
```

依赖变化再在Linux执行`uv sync --locked --extra worker`。同步器排除.env、.planning、work、.venv与符号链接；客户资料/密钥不得进入Git源文件。

首次配置步骤（已有环境不重复初始化）：

1. Windows执行`wsl --install -d Ubuntu-24.04 --name OneFDE --location D:\WSL\OneFDE --version 2 --vhd-size 50GB --no-launch --web-download`。
2. 仅在全新发行版以root运行`bootstrap.sh`，安装Ubuntu签名仓库Docker包、uv0.12.5并创建onefde用户。脚本设置本发行版wsl.conf；不影响其他发行版。下载不通时使用官方PyPI同版Linux wheel并核对SHA256，以`ONEFDE_UV_WHEEL`指定本地路径。
3. root创建并归属onefde的`/home/onefde/OneFDE`后同步源码；以onefde执行`uv python install 3.13.5`、`uv sync --locked --extra worker`、`uv run --locked python local-wsl/configure.py`。配置脚本遇已有文件拒绝覆盖；失败后核查现场，不删除卷重新生成凭据。
4. root安装并运行`offline-network.sh`，作为随本发行版Docker启动的`onefde-offline-network.service`；仅重启`OneFDE`，检查规则及挂载恢复，不执行全局`wsl --shutdown`。
5. 拉取仓库固定摘要的Agent Server镜像，运行上面的环境检查；安装版本及实际结果见[C2记录](../../docs/operations/c2-verification.md)。

## 资源、网络与DeepSeek后续接入

数据库0.5 CPU/384MiB/128 PID；工程容器1 CPU/2GiB/256 PID；Worker15分钟/最多20次SDK迭代。WSL全局内存设置会影响现有Docker Desktop，本轮不改；运行前释放不需要的应用占用。

当前`onefde-engineering-offline`是internal网络；`ofde-eng0`的INPUT规则拒绝工程容器到宿主的新连接，仅允许宿主发起连接的回复。控制数据库使用其他网络。实际SDK检查核对挂载/凭据排除/回环端口、文件/Session写入、网络拒绝、停止和不可变归档。WSL与个人宿主共享基础设施，这不是客户隔离或生产安全验收。

DeepSeek稍后准备非秘密provider/base_url/model/secret_ref，在本地注入模型密钥，并确认费用上限/提供方额度。先配置模型白名单出口并验证控制库/宿主仍拒绝，最后启用`model_execution_enabled`。当前不运行`import-profile`或`once/run`；不把离线网直接替换成无限制bridge。

停止数据库使用`docker compose --env-file .env -f local-wsl/compose.yaml stop`；不加`-v`，不删除发行版。Task/Run与评审语义保持现有协议。

## 后续单机Compose项目

用户随后授权S1/S2，已在同一发行版增加独立onefde-local项目；API/PG/Worker与离线代理容器化、硬磁盘总边界及安全/资源检查见[Compose手册](../../deploy/README.md)。本文件仍描述旧宿主进程开发环境与onefde-wsl数据库，不代表新Compose的运行方式；两套数据分别保留。模型关闭，完整C2仍未验收。
