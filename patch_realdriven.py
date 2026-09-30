# -*- coding: utf-8 -*-
"""
页面修复补丁（幂等）：
 A. 窗口口径：所有「近 N 天」窗口以【数据截止日】为终点（与 Google Ads 后台「过去 N 天」一致），
    不再包含无数据的当天（旧口径 daysAgo 0..N-1 → 实际 09-01~09-29，比后台少一天）。
 B. 待办 / 优化条目 / AI 洞察 / 系列表：全部改为由真实窗口数据生成，
    删除硬编码的示例广告系列（如 'PMax - Basic Medical - US'）与写死的美元证据（$320 / $860 / +27%）。
 C. 系列表补全账户全部系列（含已暂停/已结束/窗口内无投放），显示真实状态与日预算；
    ROAS 列在无收入数据时显示「—」而不是用示例客单价编造。
用法：python patch_realdriven.py
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

WS = r"C:\Users\caleb\WorkBuddy\2026-09-15-10-47-36"
PAGE = os.path.join(WS, "repo", "index.html")

REPL = []          # (name, old, new, marker)


def add(name, old, new, marker):
    REPL.append((name, old, new, marker))


# ---------- A1. dEndAgo 辅助函数 ----------
add(
    "A1 数据截止日锚点",
    "function dateByAgo(daysAgo){var d=today0();d.setDate(d.getDate()-daysAgo);return d}",
    "function dateByAgo(daysAgo){var d=today0();d.setDate(d.getDate()-daysAgo);return d}\n"
    "/* 数据截止日（REAL_DATA_END）距今天数：所有「近N天」窗口都以它为终点，\n"
    "   与 Google Ads 后台「过去N天」（截止昨天）口径一致 */\n"
    "function dEndAgo(){return Math.max(0,Math.round((today0()-new Date(REAL_EPOCH+'T00:00:00'))/864e5))+1}",
    "function dEndAgo()",
)

# ---------- A2. 明细窗口同步 ----------
add(
    "A2 明细窗口锚点",
    "  var d=data.detail;if(!d)return false;\n"
    "  var shift=Math.max(0,Math.round((today0()-new Date(REAL_EPOCH+'T00:00:00'))/864e5));",
    "  var d=data.detail;if(!d)return false;\n"
    "  var shift=dEndAgo(); /* ★ 明细窗口终点同样对齐数据截止日 */",
    "var shift=dEndAgo()",
)

# ---------- A3. 全站点击（HubSpot 卡片用）窗口 ----------
add(
    "A3 全站点击窗口",
    "    t+=sumRows(inWin(d.rows,S.filters,0,range-1,ACCOUNTS[i],d)).clicks;",
    "    var w0=dEndAgo();t+=sumRows(inWin(d.rows,S.filters,w0,w0+range-1,ACCOUNTS[i],d)).clicks;",
    "var w0=dEndAgo();t+=sumRows",
)

# ---------- A4. 对比周期 ----------
add(
    "A4 对比周期",
    "function cmpWindow(){\n"
    "  if(S.compare==='yoy')return [365,365+S.range-1];\n"
    "  if(S.compare==='prev')return [S.range,S.range*2-1];\n"
    "  return null;\n"
    "}",
    "function cmpWindow(){\n"
    "  var w0=dEndAgo();\n"
    "  if(S.compare==='yoy')return [w0+365,w0+365+S.range-1];\n"
    "  if(S.compare==='prev')return [w0+S.range,w0+S.range*2-1];\n"
    "  return null;\n"
    "}",
    "return [w0+365,w0+365+S.range-1];",
)

# ---------- A5. 主窗口 ----------
add(
    "A5 主窗口",
    "  var rows=inWin(data.rows,f,0,S.range-1,acc,data);\n  var cw=cmpWindow();",
    "  /* ★ 窗口 = 数据截止日往前 S.range 天（与 Google Ads 后台「过去N天」一致） */\n"
    "  var w0=dEndAgo();\n"
    "  var rows=inWin(data.rows,f,w0,w0+S.range-1,acc,data);\n"
    "  var cw=cmpWindow();",
    "var rows=inWin(data.rows,f,w0,w0+S.range-1,acc,data);",
)

# ---------- A6. KPI 周期标签 ----------
add(
    "A6 KPI 周期标签",
    "  var endD=dateByAgo(0),startD=dateByAgo(S.range-1);",
    "  var endD=dateByAgo(dEndAgo()),startD=dateByAgo(dEndAgo()+S.range-1);",
    "var endD=dateByAgo(dEndAgo())",
)

# ---------- B1. optSeeds：真实数据驱动 ----------
OLD_SEEDS_HEAD = """function optSeeds(acc){
  var w=acc.campaigns.filter(function(c){return c.role==='waste'})[0];"""
NEW_SEEDS = """/* 示例账户的种子（仅在没有任何真实数据时才使用） */
function optSeedsDemo(acc){
  var w=acc.campaigns.filter(function(c){return c.role==='waste'})[0];"""

add("B1a 示例种子改名", OLD_SEEDS_HEAD, NEW_SEEDS, "function optSeedsDemo(acc){")

OLD_SEEDS_TAIL = """   {priority:'P2',entity:rk.name,issue:'CPA ↑',evidence:'CPA 环比 +45%',reco:'检查落地页与出价策略',status:'待处理'}];
}
"""
NEW_SEEDS_TAIL = """   {priority:'P2',entity:rk.name,issue:'CPA ↑',evidence:'CPA 环比 +45%',reco:'检查落地页与出价策略',status:'待处理'}];
}

/* ★ 优化条目：全部由当前账户【真实窗口数据】生成（系列 / 关键词 / 搜索词都是后台真实对象） */
function optSeeds(acc){
  var data=ds(acc);
  if(!data||isDemo(acc))return optSeedsDemo(acc);
  var w0=dEndAgo(),win=S.range;
  var rows=inWin(data.rows,{},w0,w0+win-1,acc,data);
  var camps=campAgg(rows,data);
  var totSpend=0,totConv=0;
  camps.forEach(function(c){totSpend+=c.spend;totConv+=c.conv});
  var avgCpa=totConv>0?totSpend/totConv:NaN;
  var kws=(data.realMod&&data.realMod.kw&&data.keywords)?data.keywords:[];
  var sts=(data.realMod&&data.realMod.st&&data.searchTerms)?data.searchTerms:[];
  var winTag='近'+win+'天';
  var items=[];
  var zeroCamp=null;
  camps.forEach(function(c){if(c.spend>0&&c.conv<=0&&(!zeroCamp||c.spend>zeroCamp.spend))zeroCamp=c});
  if(zeroCamp)items.push({priority:'P0',entity:zeroCamp.name,issue:'高花费低转化',
    evidence:winTag+'花费 '+money(zeroCamp.spend)+' / 0 转化',reco:'先查搜索词与落地页，再削减预算',status:'待处理'});
  var worstCpa=null;
  camps.forEach(function(c){if(c.conv>0){var cpa=c.spend/c.conv;
    if(!worstCpa||cpa>worstCpa.cpa)worstCpa={name:c.name,cpa:cpa}}});
  if(!zeroCamp&&worstCpa&&isFinite(avgCpa)&&worstCpa.cpa>avgCpa*2)items.push({priority:'P0',entity:worstCpa.name,
    issue:'CPA 高于账户均值',evidence:'CPA '+money(worstCpa.cpa)+'，为均值 '+num1(worstCpa.cpa/avgCpa)+' 倍',
    reco:'收紧预算或调整出价',status:'待处理'});
  var stWaste=null;
  sts.forEach(function(s){if(s.spend>0&&s.conv<=0&&(!stWaste||s.spend>stWaste.spend))stWaste=s});
  if(stWaste)items.push({priority:'P0',entity:'搜索词',issue:'预算浪费',
    evidence:'「'+stWaste.term+'」'+money(stWaste.spend)+' / 0 转化',reco:'加否定词',status:'待处理'});
  var bestKw=null;
  kws.forEach(function(k){if(k.conv>=2){var cpa=k.spend/k.conv;
    if(!bestKw||cpa<bestKw.cpa)bestKw={kw:k.kw,cpa:cpa,conv:k.conv}}});
  if(bestKw)items.push({priority:'P1',entity:bestKw.kw,issue:'高 ROI',
    evidence:'CPA '+money(bestKw.cpa)+'，转化 '+int(bestKw.conv),reco:'提高出价并加 Exact 版本',status:'待处理'});
  var stBest=null;
  sts.forEach(function(s){if(s.conv>0){var cpa=s.spend/s.conv;
    if(!stBest||cpa<stBest.cpa)stBest={term:s.term,cpa:cpa}}});
  if(stBest)items.push({priority:'P1',entity:'搜索词 '+stBest.term,issue:'意图明确',
    evidence:'有转化且 CPA '+money(stBest.cpa),reco:'添加为 Exact 关键词',status:'待处理'});
  var oem=0,stTot=0;
  sts.forEach(function(s){stTot+=s.spend;if(intentOf(s.term)==='OEM'||intentOf(s.term)==='制造商')oem+=s.spend});
  if(stTot>0)items.push({priority:'P1',entity:'内容机会',issue:'OEM / 制造商类搜索词',
    evidence:'花费占比 '+pct(oem/stTot,0)+'（'+money(oem)+'）',reco:'新建 OEM / Private Label 主题 RSA',status:'待处理'});
  var lowCtr=null;
  camps.forEach(function(c){if(c.impr>=2000){var ctr=c.clicks/c.impr;
    if(!lowCtr||ctr<lowCtr.ctr)lowCtr={name:c.name,ctr:ctr,impr:c.impr}}});
  if(lowCtr)items.push({priority:'P2',entity:lowCtr.name,issue:'CTR 偏低',
    evidence:'曝光 '+int(lowCtr.impr)+' 但 CTR 仅 '+pct(lowCtr.ctr),reco:'重写文案与素材',status:'待处理'});
  var worstKw=null;
  kws.forEach(function(k){if(k.spend>0){var cpa=k.conv>0?k.spend/k.conv:Infinity;
    if(!worstKw||cpa>worstKw.cpa)worstKw={kw:k.kw,cpa:cpa}}});
  if(worstKw&&isFinite(worstKw.cpa))items.push({priority:'P2',entity:worstKw.kw,issue:'CPA 偏高',
    evidence:'CPA '+money(worstKw.cpa),reco:'检查落地页与匹配方式',status:'待处理'});
  if(!items.length)items.push({priority:'P2',entity:'本账户',issue:'窗口内无异常',
    evidence:winTag+'花费 '+money(totSpend)+'，未发现高花费零转化或 CPA 异常',reco:'保持观察',status:'待处理'});
  return items;
}
"""
add("B1b 新增真实数据种子", OLD_SEEDS_TAIL, NEW_SEEDS_TAIL, "function optSeeds(acc){\n  var data=ds(acc);")

# ---------- B2. optItems：丢弃旧版示例种子 ----------
add(
    "B2 丢弃旧示例种子",
    "  if(S.cloudOpt[acc.id]&&S.cloudOpt[acc.id].length)return S.cloudOpt[acc.id];\n"
    "  if(local&&local.length)return local;\n"
    "  return optSeeds(acc).map(function(x,i){var o={};for(var k in x)o[k]=x[k];o.lid='seed'+i;return o});\n"
    "}",
    "  var OPT_V=2; /* 种子版本：旧版示例种子（无 _v 标记）直接丢弃，避免示例系列被当成真实待办 */\n"
    "  function isLegacySeed(it){var k=String(it._id||it.lid||'');return /^seed\\d+$/.test(k)&&it._v!==OPT_V}\n"
    "  var src=(S.cloudOpt[acc.id]&&S.cloudOpt[acc.id].length)?S.cloudOpt[acc.id]:(local&&local.length?local:null);\n"
    "  if(src){var keep=src.filter(function(it){return !isLegacySeed(it)});if(keep.length)return keep}\n"
    "  return optSeeds(acc).map(function(x,i){var o={};for(var k in x)o[k]=x[k];o.lid='seed'+i;o._v=OPT_V;return o});\n"
    "}",
    "var OPT_V=2; /* 种子版本",
)

# ---------- B3. 线索质量：无数据不猜 ----------
add(
    "B3 线索质量缺省值",
    "  return {brand:'高',growth:'高',steady:'中',waste:'低',content:'低',risk:'中',imported:'中'}[role]||'中'}",
    "  /* 未在 HubSpot 里匹配到的真实系列：没有线索质量数据就显示「—」，不猜 */\n"
    "  return {brand:'高',growth:'高',steady:'中',waste:'低',content:'低',risk:'中',imported:'中'}[role]||'—'}",
    "return {brand:'高',growth:'高',steady:'中',waste:'低',content:'低',risk:'中',imported:'中'}[role]||'—'}",
)

# ---------- B4. 系列表：补全账户全部系列 + 状态 / 预算 + ROAS 不再编造 ----------
OLD_CAMPTBL = """function renderCampTable(camps,totSpend,acc){
  var html=['<thead><tr><th>广告系列</th><th class="num">花费</th><th class="num">花费占比</th><th class="num">点击</th><th class="num">CTR</th><th class="num">CPC</th><th class="num">转化</th><th class="num">CVR</th><th class="num">CPA</th><th>线索质量</th><th class="num">ROAS</th></tr></thead><tbody>'];
  camps.forEach(function(c){
    var ctr=safeDiv(c.clicks,c.impr),cpc=safeDiv(c.spend,c.clicks),cvr=safeDiv(c.conv,c.clicks),cpa=safeDiv(c.spend,c.conv);
    var roas=safeDiv(c.conv*acc.aov,c.spend);
    var ps=totSpend?c.spend/totSpend:0;
    var bw=Math.round(ps*46);
    html.push('<tr><td><b>'+esc(c.name)+'</b><div style="font-size:11px;color:var(--ink2)">'+esc(c.type)+' · '+esc(c.market)+' · '+esc(c.brand)+'</div></td>'+
     '<td class="num"><b>'+money(c.spend)+'</b></td>'+
     '<td class="num"><span class="spendbar" style="width:'+bw+'px"></span>'+pct(ps,1)+'</td>'+
     '<td class="num">'+int(c.clicks)+'</td><td class="num">'+pct(ctr)+'</td><td class="num">'+money2(cpc)+'</td>'+
     '<td class="num">'+int(c.conv)+'</td><td class="num">'+pct(cvr)+'</td>'+
     '<td class="num">'+(isFinite(cpa)?money(cpa):'—')+'</td>'+
     '<td><span class="pill '+(c.leadQ==='高'?'p-best':c.leadQ==='低'?'p-poor':'p-maint')+'">'+c.leadQ+'</span></td>'+
     '<td class="num">'+(isFinite(roas)?roas.toFixed(2)+'x':'—')+'</td></tr>')});
  html.push('</tbody>');
  $('campTbl').innerHTML=html.join('');
}"""

NEW_CAMPTBL = """function campStateOf(name,invMap){
  var e=invMap&&invMap[name];if(!e)return '';
  var s=String(e.s||''),end=e.en||'';
  if(s==='REMOVED')return '已移除';
  if(end&&end<isoDate(today0()))return '已结束';
  if(s==='PAUSED')return '已暂停';
  if(s==='ENABLED')return '有效';
  return s||'';
}
function campStatePill(st){
  if(!st)return '';
  var cls=st==='已暂停'?'p-maint':(st==='已结束'||st==='已移除'?'p-poor':'p-best');
  return '<span class="pill '+cls+'">'+esc(st)+'</span>';
}
function renderCampTable(camps,totSpend,acc){
  /* ★ 以账户真实系列清单为准：窗口内无投放的系列（已暂停 / 已结束 / 移除）也列出，
     状态与日预算取自 Google Ads API，与后台「广告系列」列表一致 */
  var inv=(typeof REAL_CAMPS!=='undefined'&&REAL_CAMPS&&REAL_CAMPS[acc.id])?REAL_CAMPS[acc.id]:null;
  var invMap={};(inv||[]).forEach(function(v){invMap[v.n]=v});
  var list=camps.slice(),have={};
  camps.forEach(function(c){have[c.name]=1});
  if(inv)inv.forEach(function(v){
    if(have[v.n])return;
    var rc=realCamp(v.n,(acc&&acc.cat)||'—');
    list.push({name:v.n,role:'inventory',type:v.t||rc.type,market:rc.market||'—',brand:rc.brand||'Non-brand',
      cat:rc.cat||'—',impr:0,clicks:0,spend:0,conv:0,idle:1,leadQ:'—'});
  });
  var html=['<thead><tr><th>广告系列</th><th>状态</th><th class="num">预算/天</th><th class="num">花费</th><th class="num">花费占比</th><th class="num">点击</th><th class="num">CTR</th><th class="num">CPC</th><th class="num">转化</th><th class="num">CVR</th><th class="num">CPA</th><th>线索质量</th><th class="num" title="未接入收入 / 成交金额数据，无法计算 ROAS">ROAS</th></tr></thead><tbody>'];
  list.forEach(function(c){
    var ctr=safeDiv(c.clicks,c.impr),cpc=safeDiv(c.spend,c.clicks),cvr=safeDiv(c.conv,c.clicks),cpa=safeDiv(c.spend,c.conv);
    var ps=totSpend?c.spend/totSpend:0;
    var bw=Math.round(ps*46);
    var st=campStateOf(c.name,invMap);
    var bud=invMap[c.name]?(invMap[c.name].b>0?money(invMap[c.name].b/1e6)+'/天':'—'):'—';
    var sub=esc(c.type)+' · '+esc(c.market)+' · '+esc(c.brand)+(c.idle?' · 窗口内无投放':'');
    html.push('<tr><td><b>'+esc(c.name)+'</b><div style="font-size:11px;color:var(--ink2)">'+sub+'</div></td>'+
     '<td>'+campStatePill(st)+'</td>'+
     '<td class="num">'+bud+'</td>'+
     '<td class="num"><b>'+money(c.spend)+'</b></td>'+
     '<td class="num"><span class="spendbar" style="width:'+bw+'px"></span>'+pct(ps,1)+'</td>'+
     '<td class="num">'+int(c.clicks)+'</td><td class="num">'+(c.impr?pct(ctr):'—')+'</td><td class="num">'+(isFinite(cpc)?money2(cpc):'—')+'</td>'+
     '<td class="num">'+int(c.conv)+'</td><td class="num">'+(c.clicks?pct(cvr):'—')+'</td>'+
     '<td class="num">'+(isFinite(cpa)?money(cpa):'—')+'</td>'+
     '<td>'+(c.leadQ&&c.leadQ!=='—'?'<span class="pill '+(c.leadQ==='高'?'p-best':c.leadQ==='低'?'p-poor':'p-maint')+'">'+c.leadQ+'</span>':'<span style="color:var(--ink2)">—</span>')+'</td>'+
     '<td class="num" style="color:var(--ink2)">—</td></tr>')});
  html.push('</tbody>');
  $('campTbl').innerHTML=html.join('');
}"""

add("B4 系列表真实化", OLD_CAMPTBL, NEW_CAMPTBL, "function campStateOf(name,invMap){")

# ---------- B5. AI 洞察：关键词 / 搜索词改用真实明细 ----------
add(
    "B5a AI 关键词数据源",
    "  var bestKw=baseData(acc).keywords.filter(function(k){return k.conv>=3}).sort(function(a,b){return safeDiv(a.spend,a.conv)-safeDiv(b.spend,b.conv)})[0];",
    "  /* ★ 用真实明细（applyDetail 注入的 data.keywords / data.searchTerms），示例账户才回退到示例数据 */\n"
    "  var aiKw=(data.realMod&&data.realMod.kw&&data.keywords)?data.keywords:baseData(acc).keywords;\n"
    "  var aiSt=(data.realMod&&data.realMod.st&&data.searchTerms)?data.searchTerms:baseData(acc).searchTerms;\n"
    "  var bestKw=aiKw.filter(function(k){return k.conv>=3}).sort(function(a,b){return safeDiv(a.spend,a.conv)-safeDiv(b.spend,b.conv)})[0];",
    "var aiKw=(data.realMod&&data.realMod.kw&&data.keywords)?data.keywords:baseData(acc).keywords;",
)
add(
    "B5b AI 搜索词数据源",
    "  var stBest=baseData(acc).searchTerms.filter(function(s){return s.conv>0}).sort(function(a,b){return safeDiv(a.spend,a.conv)-safeDiv(b.spend,b.conv)})[0];",
    "  var stBest=aiSt.filter(function(s){return s.conv>0}).sort(function(a,b){return safeDiv(a.spend,a.conv)-safeDiv(b.spend,b.conv)})[0];",
    "var stBest=aiSt.filter(",
)
add(
    "B5c AI 内容机会去伪",
    "  var oemShare=baseData(acc).searchTerms.filter(function(s){return intentOf(s.term)==='OEM'||intentOf(s.term)==='制造商'}).reduce(function(a,s){return a+s.spend},0);\n"
    "  var stTot=baseData(acc).searchTerms.reduce(function(a,s){return a+s.spend},0)||1;\n"
    "  conts.push('OEM / Manufacturer 类搜索词花费占比 '+pct(oemShare/stTot,0)+'，且环比增长约 27%，但当前广告中相关文案覆盖率较低。');",
    "  var oemShare=aiSt.filter(function(s){return intentOf(s.term)==='OEM'||intentOf(s.term)==='制造商'}).reduce(function(a,s){return a+s.spend},0);\n"
    "  var stTot=aiSt.reduce(function(a,s){return a+s.spend},0)||0;\n"
    "  if(stTot>0)conts.push('OEM / Manufacturer 类搜索词花费占比 '+pct(oemShare/stTot,0)+'（'+money(oemShare)+' / '+money(stTot)+'），可考虑补一轮 OEM 主题文案。');",
    "if(stTot>0)conts.push('OEM / Manufacturer 类搜索词花费占比 '",
)
add(
    "B5d 建议行动去示例词",
    "  acts.push('新建 OEM / Private Label 主题 RSA，标题中直接使用「private label '+acc.p1+'」。');",
    "  var seedTerm=(aiKw[0]&&aiKw[0].kw)||(REAL_DATA[acc.id]&&REAL_DATA[acc.id].meta&&REAL_DATA[acc.id].meta.cat)||acc.p1;\n"
    "  acts.push('新建 OEM / Private Label 主题 RSA，标题中直接使用「private label '+seedTerm+'」。');",
    "var seedTerm=(aiKw[0]&&aiKw[0].kw)",
)


# ---------- B6. 系列表容器：账户全量系列较多，加纵向滚动 ----------
add(
    "B6 系列表滚动",
    '<div class="tbl-wrap" data-page-node-id="7qHpgSycE9hl8k1YrxblBo"><table class="tbl" id="campTbl"',
    '<div class="tbl-wrap" style="max-height:560px;overflow:auto" data-page-node-id="7qHpgSycE9hl8k1YrxblBo"><table class="tbl" id="campTbl"',
    'style="max-height:560px;overflow:auto" data-page-node-id="7qHpgSycE9hl8k1YrxblBo"',
)

# ---------- B7. 预算显示两位小数，与后台一致（¥416.00/天） ----------
add(
    "B7 预算精度",
    "    var bud=invMap[c.name]?(invMap[c.name].b>0?money(invMap[c.name].b/1e6)+'/天':'—'):'—';",
    "    var bud=invMap[c.name]?(invMap[c.name].b>0?money2(invMap[c.name].b/1e6)+'/天':'—'):'—';",
    "money2(invMap[c.name].b/1e6)",
)


def main():
    with open(PAGE, encoding="utf-8") as f:
        html = f.read()
    before = len(html)
    ok = fail = skip = 0
    for name, old, new, marker in REPL:
        if marker in html:
            print("  [skip] %s（已是新版）" % name)
            skip += 1
            continue
        if old not in html:
            print("  [失败] %s：锚点未匹配" % name)
            fail += 1
            continue
        html = html.replace(old, new, 1)
        print("  [ok] %s" % name)
        ok += 1
    if fail:
        print("\n有 %d 处未匹配，未写入文件。请检查页面是否已被其他版本改写。" % fail)
        return 1
    with open(PAGE, "w", encoding="utf-8") as f:
        f.write(html)
    print("\n已写入 %s（%d → %d 字节；ok=%d skip=%d）"
          % (PAGE, before, len(html), ok, skip))
    return 0


if __name__ == "__main__":
    sys.exit(main())
