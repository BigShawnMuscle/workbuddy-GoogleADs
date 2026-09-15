/* 运行时冒烟：用最小 DOM 桩执行整段页面脚本，捕获运行时异常并抽查渲染结果 */
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const CANDIDATES = [
  path.join(__dirname, 'index.html'),
  path.join(__dirname, '..', 'index.html'),
  path.join(__dirname, 'repo', 'index.html'),
  'repo/index.html',
];
const HTML_PATH = CANDIDATES.find(p => fs.existsSync(p));
if (!HTML_PATH) throw new Error('找不到 index.html，已尝试: ' + CANDIDATES.join(' | '));
const html = fs.readFileSync(HTML_PATH, 'utf8');
const code = html.match(/<script\b[^>]*>([\s\S]*?)<\/script>/i)[1];

const store = {};
const errors = [];
const created = {};

function mkEl(id) {
  const el = {
    id, _text: '', _html: '', style: {}, className: '', value: '', dataset: {},
    children: [], classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    get textContent() { return this._text; }, set textContent(v) { this._text = String(v); },
    get innerHTML() { return this._html; }, set innerHTML(v) { this._html = String(v); },
    appendChild(c) { this.children.push(c); return c; },
    removeChild() {}, remove() {}, setAttribute() {}, getAttribute() { return null; },
    addEventListener() {}, removeEventListener() {}, focus() {}, click() {},
    querySelector() { return mkEl('q'); }, querySelectorAll() { return []; },
    closest() { return null; }, getBoundingClientRect() { return { width: 800, height: 400, top: 0, left: 0 }; },
    insertAdjacentHTML(p, s) { this._html += String(s); }, scrollIntoView() {},
  };
  return el;
}

const document = {
  getElementById(id) { return (created[id] = created[id] || mkEl(id)); },
  querySelector() { return mkEl('q'); }, querySelectorAll() { return []; },
  createElement(t) { return mkEl(t); },
  createElementNS() { return mkEl('ns'); },
  addEventListener() {}, removeEventListener() {},
  body: mkEl('body'), head: mkEl('head'), documentElement: mkEl('html'),
  readyState: 'complete',
};

const window = {
  document, location: { href: 'http://localhost/', search: '', hash: '' },
  localStorage: {
    getItem: k => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: k => { delete store[k]; },
  },
  addEventListener() {}, removeEventListener() {},
  setTimeout: (fn, ms) => setTimeout(fn, Math.min(ms || 0, 5)),
  clearTimeout, setInterval: () => 0, clearInterval,
  fetch: () => Promise.reject(new Error('offline')),
  matchMedia: () => ({ matches: false, addListener() {}, addEventListener() {} }),
  requestAnimationFrame: fn => setTimeout(fn, 0),
  innerWidth: 1440, innerHeight: 900, devicePixelRatio: 1,
  Blob: class {}, URL: { createObjectURL: () => '', revokeObjectURL() {} },
  AbortController: class { constructor() { this.signal = {}; } abort() {} },
  navigator: { userAgent: 'node' }, console,
  __SMART_PAGE__: null,
};
window.window = window;
window.self = window;

const ctx = Object.assign(window, {
  console, Math, Date, JSON, Object, Array, String, Number, Boolean, RegExp, Error,
  isFinite, isNaN, parseInt, parseFloat, encodeURIComponent, decodeURIComponent,
  Promise, Set, Map, Intl,
});
vm.createContext(ctx);

try {
  vm.runInContext(code, ctx, { timeout: 30000 });
} catch (e) {
  errors.push('运行时异常: ' + e.message + '\n' + (e.stack || '').split('\n').slice(0, 4).join('\n'));
}

// 抽查关键渲染产物
const checks = [
  ['KPI 周期', 'kpiPeriod'], ['数据徽标', 'dataBadge'], ['账户下拉', 'accSel'],
  ['系列下拉', 'fCampaign'], ['市场下拉', 'fMarket'], ['KPI 花费', 'kSpend'],
];
console.log('=== 冒烟测试 ===');
console.log('运行时错误:', errors.length ? '\n  ' + errors.join('\n  ') : '无 ✓');
console.log('\n关键节点渲染结果：');
for (const [label, id] of checks) {
  const el = created[id];
  const v = el ? (el._text || el._html || '').slice(0, 90).replace(/\s+/g, ' ') : '(未访问)';
  console.log('  %s (%s): %s', label.padEnd(8), id, v || '(空)');
}

// 切到每个账户再渲染一次，确保 5 个账户都不炸
console.log('\n逐账户渲染：');
for (const a of ctx.ACCOUNTS) {
  try {
    ctx.S.account = a.id;
    ctx.S.range = 30;
    ctx.S.filters = { campaign: '', ctype: '', market: '', adgroup: '', device: '', action: '', brand: '', category: '' };
    ctx.renderAll();
    const badge = created['dataBadge'] ? created['dataBadge']._text : '';
    const spend = created['kSpend'] ? created['kSpend']._text : '';
    console.log('  ' + a.id.padEnd(12) + (a.gname || a.name).padEnd(30) + '徽标=' + badge + ' 花费=' + spend);
  } catch (e) {
    errors.push(a.id + ': ' + e.message);
    console.log('  %-11s 渲染失败: %s', a.id, e.message);
  }
}

// 抓取 KPI 卡片实际渲染出的数字
console.log('\nKPI 看板实际渲染（近 30 天）：');
for (const a of ctx.ACCOUNTS) {
  ctx.S.account = a.id; ctx.S.range = 30;
  ctx.S.filters = { campaign: '', ctype: '', market: '', adgroup: '', device: '', action: '', brand: '', category: '' };
  ctx.autoRangeFor(ctx.accById(a.id));
  ctx.renderAll();
  const g = created['kpiGrid'];
  const txt = (g ? g._html : '').replace(/<[^>]+>/g, '|').replace(/\|+/g, ' | ').replace(/\s+/g, ' ').trim();
  console.log('  [%s] %s', a.id, txt.slice(0, 240));
}

// 明细看板（关键词/搜索词/广告/落地页）是否有真实内容
console.log('\n明细看板渲染（近 30 天）：');
for (const a of ctx.ACCOUNTS) {
  ctx.S.account = a.id; ctx.S.range = 30;
  ctx.S.filters = { campaign: '', ctype: '', market: '', adgroup: '', device: '', action: '', brand: '', category: '' };
  ctx.renderAll();
  const cnt = id => {
    const el = created[id];
    if (!el) return '无节点';
    const h = el._html || '';
    const rows = (h.match(/<tr>/g) || []).length;
    return /没有该维度的真实数据|无广告投放数据|无落地页数据/.test(h) ? '空态提示' : rows + ' 行';
  };
  const tag = id => (created[id] ? created[id]._text : '');
  console.log('  ' + a.id.padEnd(12) + '关键词 ' + cnt('kwTbl').padEnd(10)
    + tag('kwDemoTag').padEnd(18) + '搜索词 ' + cnt('stTbl').padEnd(10)
    + '广告 ' + cnt('adTbl').padEnd(10) + '落地页 ' + cnt('lpTbl'));
}

// HubSpot 转化漏斗 / 线索质量 / 广告系列归因
console.log('\nHubSpot 接入渲染（近 30 天 / 90 天）：');
for (const rg of [30, 90]) {
  ctx.S.account = 'all'; ctx.S.range = rg;
  ctx.S.filters = { campaign: '', ctype: '', market: '', adgroup: '', device: '', action: '', brand: '', category: '' };
  try {
    ctx.renderAll();
  } catch (e) {
    errors.push('HubSpot renderAll r' + rg + ': ' + e.message);
    console.log('  近 %d 天 渲染失败: %s', rg, e.message);
    continue;
  }
  const fb = created['funnelBox'] ? created['funnelBox']._html : '';
  const rows = (fb.match(/<tr>/g) || []).length;
  const nums = (fb.replace(/<[^>]+>/g, ' ').match(/\d[\d,\.]*%?/g) || []).slice(0, 24).join(' ');
  console.log('  近 %d 天 漏斗: %s', rg, (/没有|暂无|未同步/.test(fb) ? '空态' : rows + ' 段') + ' | ' + nums);
  const dg = created['funnelDiag']
    ? created['funnelDiag']._html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 320) : '';
  console.log('         诊断: %s', dg || '(空)');

  const hs = created['hsTbl'] ? created['hsTbl']._html : '';
  console.log('         HubSpot 表: %d 行 | 标记=%s', (hs.match(/<tr>/g) || []).length,
    created['hsDemoTag'] ? created['hsDemoTag']._text : '');

  const hc = created['hsCampTbl'] ? created['hsCampTbl']._html : '';
  console.log('         系列归因表: %d 行 | 标记=%s', (hc.match(/<tr>/g) || []).length,
    created['hsCampTag'] ? created['hsCampTag']._text : '');
  if (rg === 30) {
    const head = hc.replace(/<[^>]+>/g, '|').replace(/\|+/g, ' | ').replace(/\s+/g, ' ').trim().slice(0, 300);
    console.log('         归因表内容: %s', head || '(空)');
  }
}

console.log('\n结论: %s', errors.length ? '存在问题 ✗\n  ' + errors.join('\n  ') : '冒烟通过 ✓');
process.exit(errors.length ? 1 : 0);
