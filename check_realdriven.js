/* 校验：系列表是否与 Google Ads 后台列表一致（含暂停/结束）、待办与洞察是否引用真实对象 */
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const CANDIDATES = [path.join(__dirname, 'index.html'), path.join(__dirname, '..', 'index.html'), 'repo/index.html'];
const HTML_PATH = CANDIDATES.find(p => fs.existsSync(p));
const html = fs.readFileSync(HTML_PATH, 'utf8');
const code = html.match(/<script\b[^>]*>([\s\S]*?)<\/script>/i)[1];

const created = {};
function mkEl(id) {
  return {
    id, _text: '', _html: '', style: {}, className: '', value: '', dataset: {}, children: [],
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    get textContent() { return this._text; }, set textContent(v) { this._text = String(v); },
    get innerHTML() { return this._html; }, set innerHTML(v) { this._html = String(v); },
    appendChild(c) { this.children.push(c); return c; }, removeChild() {}, remove() {},
    setAttribute() {}, getAttribute() { return null; }, addEventListener() {}, removeEventListener() {},
    focus() {}, click() {}, querySelector() { return mkEl('q'); }, querySelectorAll() { return []; },
    closest() { return null; }, getBoundingClientRect() { return { width: 800, height: 400, top: 0, left: 0 }; },
    insertAdjacentHTML(p, s) { this._html += String(s); }, scrollIntoView() {},
  };
}
const document = {
  getElementById(id) { return (created[id] = created[id] || mkEl(id)); },
  querySelector() { return mkEl('q'); }, querySelectorAll() { return []; },
  createElement(t) { return mkEl(t); }, createElementNS() { return mkEl('ns'); },
  addEventListener() {}, removeEventListener() {},
  body: mkEl('body'), head: mkEl('head'), documentElement: mkEl('html'), readyState: 'complete',
};
const store = {};
const window = {
  document, location: { href: 'http://localhost/', search: '', hash: '' },
  localStorage: { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: k => { delete store[k]; } },
  addEventListener() {}, removeEventListener() {}, setTimeout: (fn, ms) => setTimeout(fn, Math.min(ms || 0, 5)),
  clearTimeout, setInterval: () => 0, clearInterval, fetch: () => Promise.reject(new Error('offline')),
  matchMedia: () => ({ matches: false, addListener() {}, addEventListener() {} }),
  requestAnimationFrame: fn => setTimeout(fn, 0), innerWidth: 1440, innerHeight: 900, devicePixelRatio: 1,
  Blob: class {}, URL: { createObjectURL: () => '', revokeObjectURL() {} },
  AbortController: class { constructor() { this.signal = {}; } abort() {} },
  navigator: { userAgent: 'node' }, console, __SMART_PAGE__: null,
};
window.window = window; window.self = window;
const ctx = Object.assign(window, { console, Math, Date, JSON, Object, Array, String, Number, Boolean, RegExp, Error, isFinite, isNaN, parseInt, parseFloat, encodeURIComponent, decodeURIComponent, Promise, Set, Map, Intl });
vm.createContext(ctx);
vm.runInContext(code, ctx, { timeout: 30000 });

const txt = h => String(h || '').replace(/<[^>]+>/g, '|').replace(/\|+/g, ' | ').replace(/\s+/g, ' ').trim();
const only = process.argv[2] || 'basic';
const RANGE = Number(process.argv[3] || 30);

ctx.S.account = only; ctx.S.range = RANGE;
ctx.S.filters = { campaign: '', ctype: '', market: '', adgroup: '', device: '', action: '', brand: '', category: '' };
ctx.renderAll();

console.log('=== 账户 %s · 近 %d 天（%s） ===', only, RANGE, created['kpiPeriod'] ? created['kpiPeriod']._text : '');

const rows = (created['campTbl'] ? created['campTbl']._html : '').match(/<tr>[\s\S]*?<\/tr>/g) || [];
console.log('\n[系列表] 共 %d 行（表头 + 数据行）：', rows.length);
rows.forEach((r, i) => { if (i > 0 && i <= 40) console.log('   ' + txt(r).slice(0, 150)); });
if (rows.length - 1 > 40) console.log('   … 其余 %d 行省略', rows.length - 41);

console.log('\n[优化条目 / 今日待办]');
console.log('   ' + txt(created['focusList'] ? created['focusList']._html : '').slice(0, 400));
console.log('\n[AI 洞察]');
for (const [label, id] of [['风险', 'aiRisk'], ['机会', 'aiOpp'], ['内容', 'aiCont'], ['行动', 'aiAct']]) {
  console.log('   ' + label + '：' + txt(created[id] ? created[id]._html : '').slice(0, 300));
}
