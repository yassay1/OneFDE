# 果采报价台

2026-11-07 已接受筛选修复：载入示例清除旧搜索/状态条件，新增「清空筛选」按钮，保留当前 CSV、来源和价格精度。经 MiMo Coding Agent 通过 OneFDE 实现，五项技能实际调用及独立 Playwright 检查见[测试记录](../../docs/operations/testing.md#playwright-与-mimo-技能实测2026-11-07)。

本地入口：http://127.0.0.1:8774/ 。导入 UTF-8 CSV 或粘贴八列报价，点击「比较报价」，可搜索、筛选和下载结果。页面提供 CSV 模板与明确标注的虚构示例。

仅比较商品、等级、规格相同的 kg / CNY 报价。箱价、缺信息和无效价格待核对，不同等级不合并。全部输入行保留；未计运费、起订量、送货条件，采购由人决定。数据处理在浏览器本地完成。

本版本通过 OneFDE 工作台提交目标，由 MiMo FDE 查询能力库、创建 Task 和派发 MiMo Engineering。页面集成由 Engineering 生成，复用既有 CSV 比价核心。经历受控重试和人工恢复后通过独立验证及浏览器验收，已正式接受；不代表无人干预首跑成功或公网部署。

本机服务停止后，在仓库根目录启动：

```powershell
python -m http.server 8774 --bind 127.0.0.1 --directory products/mimo-fruit-quotes
```

完整记录见[测试事实](../../docs/operations/testing.md)与[脱敏证据](../../docs/operations/evidence/mimo-fruit-quotes-20261107.json)。
