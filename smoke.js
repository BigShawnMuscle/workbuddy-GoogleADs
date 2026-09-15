/* 运行时冒烟：用最小 DOM 桩执行整段页面脚本，捕获运行时异常并抽查渲染结果 */
const fs = require('fs');
const vm = require('vm');
const html = fs.readFileSync('repo/index.html', 'utf8');
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
    console.log('  %-11s %-30s 徽标=%s 花费=%s', a.id, a.gname || a.name, badge, spend);
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

console.log('\n结论: %s', errors.length ? '存在问题 ✗\n  ' + errors.join('\n  ') : '冒烟通过 ✓');
process.exit(errors.length ? 1 : 0);
