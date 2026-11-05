# P0 模拟报价 CSV 样例

资料类型：**模拟演示**。金额与供应商均为虚构，仅用于检查比较逻辑与待核对行为。不是真实客户报价，不能用于宣称经营收益。

权威规则见上级 [brief.md](../brief.md) 的 R01—R05 与 P0 字段约定。本目录文件是输入；预期结果以 brief 中「P0 固定预期」为准。

| 文件 | 对应场景 | 用途 |
| --- | --- | --- |
| [s01-same-basis.csv](s01-same-basis.csv) | S01 同口径 | 两家可比较；B 单位价更低 |
| [s02-missing-net-weight.csv](s02-missing-net-weight.csv) | S02 缺净重 | 全部待核对；不按盒价选最低 |
| [s03-different-grade.csv](s03-different-grade.csv) | S03 等级不同 | 不合并为单一最低价 |
| [s05-mixed.csv](s05-mixed.csv) | S05 混合 | 可比较与待核对/不可比同时呈现 |

编码为 UTF-8；首行为表头；字段顺序固定。S04 换算样例在换算表确认前不提供。
