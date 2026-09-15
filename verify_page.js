/* 抽取页面脚本做语法检查 + 用页面自身逻辑重算近30天KPI */
const fs = require('fs');
const vm = require('vm');
const html = fs.readFileSync('repo/index.html', 'utf8');

// --- 1. 语法检查 ---
const scripts = [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)].map(m => m[1]);
console.log('script 块数:', scripts.length);
let all = scripts.join('\n;\n');
try { new vm.Script(all); console.log('[PASS] JS 语法检查通过'); }
catch (e) { console.log('[FAIL] JS 语法错误:', e.message); process.exit(1); }

// --- 2. 抽出数据层，用页面逻辑重算 ---
function grab(startMarker, endMarker) {
  const i = html.indexOf(startMarker);
  if (i < 0) throw new Error('未找到 ' + startMarker);
  const j = html.indexOf(endMarker, i);
  return html.slice(i, j + endMarker.length);
}
const src = [
  grab("var REAL_EPOCH=", "';"),
  grab("var REAL_DATA_END=", "';"),
  (function () { const i = html.indexOf('var REAL_DATA='); const j = html.indexOf('\n', i); return html.slice(i, j); })(),
  grab("var ACTIONS=", ";"),
  grab("var DEVICES=", ";"),
  grab("var ACCOUNTS=[", "\n];"),
].join('\n');

const ctx = { console };
vm.createContext(ctx);
vm.runInContext(src + `
function today0(){return new Date(new Date().toFullISO?0:0)}
`, ctx);

// 复刻页面 realData 的 shift 逻辑
const todayStr = process.env.FAKE_TODAY || new Date().toISOString().slice(0, 10);
const today = new Date(todayStr + 'T00:00:00');
const epoch = new Date(ctx.REAL_EPOCH + 'T00:00:00');
const shift = Math.max(0, Math.round((today - epoch) / 864e5));
console.log(`\n今天=${todayStr}  REAL_EPOCH=${ctx.REAL_EPOCH}  数据截止=${ctx.REAL_DATA_END}  shift=${shift}`);

const out = {};
for (const a of ctx.ACCOUNTS) {
  const rd = ctx.REAL_DATA[a.id];
  if (!rd) { out[a.id] = null; continue; }
  let impr = 0, clicks = 0, spend = 0, conv = 0, n = 0;
  // 页面视角：窗口 daysAgo ∈ [shift+0, shift+29]，而 row[0] 已含 shift
  for (const r of rd.r) {
    const ago = r[0] + shift;
    if (ago < 0 || ago > 29) continue;          // 近 30 天
    impr += r[5]; clicks += r[6]; spend += r[7] / 1e6; conv += r[8]; n++;
  }
  out[a.id] = { name: a.gname || a.name, cid: a.cid.replace(/-/g, ''), impr, clicks, spend: +spend.toFixed(2), conv: +conv.toFixed(2), rows: n,
                camps: rd.c.length, cur: (rd.meta && rd.meta.cur) || '?' };
}
console.log('\n页面重算的「近 30 天」KPI：');
for (const k of Object.keys(out)) {
  const o = out[k]; if (!o) { console.log(`  ${k}: 无 REAL_DATA`); continue; }
  console.log(`  ${k.padEnd(11)} ${String(o.cid).padEnd(12)} ${o.name.padEnd(30)} impr=${String(o.impr).padStart(8)} clicks=${String(o.clicks).padStart(7)} spend=${String(o.spend).padStart(11)} conv=${String(o.conv).padStart(7)} (${o.cur}, rows=${o.rows}, camps=${o.camps})`);
}
fs.writeFileSync('page_kpi.json', JSON.stringify(out, null, 1));
console.log('\n已保存 -> page_kpi.json');
