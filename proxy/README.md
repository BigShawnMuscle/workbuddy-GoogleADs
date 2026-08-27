# Google Ads 实时数据代理（Cloudflare Worker）

让工作台从「每日定时刷新」升级为「打开即查最新数据」的云端代理层。

## 架构

```
浏览器（google-ads-workspace.html）
   │  GET https://ads-proxy.<你的域名>/?days=30   （页面加载时自动调用）
   ▼
Cloudflare Worker（本目录 worker.js，持有凭据）
   │  1. 用 refresh_token 换 access_token（oauth2.googleapis.com）
   │  2. 调 Google Ads API searchStream（GAQL 查询 campaign 日报）
   ▼
Google Ads API  →  返回 JSON：{ epoch, accounts: { customerId: { c, r } } }
```

返回格式与页面内置的 `REAL_DATA` 完全一致（`c` = campaign 名列表，`r` = 行数组
`[daysAgo, campaignIdx, 0, deviceIdx, 0, impr, clicks, cost, conv]`），页面拿到后直接
替换对应账户的数据即可，无需改任何图表逻辑。

## 一、准备凭据（一次性）

1. **OAuth 客户端**
   - 打开 Google Cloud Console → 创建项目 → 启用「Google Ads API」
   - API 与服务 → 凭据 → 创建 OAuth 客户端 ID（类型：Web 应用，重定向 URI 随便填如
     `http://localhost`）→ 记下 Client ID / Client Secret
2. **授权获取 refresh_token**（一次性，浏览器打开）：
   ```
   https://accounts.google.com/o/oauth2/v2/auth?client_id=<CLIENT_ID>&redirect_uri=http://localhost&response_type=code&scope=https://www.googleapis.com/auth/adwords&access_type=offline&prompt=consent
   ```
   授权后地址栏会跳到 `http://localhost?code=<CODE>`，然后：
   ```
   curl -X POST https://oauth2.googleapis.com/token \
     -d client_id=<CLIENT_ID> -d client_secret=<CLIENT_SECRET> \
     -d code=<CODE> -d grant_type=authorization_code -d redirect_uri=http://localhost
   ```
   返回里的 `refresh_token` 就是 `GOOGLE_REFRESH_TOKEN`
3. **开发者令牌**：Google Ads 后台 → 工具与设置 → API 中心 → 申请开发者令牌
   （测试环境即可用，正式环境需审核）
4. **MCC 客户 ID**（可选）：8021601652，用于跨账户查询

## 二、部署 Worker

```bash
npm install -g wrangler
cd proxy
wrangler login
wrangler deploy            # 或 wrangler dev 本地调试
wrangler secret put GOOGLE_CLIENT_ID
wrangler secret put GOOGLE_CLIENT_SECRET
wrangler secret put GOOGLE_REFRESH_TOKEN
wrangler secret put GOOGLE_ADS_DEVELOPER_TOKEN
```

（`GOOGLE_ADS_LOGIN_CUSTOMER`、`GOOGLE_ADS_API_VERSION`、`REAL_EPOCH` 可在
`wrangler.toml` 的 `[vars]` 里配置；不配则用代码默认值。）

## 三、页面接入

把 `google-ads-workspace.html` 里 `REAL_API_URL` 常量填成你的 Worker 地址，例如：

```js
var REAL_API_URL = 'https://ads-proxy.你的域名.workers.dev';
```

保存并重新部署页面即可。Worker 不可用时自动回退到内置 REAL_DATA，不影响使用。

## 四、验证

```bash
curl 'https://ads-proxy.你的域名.workers.dev/?days=7'
# 应返回 { epoch, range, accounts: { "2068692080": {c:[...], r:[...]}, ... } }
```

## 注意事项

- Google Ads 报表本身有约 1 天延迟，即使实时查询，「今天」的数据也不完整，属正常现象。
- 每次请求都会刷新 OAuth token，低频使用（每天几次）完全免费（Worker 免费额度内）。
- 升级 API 版本：改环境变量 `GOOGLE_ADS_API_VERSION`（当前默认 v19，按官方最新调整）。
- 不要把凭据提交到 git——所有密钥走 `wrangler secret`，`.env` 类文件一律 gitignore。
