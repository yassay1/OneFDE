# demo-supplier-quotes 变更

## v1.0 — 首版可比较交付

- 浏览器导入 P0 八列 CSV，按 R01—R05 / P0 可比条件分组比较。
- `unit!=kg` 或非 CNY → 待核对；同口径仅一家 → 不可合并跨组最低价。
- 导出全部结果 CSV（含 status/reason）。
- 确定性检查：`node check.mjs` 覆盖 S01/S02/S03/S05。

## v1.1 — 同 Task 范围内修改

修改意见：待核对项不能只混在总表里，需要单独导出以便老板催供应商补净重。

- 新增「导出待核对 CSV」；仅包含 `status=pending` 行。
- 不改变比较规则与 S01—S05 预期。
- 检查脚本增加对待核对导出列的断言。

## CSV 售后修复（人工归档已验收）

- `unit_price` 表头可带边缘 ASCII 空格。缺列和归一后重名仍报错。
- 原样例、专项回归和独立回环内部复测通过。 [验收记录](../../docs/operations/testing.md#报价自动售后验收)
