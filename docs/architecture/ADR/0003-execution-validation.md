# 采用隔离容器工程工作区

状态为纳入推荐技术基线，未接入、未开通服务。日期为 2026 年 11 月 3 日。

## 背景

首版需要真实文件、命令、构建与部署。用户没有指定云厂商或预算，授权提出推荐。模型生成代码不应默认在存放个人资料和平台凭据的宿主直接运行。

## 推荐

采用 OpenHands SDK 与 DockerWorkspace，可信 Worker 位于专用 Linux 执行节点，使用固定版本的 Agent Server 镜像；控制数据、管理进程凭据和生成代码容器分开。生成软件的托管与工程环境生命周期分离，先一个有界 Worker 串行运行。

## 比较与代价

原生组合减少自行开发工具循环与工作区适配，但需配置宿主、容器权限、网络及持久产物。E2B 或托管工作区能减少部分运维，但需额外验证账号、地区、成本及适配，不默认两套同时接入。自研 Harness 或直接开放宿主文件系统均不优先。

## 验证与重访

先落实可用执行宿主与配额，复用官方示例做一次接入冒烟；自有取消、状态归属和基本恢复随开发检查，不再先开发通用验证平台。若运维投入明显超出 MVP 收益，比较 OpenHands Cloud Workspace 与 E2B 替代；没有运行证据前不将组合标为已可用。

参考 [DockerWorkspace 官方说明](https://docs.openhands.dev/sdk/guides/agent-server/docker-sandbox)、[Docker 安全边界](https://docs.docker.com/engine/security/)、[E2B 生命周期](https://docs.e2b.dev/sandbox)。部署选择与其他限制见[架构](../architecture.md)。
