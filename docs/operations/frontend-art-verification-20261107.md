# Web 工作台美术与回归验收（2026-11-07）

范围：用户授权的 `frontend/` 浏览器 SPA 小完善。需求来源为本轮素材映射、[前端设计](../frontend/design.md)、[前端验收矩阵](../frontend/implementation.md)及 [PRD](../product/PRD.md) P02/P07/P10。仅修改前端与相关文档，未新增 API、依赖、模型调用、Task/Run 或业务数据。

## 已安装素材

源目录：`D:\proj\one-picture\`。以 Pillow Lanczos 等比缩放副本到宽 1400px，保留原图与全部画面；不强制裁成 1400×420。

| 源文件 | 安装目标（仓库根目录起） | 尺寸 |
| --- | --- | --- |
| 黄昏时分的温暖办公时光.png | `frontend/public/business-hero-scene.png` | 1400×467 |
| 萌猫办公方案设计_scene.png | `frontend/public/fde-hero-scene.png` | 1400×467 |
| 霓虹代码中的熊猫程序员.png | `frontend/public/engineering-hero-scene.png` | 1400×560 |
| 温暖书房里的猫头鹰学者.png | `frontend/public/knowledge-hero-scene.png` | 1400×560 |

四头像与 `office-scene.png` 沿用现有版本。角色场景框采用 `object-position: left center`，头像由居中 96px 改为右下 64px。1600/1280 下可见角色头部、耳机/眼镜及桌面，头像不遮挡场景主体。正常加载不再显示待替换框；实际图片失败才显示「场景暂不可用」。

## 修复与构建

- 会话 401：清理私有缓存时保留正在结束的 session 查询，使错误状态能正常进入登录页；已实际观察修复前卡住、修复后显示登录并成功登录。凭据未写入证据。
- 项目详情/Business Case：UUID 校验后再启用查询，无效路径提示返回列表；项目详情的 Case/Task 参数同样过滤。
- 导航：侧栏从项目详情路径提取项目 ID，Business/FDE/Engineering/Knowledge 切换保留项目；三个角色页头 Knowledge 入口也保留项目。FDE 改项目时清除原 Case/Work。
- Engineering：指定 Task 不属于项目时不回退其他任务；确认 Task 和已读取 Run 列表后才读取指定轮次，无法确认的 Run 保持只读并可返回当前。轮次列表仍遵循现有 50 条上限，超出已读取范围的历史 Run 提示核对。
- Engineering：将状态条「固定检查完成」改为「提交证据」，不从 submitted/succeeded 推断检查通过；实际证据缺失继续诚实说明。
- Knowledge：关键词草稿随 URL `q` 更新，前进后退时输入与结果一致。

最终命令在 `frontend` 执行 `npm run build`，退出 **0**：TypeScript 检查与 Vite 构建通过。产物为 `index-Bccrm7MC.js`（905.88 kB / gzip 286.61 kB）、`index-6_VVVYCr.css`（45.90 kB）。Vite 保留大于 500 kB 的 chunk 体积提示，本轮未扩大为拆包重构。

## 浏览器实测

Origin：`http://localhost:8000`，Edge，已有 Windows 开发库。按后端 README 启动本地 API；只使用现有开发数据和 manifest 检索，没有提交工程/模型命令。详细 DOM、图片 natural size、URL 和页面宽度保存在 [checks.json](evidence/frontend-art-20261107/checks.json)。

| 场景 | 实际结果 |
| --- | --- |
| 五页 1600×900 / 1280×800 | 四张新图和头像 naturalWidth 均大于 0，无待替换框；页面 scrollWidth 不超过视口宽度；Office 原场景/气泡/待办与动态可读 |
| 项目 → Business → FDE → Engineering → Knowledge | 保留项目 `651dc06f-e29d-49c8-8be0-da242bb65799`；Business 仍为全局收件箱，不伪装为项目过滤 |
| FDE 页头 → Knowledge → 返回原工作 | 返回相同项目 FDE，未登记 Work |
| Engineering 刷新 | 恢复 Task `9bb8c6ff-74b3-436e-9184-58ae3756f0f2`、已有 Run 与已接受状态；未修改任务 |
| Knowledge 报价检索/详情/刷新/前进后退 | 真实查询 `fresh-quote-compare-csv@1.1.0`；详情和 URL 恢复；退到未查询状态时关键词清空，前进恢复「报价」 |
| 非法 UUID | `projects/not-a-uuid`、`business/not-a-uuid` 提示返回列表；FDE/Engineering 的非法 project/case/work/task/run 参数清理；无 `VALIDATION_ERROR` |
| 有效 UUID、错误对象关联 | 不在项目中的 Task 不自动替换；未在当前 Task 轮次列表的 Run 显示核对提示，运行命令只读，返回当前恢复 |
| 固定证据为空 | 当前开发样例 Run `f40cc92e-738d-48ab-afdf-eb3796277679` 的证据面板显示「本轮暂无固定证据」，不补造 Diff/检查结果 |

截图：

| 页面 | 1600 | 1280 |
| --- | --- | --- |
| Office | [首屏](evidence/frontend-art-20261107/office-1600.jpg) | [首屏](evidence/frontend-art-20261107/office-1280.jpg) |
| Business | [首屏](evidence/frontend-art-20261107/business-1600.jpg) | [首屏](evidence/frontend-art-20261107/business-1280.jpg) |
| FDE | [项目工作区](evidence/frontend-art-20261107/fde-project-1600.jpg) | [项目工作区](evidence/frontend-art-20261107/fde-project-1280.jpg) |
| Engineering | [场景](evidence/frontend-art-20261107/engineering-1600.jpg) | [最终工作区](evidence/frontend-art-20261107/engineering-task-1280.jpg) |
| Knowledge | [首屏](evidence/frontend-art-20261107/knowledge-1600.jpg) | [真实检索](evidence/frontend-art-20261107/knowledge-1280.jpg) |

## 验收边界

本轮目标通过，等待用户验收。当前开发库 Business Case 为空，因此验证了空态与非法深链，未验证含真实会话的写路径；固定证据为空不等于工程验收通过。未调用模型、启动 Worker、部署公网或改变业务生命周期。现有大 chunk 提示保留。四张英雄场景均已安装，没有待生成项。
