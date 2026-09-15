/* 把页面按当前窗口聚合出的明细看板数据导出为 JSON，供 Python 回查 API 对账 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const CANDIDATES = [
  path.join(__dirname, 'index.html'),
  path.join(__dirname, '..', 'index.html'),
  path.join(__dirname, 'repo', 'index.html'),
];
const HTML_PATH = CANDIDATES.find(p => fs.existsSync(p));
if (!HTML_PATH) throw new Error('找不到 index.html');
const html = fs.readFileSync(HTML_PATH, 'utf8');
const code = html.match(/<script\b[^>]*>([\s\S]*?)<\/script>/i)[1];

const store = {};
const created = {};
function mkEl(id) {
  const el = {
    id, _text: '', _html: '', style: {}, className: '', value: '', dataset: {},
    children: [], classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    get textContent() { return this._text; }, set textContent(v) { this._text = String(v); },
    get innerHTML() { return this._html; }, set innerHTML(v) { this._html = String(v); },
    appendChild(c) { this.children.push(c); return c; },
    setAttribute() {}, getAttribute() { return null; }, removeAttribute() {},
    addEventListener() {}, removeEventListener() {}, querySelector() { return null; },
    querySelectorAll() { return []; }, focus() {}, click() {}, remove() {},
    insertAdjacentHTML(pos, h) { this._html += h; }, getBoundingClientRect() { return { width: 800, height: 400, top: 0, left: 0 }; },
  };
  return el;
}
const document = {
  getElementById(id) { if (!created[id]) created[id] = mkEl(id); return created[id]; },
  querySelector() { return mkEl('q'); }, querySelectorAll() { return []; },
  createElement(t) { return mkEl('<' + t + '>'); },
  createElementNS() { return mkEl('ns'); },
  addEventListener() {}, removeEventListener() {},
  body: mkEl('body'), head: mkEl('head'), documentElement: mkEl('html'),
  readyState: 'complete',
};
const window = {
  document, location: { href: 'http://localhost/', search: '', hash: '' },
  localStorage: { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: k => { delete store[k]; } },
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
window.window = window; window.self = window;
const ctx = Object.assign(window, {
  console, Math, Date, JSON, Object, Array, String, Number, Boolean, RegExp, Error,
  isFinite, isNaN, parseInt, parseFloat, encodeURIComponent, decodeURIComponent,
  Promise, Set, Map, Intl,
});
vm.createContext(ctx);
vm.runInContext(code, ctx, { timeout: 60000 });

const RANGE = parseInt(process.argv[2] || '30', 10);
const out = { range: RANGE, epoch: ctx.REAL_EPOCH, accounts: {} };
for (const a of ctx.ACCOUNTS) {
  ctx.S.account = a.id;
  ctx.S.range = RANGE;
  ctx.S.filters = { campaign: '', ctype: '', market: '', adgroup: '', device: '', action: '', brand: '', category: '' };
  const acc = ctx.accById(a.id);
  const data = ctx.ds(acc);
  ctx.applyDetail(data, RANGE);
  const mod = data.realMod || {};
  const pick = (arr, key, n) => (arr || []).slice(0, n).map(x => ({
    n: x[key], impr: x.impr | 0, clicks: x.clicks | 0,
    spend: +(x.spend || 0).toFixed(2), conv: +(x.conv || 0).toFixed(2),
  }));
  out.accounts[a.id] = {
    win: mod.win || null,
    kw: pick(data.keywords, 'kw', 12),
    st: pick(data.searchTerms, 'term', 12),
    ad: pick(data.ads, 'name', 8),
    lp: pick(data.landing, 'lp', 8),
    ca: (data.ca || []).slice(0, 8).map(x => ({ n: x.name, conv: +x.conv.toFixed(2), all: +x.all.toFixed(2) })),
  };
}
fs.writeFileSync(path.join(__dirname, '..', 'page_detail.json'), JSON.stringify(out, null, 1), 'utf8');
console.log('已导出 page_detail.json（窗口 %d 天）', RANGE);
