# 第二模拟项目：报价比较资产复用

项目 ID 为 `demo-supplier-quotes-reuse`。资料类型为**模拟**。用于黑客松 P3：检索并采用首案例固定资产，重新跑样例检查。

## 目标

在新项目中复用 `fresh-quote-compare-csv@1.1.0`，验证「不是粘贴上轮聊天，而是固定版本 + 再检查」。

## 采用记录

| 项 | 值 |
| --- | --- |
| 检索工具 | `POST /api/v1/knowledge/tools` → `search_assets` / `get_asset` |
| 采用资产 | `fresh-quote-compare-csv` 版本 `1.1.0` |
| 实现引用 | `products/demo-supplier-quotes@v1.1` |
| 适配 | 本项目未改比较规则；直接复用产品与 P0 样例路径 |
| 重新检查 | `node products/demo-supplier-quotes/check.mjs`（见证据） |
| 不适用扩展 | 不做 S04 换算；不提升为公开案例 |

## 边界

- 来源首项目 `demo-supplier-quotes`；模拟标记保留。
- 受限夹具 `fixture-restricted-supplier-notes` **不得**被本项目或公开展示用途读取。
- Business 交接不派发工程；本记录由 FDE/Engineering 复用检查驱动。
