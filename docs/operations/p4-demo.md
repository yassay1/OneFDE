# P4 本地演示复现

触发：准备黑客松演示、重跑报价产品入口，或核对 HM08/HM09。云上线和演示录像不在本文件。一条薄工作台路径的启动和点通记录见第 4 节。状态以[实施计划](../development/implementation-plan.md)为准。

完成标准：`python deploy/verify_product_origin.py` 退出 0，且证据 `ok` 为 true。产品 Origin 是 `http://127.0.0.1:8765`。工作台 Origin 仍是开发 API `http://127.0.0.1:8000` 与 Compose API `http://127.0.0.1:8002`。

## 1. 产品 Origin

在仓库根执行：

```powershell
python deploy/verify_product_origin.py
```

脚本只绑定 `127.0.0.1:8765`，提供 `products/demo-supplier-quotes`，并运行 `node check.mjs`。通过时同时满足：

- 首页脚本为 `./compare.js`、`./app.js` 与 `./business.js`
- 产品 Origin 对 `/health` 和 `/api/v1/...` 返回 404，且不设置 Cookie
- 报价页只跨 Origin 调用客户 Business 接口，产品静态文件仍由独立 Origin 提供
- S01/S02/S03/S05 检查退出 0

证据写入 [p4-product-origin.json](evidence/p4-product-origin.json)。需要保持页面可打开时另开 `python deploy/verify_product_origin.py --serve`，浏览器只打开 `http://127.0.0.1:8765/`。

2026-11-05 实测：检查退出 0。当时 `8000` 与 `8002` 未监听，证据里的 `workbench_probes.running` 为 false；这只说明工作台进程没开，不能当成一次在线 API 对照。浏览器在 `http://127.0.0.1:8765` 导入 S01 后显示「可比较 2 行 · 待核对 0 行 · 同口径单家 0 行」；同 Origin 的 `/api/v1/engagements` 为 404。

## 2. 平台主链

产品页不登录工作台。控制链与复用沿用已有检查，在 `backend` 执行：

```powershell
uv run --locked pytest tests/integration/test_fde_tools.py tests/integration/test_p2_quote_fde_delivery.py tests/integration/test_knowledge_tools.py -q
```

需要独立 PostgreSQL 测试库。本轮没有重跑这三项。已有证据：

| 环节 | 证据 | 限制 |
| --- | --- | --- |
| FDE 工具与交付详情 | `backend/tests/integration/test_fde_tools.py` | 无 FDE 模型循环；三入口页面未做 |
| 报价控制链 | [p2-quote-control.json](evidence/p2-quote-control.json) | 确定性 Run 回填，不是 OpenHands |
| 样例结果 | [p2-quote-product-check.json](evidence/p2-quote-product-check.json) | 与本节 Origin 检查重复覆盖 S01—S05 |
| 第二项目复用 | [p3-reuse-recheck.json](evidence/p3-reuse-recheck.json) | 无 Knowledge 模型循环 |

交付详情 API 只返回项目、未知项、Task/Run 摘要和版本提示，不返回产品 HTML。

## 3. 讲解顺序与备用记录

按[黑客松实施方案](../product/hackathon-proposal.md)的三分钟顺序讲。现场打不开产品时，改用上表 JSON 和产品目录里的 v1.1 源码，并说明是历史检查结果。

网页冒烟 Task `a2d797a5-ed37-4403-8645-46b26074b125`、Run `523cad22-acfd-40e7-9f84-9c739e34afe1` 只证明一次无关的真实网页工程，不能当作本报价案例的模型 Run。报价案例尚未用真实 Engineering 替换确定性回填。

## 4. 薄工作台路径

在 `frontend` 构建后，从 `backend` 启动 API。页面和接口共用 `ONEFDE_TRUSTED_ORIGIN`。当前开发值是 `http://localhost:8000`；不要改用 `http://127.0.0.1:8000` 登录。报价产品仍用上一节的 `--serve`。

2026年11月5日浏览器点通：登录后打开模拟项目 `651dc06f-e29d-49c8-8be0-da242bb65799`，任务 `9bb8c6ff-74b3-436e-9184-58ae3756f0f2` 显示待评审，Run `f40cc92e-738d-48ab-afdf-eb3796277679` 的检查结果和产物「报价对照表」来自接口。接受返回 201，页面变为已接受。工作台保持在 `localhost:8000`，报价页在新标签 `http://127.0.0.1:8765/` 打开，标题为「模拟水果店报价比较」。该 Run 是确定性登记，不是模型报价。交接和能力入口没有页面。

## 仍未做

演示录像、公网 HTTPS、能力入口、S04 换算规则、用真实模型重跑报价 Task。Business 会话交接的最新步骤见 [Business 本地验收](business-v1.md)。
