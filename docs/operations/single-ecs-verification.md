# 单ECS一体化：实施阶段与验收

2026年11月4日，用户已授权先执行本地S1/S2；本地Compose、真实SDK无模型隔离/资源检查已落地，下方逐项区分证据范围。购买云资源、真实模型费用与公网发布未获本轮授权。拓扑和预算以[部署设计](deployment.md)为准，操作见[Compose手册](../../deploy/README.md)，角色/Task语义沿用[数据模型](../architecture/data-model.md)。

## 实施顺序

| 阶段 | 范围 | 退出条件与证据 | 当前状态 |
| --- | --- | --- | --- |
| S0 设计审阅 | 调研、单机服务边界、资源估算及差距 | 架构图、服务表、执行/发布链路、验收与文档一致；用户确认后才能改代码/部署 | 用户已确认先实施S1/S2，云端后置 |
| S1 本地Compose对齐 | 锁定应用镜像与独立API/PG/Worker，明确ecs_shared配置与宿主路径映射 | 新隔离演示项目验证持久化、健康/重启及非公开端口；原Windows/WSL开发数据保留 | 本地完成；生产构建/网关未做 |
| S2 无模型安全与资源 | 创建时限额、安全选项、私有桥HTTP/认证、出口代理、磁盘硬边界/日志/准入 | 本地E01—E04实测；E05/E06按下方真实控制/SDK与回归证据验证。模型关闭不消费任务；生产剩余门槛保留 | 本地验证完成；不等于云端安全/容量验收或真实模型闭环 |
| S3 C2真实工程与最薄角色适配 | 用户本地配置模型/预算后先跑简单网页及检查脚本；再逐个接FDE/Business/Knowledge受控工具 | 原Task/Run真实文件/命令/产物/评审闭环，角色请求身份/权限/预算可查；尚无其他角色实现时明确报告，不把容器数量当Agent能力 | 工程契约/固定验证无模型子集已完成，见[CA验证](coding-agent-verification.md)；真实模型与角色工具未执行 |
| S4 工作台与产品可部署版本 | 前端按单独确认设计实施；公司网站内容另定；报价规则确认后本地开发、构建和评审客户产品 | 工作台登录/Task反馈；角色最小可用链路；客户软件样例检查与版本可追溯，仍不算公网交付 | 未执行 |
| S5 阿里云购买与基础部署 | 确认地域、规格、预算、域名、维护/备份位置和上线要求；另获购买/部署授权后才开机 | 单台ECS的核心Compose启动、TLS/认证、网络/磁盘/内存/备份恢复实测；工程不要求第二台ECS | 未执行，未购买 |
| S6 同机产品交付与回退 | 受控发布已接受版本，隔离产品数据/服务 | E08—E11通过，实际客户网络访问，停止Worker/Sandbox后产品可用；记录部署/访问及维护期限 | 未执行 |

S1—S4在本地完成能力验证即可，不强制先购买ECS。可按切片先部署已有能力，但“完整OneFDE一体化MVP”验收必须明确网站、工作台及四角色实际完成范围；缺失部分继续标为未完成。S3首个真实工程先使用无业务歧义的小网页，不提前开发报价或扩大C2范围。

## 核心验收矩阵（目标；实际范围见下方）

| 编号 | 具体操作 | 必须观察到的结果/证据 |
| --- | --- | --- |
| E01 Worker容器接线 | bridge Worker通过Docker创建同宿主Sandbox，读写Task/Run指定挂载；用单Run key访问8000，错误key再访问 | 宿主/Worker同绝对路径对应同一文件；正确认证成功、错误认证拒绝；无需host网络/公开Agent端口；记录实际容器ID/镜像/路径映射，证据不含key |
| E02 权限与文件边界 | 从工程终端检查Socket/secret/PG/其他Task/发布根；尝试sudo、setuid提权与越界写入 | Socket/凭据不可读、越界写入拒绝，NNP/cap/seccomp生效，固定用户与700目录匹配；兼容性失败不得以privileged放行 |
| E03 在线网络 | 允许模型/批准依赖；实际连接控制库、产品后端、宿主上已验证可达的测试端口、100.100.100.200、任意公网IP/未授权域名及IPv6 | 白名单路径成功，所有绕过和横向连接拒绝；验证Worker能连接Agent Server而Agent不能新连Worker；不能仅用目标没有监听来证明过滤 |
| E04 资源 | 在受控测试额度内触发CPU/内存/PID/磁盘配额，观测动态容器及宿主 | 创建瞬间已有限额；该Run失败/阻塞有证据，API/PG仍可用；磁盘硬配额实际拒绝超额写入，不把du轮询当硬限制；未实现时仅可继续本地小演示，不能据此通过云端验收 |
| E05 准入与停止 | 模拟低磁盘/内存拒绝，新Run与interrupted并发启动；请求cancel/stop_for_update、心跳失联 | 只1个工程活动Run；不足不创建资源；未知现场继续占槽；Docker确认停止后才释放；冻结/回执与恢复核查可追溯 |
| E06 生命周期 | Worker/Sandbox/核心Compose分别重启；同代次回填重放与异结果冲突；恢复已提交数据 | 不重复执行副作用、不自动重跑未知Run；PG/Task/Run/产物摘要保持，Session有持久文件但不假称已支持自动会话恢复 |
| E07 模型与费用 | 含真实工具往返的C2网页任务，统计模型请求、迭代、费用与停止延迟，审查配置快照 | 命令与退出码、源码/构建Artifact、Task/Run/评审固定关联；未超授权预算；不能仅凭SDK迭代上限声称提供方硬封顶 |
| E08 发布与访问 | 相同产物重复发布、访问公司站/工作台/产品及错误产品路径；用约定设备/网络检查 | 发布幂等/固定版本与期限，HTTPS有效；工作台未登录拒绝；客户不取得内部权限或其他客户数据；前端无secret |
| E09 交付独立性与回退 | 停止Worker及所有工程容器；从新版切回上一可用产品 | 产品继续服务，回退实测；故障版本与检查记录保留；数据库迁移另按恢复方案处理 |
| E10 备份恢复 | PG逻辑导出/角色与产物清单形成异机副本，在独立测试库/恢复目录还原并读回 | Task/Run/固定版本/产物SHA可关联，密钥独立加密保存；无异机副本不能称灾难恢复完成；不破坏现有开发/生产数据 |
| E11 资源压测与运营 | 一个最大预算工程Run+约定客户产品样例负载，观测API/PG/内存/CPU/磁盘和队列 | 记录实测峰值与容量边界、告警/准入行为；根据结果调预算。未提供真实负载前不宣称可承载固定客户数或SLA |

E07在模型授权后执行；其余无模型检查不调用模型。E03的真实模型验证与依赖下载要分别记录。E04不得在已有生产数据上无控制制造全盘满或宿主OOM。

## 交付记录

每阶段保留日期、需求/配置版本、镜像摘要、实际命令/返回、Task/Run/Artifact与访问结果。原始凭据、Cookie、Session内容和客户资料不进入公开证据；客户交付归对应Engagement。

本设计关联P05/P06/P07/P08及V06/V07/V08，不修改业务规则。旧100项测试/WSL记录不倒写为本轮验收；本轮单机实测单列如下。真实模型工程仍见[C2记录](c2-verification.md)。

## S1/S2本地执行记录

独立项目`onefde-local`，API仅127.0.0.1:8002；PG无宿主端口；可信Worker在bridge容器中通过宿主Socket创建同宿主Sandbox。应用/固定基础镜像、实际命令与资源详情见[操作手册](../../deploy/README.md)及以下脱敏证据。本轮未创建Agent/LLM进行推理，也未接受业务成果。

| 条件 | 本轮实际结果 | 范围限制 |
| --- | --- | --- |
| E01 | 真实固定SDK、Worker→私网Agent Server成功，错误key拒绝；同绝对路径workspace/session真实读写，无Agent宿主端口 | 环境UUID目录验证；未把这次环境容器冒充业务Run |
| E02 | UID10001、根只读、无Socket/管理secret/其他Task根、sudo拒绝；NNP/CapEff0/seccomp过滤有效；创建时限额/挂载inspect通过 | Docker共享内核，可信Worker管理权仍等同宿主；不是任意多租户强隔离认证 |
| E03 | 已确认监听的Worker/宿主端口被Sandbox拒绝；控制PG、两类元数据、公网IP/IPv6拒绝；离线CONNECT fixture成功，其他域名/元数据代理403 | fixture非模型/真实TLS；实际模型、依赖出口与产品后端尚未部署，保持未验证 |
| E04 | SDK真实写满独立2GiB数据盘得到ENOSPC并清除探测文件；另以64MiB/32PID/0.1CPU受限容器触发OOM137、EAGAIN与CPU节流，核心API/PG仍可用 | 本地为Worker整体硬容量，不是生产每Task/Session配额；未实现工程总slice、云端inode/缓存上限或真实业务负载压测 |
| E05 | 真实容量阈值拒绝前不认领；HTTP跨Task并发409；standby下pending作业attempts=0后HTTP取消；原停止/失联/interrupted占槽测试通过，SDK停止由Docker独立核实 | 取消/失联控制分支使用明确测试适配；真实模型执行中的端到端取消/停止延迟留E07 |
| E06 | Sandbox重启保留workspace/session文件；核心Compose重启保留Task/Run和产物摘要；仅OneFDE WSL重启检查挂载、服务和网络规则恢复；回填重放/冲突既有回归通过 | Session仅文件持久化，未实现Conversation自动恢复；不证明任意外部副作用恰好一次 |
| E07—E11 | 未执行，C2真实模型网页任务/费用、客户交付/HTTPS/回退、异机备份与业务压测未完成 | 未购买ECS、未部署公网、没有真实Engineering提交或评审 |

资源不足时只拒绝新认领，未知Run继续占槽；不以租约过期自动重执行。本地模型开关false、费用未设置：环境预检应0，执行预检应2。控制探测使用明确OFFLINE fixture元数据（不可调用的.invalid端点、无密钥），创建的Run始终未认领并取消，不是模型配置就绪。

证据与实际命令见本轮新增的环境、资源、控制、重启JSON及JUnit；归档为环境文件而非业务Artifact，私有内容仍在Linux持久盘。运行时失败发现并修复：internal网不发布API端口、静态/自动IP重启冲突、捆绑Agent Server在/tmp解包所需exec映射；验证脚本的实际列名与logout Content-Type已校正。未通过的轮次没有计为成功。

| 实际命令（Linux仓库根，uv检查从backend） | 脱敏证据与结果 |
| --- | --- |
| `docker compose --env-file /srv/onefde-local/private/compose.env -f deploy/compose.yaml build worker`；PG启动后分别运行`--profile ops run --rm migrate`、`initialize` | [执行清单/镜像ID/配置SHA](evidence/single-machine-execution.json)；锁定离线构建、迁移head d5454eda0523与受限角色成功 |
| `backend/.venv/bin/python deploy/verify_local.py` | [SDK环境](evidence/single-machine-environment.json)：9组通过、错误key401、真实命令退出0、ENOSPC28；[资源](evidence/single-machine-resources.json)：CPU49周期中48次节流、内存OOM137、PID30个子进程后EAGAIN11；SDK/磁盘期间55次核心健康检查通过。发行版重启后重跑通过 |
| `backend/.venv/bin/python deploy/verify_control.py` | [HTTP控制](evidence/single-machine-control.json)：4组通过；两个DEMO Task保留，Run `24aaa137-728b-409f-ace2-71015cd63a15` 未认领且cancelled；无Engineering结果 |
| Windows `wsl --terminate OneFDE`，重新开启发行版；root核验自有iptables链；`backend/.venv/bin/python deploy/verify_recovery.py` | [恢复及预检](evidence/single-machine-recovery.json)：挂载/规则自动恢复、旧/新PG与API/Worker健康、原Task/Run及归档摘要保持；环境退出0，完整执行退出2（模型/费用缺失） |
| `uv run --locked --extra worker pytest -q --junitxml=work/shared-tests.xml` | [JUnit](evidence/single-machine-tests.xml)：106 passed、0 skipped、20.01秒；1条既有Starlette弃用警告 |
| `uv run --locked --extra worker ruff check src tests scripts migrations ../deploy`、`ruff format --check`；`python -m scripts.export_openapi --check`；`alembic check`；`uv build --out-dir work/shared-dist` | 全部通过；103个Python文件格式有效、三份HTTP契约不变、数据库无漂移、sdist/wheel实际生成 |

重启后最终环境归档SHA256：`a8180247faeb56bf5270f02dbd8f11a7b8d7eccbb26d257198d96c2136774630`，2184字节/7文件；路径仅为私有环境归档，不是已评审客户产物版本。Windows实际访问本地API health得到200/`ok`。结束后无Sandbox/资源探测容器，probe已停止；可信Worker继续standby，模型关闭。
