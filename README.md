# Google 广告分析优化工作台

面向 INTCO 系 Google Ads MCC（5 个广告账户）的日常运营分析工作台。

## 数据来源与刷新

内置数据由 `refresh_real_data.py` 从 Google Ads API 直接拉取，覆盖 MCC 下全部 5 个
ENABLED 账户、近 400 天、campaign × date × device 粒度：

| 账户 ID | Google Ads 账户名 |
| --- | --- |
| 206-869-2080 | BasicMedical_EN_20251229 |
| 446-941-0060 | Intco_Gloves_EN_20240222 |
| 852-988-1574 | Intco_Medical_EN_20251031 |
| 432-584-4223 | Intco_Wheelchair_EN_20240123 |
| 692-149-5146 | Intco_Healthcare_EN_20240222 |

关键词 / 搜索词 / 广告 / 落地页 / 转化动作 由 `refresh_detail_data.py` 单独拉取（`REAL_DETAIL`），
覆盖近 120 天、按花费取 Top N（关键词 60 / 搜索词 60 / 广告 30 / 落地页 30 / 转化动作 12）：

| 模块 | 数据源 | 口径 |
| --- | --- | --- |
| 关键词 | `keyword_view` | 真实匹配类型、展示 / 点击 / 花费 / 转化 |
| 搜索词 | `search_term_view` | 意图分类沿用原有规则，指标全部真实 |
| 广告与素材 | `ad_group_ad` | 广告名取 RSA 最长标题，素材由真实广告派生 |
| 落地页 | `landing_page_view` | 展示 / 点击 / CTR / 转化 / CPA（无"会话数/参与度"，Google Ads 没有该口径） |
| 转化漏斗 | `campaign` + `segments.conversion_action_name` | 点击 → 全部转化 → 主转化；中间环节需 GA4 / HubSpot |

```bash
python refresh_real_data.py     # 汇总层：REAL_DATA（KPI / 趋势 / 系列）
python patch_page.py            # 注入汇总数据并修复数据层
python refresh_detail_data.py   # 明细层：REAL_DETAIL（5 个明细看板）
python patch_detail.py          # 注入明细数据并改造明细看板
node smoke.js                   # 冒烟测试（含明细看板渲染检查）
node detail_dump.js 30          # 导出页面明细 → page_detail.json
python verify_detail.py         # 回查 API 对账明细模块（需先跑 detail_dump.js）
python final_verify.py          # 回查 API 对账 KPI（需先跑 node verify_page.js）
```

数据口径要点：
- `daysAgo` 按**真实日历差**计算，不能用"有数据日期的排序索引"（会整体错位）
- 花费以 `cost_micros` 整数存储，加载时 `/1e6`，避免逐行四舍五入累积误差
- 账户货币为 **CNY**，页面金额单位即 ¥
- 页面徽标会显示数据截止日；超过 3 天未刷新会提示"数据已滞后"
- 回查 API 时 GAQL **必须 SELECT `segments.date`**：实测不按日取时 Google 返回的
  `metrics.impressions` 会偏大（同一搜索词同一窗口 1300 → 2794），无法与按日聚合对齐
- 明细模块有真实数据时一律覆盖示例数据；窗口内无数据则显示空态提示，不回退示例模板

## 在线访问

- GitHub Pages：<https://bigshawnmuscle.github.io/workbuddy-GoogleADs/>（开启 Pages 后自动生效）
- 资料库版本：<https://workbuddy.link/p/wzeBQN5dNrgSpau9Xq5C7G>（支持数据表在线同步）

## 功能模块

- 多账户切换 + 多级筛选（周期 / 对比模式 / 广告系列 / 类型 / 设备 / 品牌词）
- KPI 看板与趋势图（环比 / 同比）
- 四象限分析（放量 / 观察 / 风险 / 淘汰）
- 广告系列 / 关键词 / 搜索词意图分析
- 广告素材对比（Top / Bottom Ads）
- 市场受众（国家 / 语言 / 设备）
- 落地页 Message Match 诊断
- 转化漏斗 + HubSpot 线索质量（真实数据）
- 优化中心（P0/P1/P2 优先级待办）
- AI 洞察（风险 / 机会 / 洞察 / 行动）

## 技术特点

- 单文件 HTML，零外部依赖，全部 CSS / JS / SVG 图表内联
- 深色科技感视觉系统，PC / 移动端自适应
- 数据支持：内置演示数据 + CSV 导入（Google Ads 中英文表头兼容）+ 资料库数据表在线同步
- 离线自动降级 localStorage，支持 JSON 备份 / 恢复

## 使用

直接用浏览器打开 `index.html` 即可，无需安装任何依赖。
