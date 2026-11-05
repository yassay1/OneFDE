# 模拟水果店报价比较（客户产品）

独立静态产品，**不要**挂在 OneFDE 工作台认证 Origin 下执行。本地可用任意静态服务器在单独端口打开本目录。

## 范围

- 输入：P0 八列 CSV（见 [engagement 样例](../../engagements/demo-supplier-quotes/samples/)）。
- 规则：R01—R05；仅 `unit=kg` 且同 product/grade/spec 比较；待核对不静默丢弃；不自动采购。
- Excel / 换算表 / 重复行语义：未确认，本产品不做。

## 运行

```powershell
python deploy/verify_product_origin.py
python deploy/verify_product_origin.py --serve
# 浏览器只打开 http://127.0.0.1:8765/
```

检查同时覆盖 Origin 边界和 `node check.mjs`。证据与复现步骤见[P4 演示](../../docs/operations/p4-demo.md)。

## 检查

```powershell
node check.mjs
# 或 bash check.sh
```

当前版本见 [CHANGELOG.md](CHANGELOG.md)：v1.0 首版比较；v1.1 同范围修改「待核对单独导出」。

## 与平台交付的关系

本目录是可操作客户产物与确定性检查。平台 FDE 控制链（建 Task、采用修改、两次提交/评审）由 `backend/tests/integration/test_p2_quote_fde_delivery.py` 验证，证据见 [p2-quote-control.json](../../docs/operations/evidence/p2-quote-control.json)。该路径使用确定性 Run 回填，**不是** OpenHands/模型工程；获授权后再替换为真实 Engineering Run。
