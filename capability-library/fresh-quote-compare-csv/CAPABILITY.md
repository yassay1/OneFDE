# fresh-quote-compare-csv

| 字段 | 值 |
| --- | --- |
| ID | `fresh-quote-compare-csv` |
| 名称 | 生鲜报价 CSV 同口径比较 |
| 类型 | 业务模块 |
| 版本 | 1.1.0 |
| 更新 | 2026-11-04 |
| 验证状态 | **限制使用**（仅 S01/S02/S03/S05 与 P0 字段） |
| 可见性 | 内部跨项目可复用；**不可**作公开展示原文 |
| 来源 Engagement | `demo-supplier-quotes` |

## 解决什么问题

在模拟水果店场景下，导入约定 CSV，对同商品/等级/规格且 `unit=kg` 的报价做单位价比较，缺净重或非 kg 标记待核对；不计算运费/起订量/送货，不自动采购。

## 适用与限制

- 适用：P0 八列 CSV；R01—R05；浏览器静态产品或同等确定性逻辑。
- 不适用：未确认换算表、Excel 主路径、自动定标、真实客户收益证明。
- 复用后必须重新跑样例检查；不得把本条目标成「任意报价场景已验证」。

## 实现与证据

- 实现：`products/demo-supplier-quotes`（v1.1，含待核对单独导出）
- 产品检查：`docs/operations/evidence/p2-quote-product-check.json`
- 平台控制链：`docs/operations/evidence/p2-quote-control.json`（确定性 Run 回填，非模型）

## 权限

- `delivery` / `internal_research`：三角色可检索本条目元数据与正文。
- `public_marketing`：只允许返回 `public_summary`，不返回实现路径或内部证据链接。
