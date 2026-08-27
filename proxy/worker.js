/**
 * Google Ads 实时数据代理 (Cloudflare Worker)
 *
 * 作用：浏览器无法直接调用 Google Ads API（密钥不能进前端），本 Worker 作为云端代理：
 *   浏览器 -> 本 Worker（持有凭据） -> Google Ads API (searchStream) -> 规范化 JSON -> 浏览器
 *
 * 部署：wrangler deploy（见 README.md）
 * 环境变量（wrangler secret put / dashboard 配置）：
 *   GOOGLE_CLIENT_ID           必填  OAuth Client ID（Google Cloud Console 创建）
 *   GOOGLE_CLIENT_SECRET       必填  OAuth Client Secret
 *   GOOGLE_REFRESH_TOKEN       必填  授权后的 refresh_token（需授权 Google Ads API scope）
 *   GOOGLE_ADS_DEVELOPER_TOKEN 必填  Google Ads API 开发者令牌（MCC 后台申请）
 *   GOOGLE_ADS_LOGIN_CUSTOMER  可选  MCC 客户 ID，如 8021601652（跨账户查询时建议带上）
 *   GOOGLE_ADS_API_VERSION     可选  默认 v19（按官方当前版本调整）
 *   REAL_EPOCH                 可选  与页面 REAL_EPOCH 保持一致，默认 2026-08-25，勿随意改动
 *
 * 调用方式（页面内置逻辑）：
 *   GET https://<worker域名>/?days=30
 *   返回：{ epoch, accounts: { "<customerId>": { c:[campaignName...], r:[[d,ci,0,dev,0,impr,clicks,cost,conv]...] } } }
 */

const DEV_MAP = { DESKTOP: 0, MOBILE: 1, TABLET: 2 };
const ACCOUNTS = [
  { id: '2068692080', name: 'basic' },
  { id: '4469410060', name: 'gloves' },
  { id: '8529881574', name: 'medical' },
];

async function getAccessToken(env) {
  const body = new URLSearchParams({
    grant_type: 'refresh_token',
    client_id: env.GOOGLE_CLIENT_ID,
    client_secret: env.GOOGLE_CLIENT_SECRET,
    refresh_token: env.GOOGLE_REFRESH_TOKEN,
  });
  const res = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });
  if (!res.ok) throw new Error('token refresh failed: ' + res.status + ' ' + (await res.text()).slice(0, 300));
  const j = await res.json();
  return j.access_token;
}

function buildGaql(dateFrom, dateTo) {
  return [
    'SELECT campaign.name, segments.date, segments.device,',
    ' metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions',
    'FROM campaign',
    "WHERE segments.date BETWEEN '" + dateFrom + "' AND '" + dateTo + "'",
    'ORDER BY segments.date',
  ].join(' ');
}

async function queryAccount(token, env, customerId, gaql) {
  const version = env.GOOGLE_ADS_API_VERSION || 'v24';
  const url = 'https://googleads.googleapis.com/' + version + '/customers/' + customerId + '/googleAds:searchStream';
  const headers = {
    Authorization: 'Bearer ' + token,
    'developer-token': env.GOOGLE_ADS_DEVELOPER_TOKEN,
    'Content-Type': 'application/json',
  };
  if (env.GOOGLE_ADS_LOGIN_CUSTOMER) headers['login-customer-id'] = env.GOOGLE_ADS_LOGIN_CUSTOMER;
  const res = await fetch(url, {
    method: 'POST',
    headers,
    body: JSON.stringify({ query: gaql }),
  });
  if (!res.ok) throw new Error('searchStream ' + customerId + ' failed: ' + res.status + ' ' + (await res.text()).slice(0, 300));
  const batches = await res.json();
  return batches.flatMap((b) => b.results || []);
}

function normalize(rows, epochMs) {
  const names = [];
  const idx = {};
  const out = [];
  rows.forEach((r) => {
    const n = r.campaign && r.campaign.name;
    if (!n) return;
    if (!(n in idx)) { idx[n] = names.length; names.push(n); }
    const date = r.segments.date; // YYYY-MM-DD
    const d = Math.round((epochMs - new Date(date + 'T00:00:00').getTime()) / 864e5);
    const dev = DEV_MAP[r.segments.device] !== undefined ? DEV_MAP[r.segments.device] : 0;
    const impr = parseInt(r.metrics.impressions, 10) || 0;
    const clicks = parseInt(r.metrics.clicks, 10) || 0;
    const cost = Math.round((parseInt(r.metrics.cost_micros, 10) || 0) / 1e4) / 100;
    const conv = parseFloat(r.metrics.conversions) || 0;
    if (impr === 0 && clicks === 0 && cost === 0 && conv === 0) return; // 丢弃全零行
    out.push([d, idx[n], 0, dev, 0, impr, clicks, cost, conv]);
  });
  return { c: names, r: out };
}

function corsHeaders() {
  return {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
  };
}

export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: corsHeaders() });
    if (request.method !== 'GET') return new Response('method not allowed', { status: 405, headers: corsHeaders() });

    const url = new URL(request.url);
    const days = Math.min(365, Math.max(1, parseInt(url.searchParams.get('days') || '30', 10) || 30));

    // 数据范围：截止到昨天（Google Ads 报表有约 1 天延迟）
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const dateTo = new Date(today.getTime() - 864e5);
    const dateFrom = new Date(today.getTime() - (days + 1) * 864e5);
    const fmt = (d) => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');

    try {
      const token = await getAccessToken(env);
      const gaql = buildGaql(fmt(dateFrom), fmt(dateTo));
      const epoch = env.REAL_EPOCH || '2026-08-25';
      const epochMs = new Date(epoch + 'T00:00:00').getTime();
      const accounts = {};
      for (const a of ACCOUNTS) {
        try {
          const rows = await queryAccount(token, env, a.id, gaql);
          accounts[a.name] = normalize(rows, epochMs);
        } catch (e) {
          // 单账户失败不拖垮整体，返回错误信息便于排查
          accounts[a.name] = { error: String(e && e.message || e) };
        }
      }
      return new Response(JSON.stringify({ epoch, range: { from: fmt(dateFrom), to: fmt(dateTo) }, accounts }), {
        headers: { 'Content-Type': 'application/json', ...corsHeaders() },
      });
    } catch (e) {
      return new Response(JSON.stringify({ error: String(e && e.message || e) }), {
        status: 502,
        headers: { 'Content-Type': 'application/json', ...corsHeaders() },
      });
    }
  },
};
