# 临期商品清单 CSV

`expiry-inventory-csv@1.0.0`，业务模块。仅供已授权的内部项目在列明条件下复用。

采用 UTF-8 的四列库存 CSV 和基准日。每个批次显示分类及源行号。导出过期、今日和未来 1 至 3 天的批次。浏览器本地处理，Node 运行固定回归。

使用前确认日期无首尾空格，年份至少为 0100，输入为可信模拟数据。日期边界和 CSV 公式形文本的限制见验收记录。采用时核对 manifest 中的归档摘要并用本项目样例重检。

- 来源 [模拟门店 Engagement](../../engagements/demo-expiry-inventory/brief.md)。
- 实现 [临期清单源码](../../products/demo-expiry-inventory/index.html) 与 [固定回归](../../products/demo-expiry-inventory/check.mjs)。
- 验证范围为首店跨月和第二家模拟门店跨年样例。采纳、固定版本、内部用途过滤和浏览器结果见[验收证据](../../docs/operations/evidence/onefde-expiry-chain-20261105.json)。
