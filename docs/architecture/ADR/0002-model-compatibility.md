# 通过配置和能力适配接入模型 API

状态为纳入推荐技术基线，具体模型未配置、尚未接入。日期为 2026 年 11 月 3 日。

## 背景

用户尚未选定模型，期望 API 兼容；不应因产品定义中出现 MiMo 就把平台锁定到特定型号。兼容请求格式并不证明连续工具调用、恢复或工程质量相同。

## 推荐

以 ModelProfile 配置协议、地址、模型、secretRef、能力及限额，首轮优先兼容 Chat Completions 必要子集。Run 固定配置修订；SDK 自带适配可满足时先直接使用，不额外建设独立 LLM 网关。

## 比较与代价

固定厂商最容易开始但迁移成本高；首轮统一所有协议会扩大适配工作。配置加能力标记允许逐个验证，不宣称通用无差别兼容。提供者要求的协议扩展仍需保存和正确重放。

## 验证与依据

接入时复用上游示例完成一次连续工具调用小任务；不将普通文本、流式参数、schema、恢复等逐项重建成独立前置测试项目。仅在具体不兼容或自定义适配出现时追加对应检查。OpenHands 提供 base_url 与模型等配置；MiMo 官方示例同时展示兼容端点与差异字段。[OpenHands LLM](https://docs.openhands.dev/sdk/api-reference/openhands.sdk.llm)、[MiMo 官方示例](https://github.com/XiaomiMiMo/awesome-mimo-agent/blob/main/docs/oh-my-pi.md)

当实际需要第二种协议、多个应用的集中配额或密钥管理时重访网关方案。具体接入能力清单见[架构](../architecture.md)。
