# -*- coding: utf-8 -*-
"""
把 real_detail_generated.js（关键词/搜索词/广告/落地页/转化动作 真实明细）
注入 index.html，并改造页面数据层与 4 个看板，让它们读真实数据而不是 demo 模板。

改动清单：
 1. 注入 var REAL_DETAIL={...}
 2. realData() 把 detail 挂到返回的数据集上
 3. 新增 applyDetail/detAgg/adThemeOf/buildMM 等聚合函数
 4. renderAll 渲染前按当前时间窗口聚合明细
 5. 关键词：真实匹配类型 + 真实指标；分类筛选改为按关键词文本匹配
 6. 搜索词：改用当前数据集（原来绕开 ds() 直接读 baseData，永远显示 demo）
 7. 广告：真实 CTR / 真实 CPA（原来是凭 CTR 现编的假 CPA 公式）；素材由真实广告派生
 8. 落地页：真实展示/点击/CTR/转化/CPA（原来「会话数/参与度」是编的）
 9. 转化漏斗：改用 Google Ads 真实转化动作，并说明中间环节需 GA4/HubSpot
10. 各模块徽标：真实模块显示「真实 · 近 N 天」，仍为 demo 的显示「（示例）」

幂等：可重复执行。
"""
import io, os, re, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

WS = r"C:\Users\caleb\WorkBuddy\2026-09-15-10-47-36"
PAGE = os.path.join(WS, "repo", "index.html")
DETAIL = os.path.join(WS, "real_detail_generated.js")

html = open(PAGE, encoding="utf-8").read()
detail_js = open(DETAIL, encoding="utf-8").read().strip()

# ---------- 1. 注入 REAL_DETAIL ----------
html = re.sub(r"var REAL_DETAIL=\{.*?\};\n", "", html, flags=re.S)
i = html.index("var REAL_DATA=")
j = html.index("\n", i)
html = html[: j + 1] + detail_js + "\n" + html[j + 1:]


def sub1(old, new, label, required=True):
    """幂等替换：old 出现 1 次则替换；old 缺失但 new 已存在则跳过；
    都不匹配时 required 则报错，否则警告跳过（页面已被更新的改造取代）。"""
    global html
    if new in html:
        print("[skip] %s：已是新版" % label)
        return
    n = html.count(old)
    if n == 1:
        html = html.replace(old, new, 1)
    elif required:
        raise SystemExit("[失败] %s：锚点出现 %d 次（应为 1 次）" % (label, n))
    else:
        print("[warn] %s：锚点未匹配且新版未检出，跳过（页面代码可能已被更新版本取代）" % label)


# ---------- 2. realData 挂载 detail ----------
sub1(
    "landing:base.landing,mm:base.mm,funnelRates:base.funnelRates,real:true,",
    "landing:base.landing,mm:base.mm,funnelRates:base.funnelRates,"
    "detail:(typeof REAL_DETAIL!=='undefined'&&REAL_DETAIL[acc.id])||null,real:true,",
    "realData 挂载 detail",
)

# ---------- 3. 新增聚合函数 ----------
DETAIL_FUNCS = r"""
/* ---- 明细看板：REAL_DETAIL → keywords / searchTerms / ads / landing / ca ---- */
function detAgg(blk,shift,range){
  var n=blk.n.length,out=new Array(n);
  for(var i=0;i<n;i++)out[i]={i:i,impr:0,clicks:0,micros:0,conv:0};
  var r=blk.r;
  for(var j=0;j<r.length;j++){
    var row=r[j],d=row[0]+shift;
    if(d<0||d>range-1)continue;
    var e=out[row[1]];if(!e)continue;
    e.impr+=row[2];e.clicks+=row[3];e.micros+=row[4];e.conv+=row[5];
  }
  return out.filter(function(e){return e.impr||e.clicks||e.micros||e.conv});
}
function detSort(a){return a.slice().sort(function(x,y){return y.micros-x.micros})}
function adThemeOf(name){
  var s=String(name||'').toLowerCase();
  if(/oem|private label|custom|odm/.test(s))return 'OEM';
  if(/certif|fda|ce |iso|astm|en ?\d/.test(s))return '认证';
  if(/price|factory direct|cheap|wholesale|bulk|cost|save/.test(s))return '价格';
  if(/year|experience|since \d|trusted|professional/.test(s))return '信任';
  if(/manufactur|factory|supplier|producer/.test(s))return '制造商';
  return '产品';
}
function mmTokens(s){
  return String(s||'').toLowerCase().replace(/[^a-z0-9 ]/g,' ').split(/\s+/)
    .filter(function(w){return w.length>3});
}
function buildMM(kws,ads,lps){
  if(!kws||!kws.length||!ads||!ads.length||!lps||!lps.length)return null;
  var out=[],usedAd={};
  for(var i=0;i<kws.length&&out.length<3;i++){
    var tk=mmTokens(kws[i].kw);if(!tk.length)continue;
    var adIdx=0,adBest=-1;
    for(var j=0;j<ads.length&&j<12;j++){
      if(usedAd[j])continue;
      var ta=mmTokens(ads[j].name),sc=0;
      for(var x=0;x<tk.length;x++)if(ta.indexOf(tk[x])>=0)sc++;
      if(sc>adBest){adBest=sc;adIdx=j}
    }
    usedAd[adIdx]=1;
    var lpIdx=0,lpBest=-1;
    for(var k=0;k<lps.length&&k<8;k++){
      var tl=mmTokens(lps[k].lp),sl=0;
      for(var y=0;y<tk.length;y++)if(tl.indexOf(tk[y])>=0)sl++;
      if(sl>lpBest){lpBest=sl;lpIdx=k}
    }
    var tot=Math.max(0,adBest)+Math.max(0,lpBest);
    out.push({kw:kws[i].kw,ad:ads[adIdx].name,lp:lps[lpIdx].lp,
      score:tot>=3?'Best':tot>=1?'Good':'Poor'});
  }
  return out;
}
function applyDetail(data,range){
  data.realMod=null;
  var d=data.detail;if(!d)return false;
  var shift=Math.max(0,Math.round((today0()-new Date(REAL_EPOCH+'T00:00:00'))/864e5));
  var win=Math.min(range||30,d.win||120),mod=data.realMod={win:win};
  /* 注意：只要该账户有这个模块的真实数据，就一律覆盖 demo ——
     哪怕当前窗口内为空也要置空，否则休眠账户会显示示例模板数字 */
  if(d.kw){var a=detSort(detAgg(d.kw,shift,win));mod.kw=1;
    data.keywords=a.map(function(e){return {kw:d.kw.n[e.i],
      match:(d.kw.m&&d.kw.m[e.i])||'—',impr:e.impr,clicks:e.clicks,
      spend:e.micros/1e6,conv:e.conv}})}
  if(d.st){var b=detSort(detAgg(d.st,shift,win));mod.st=1;
    data.searchTerms=b.map(function(e){return {term:d.st.n[e.i],
      impr:e.impr,clicks:e.clicks,spend:e.micros/1e6,conv:e.conv}})}
  if(d.ad){var c=detSort(detAgg(d.ad,shift,win));mod.ad=1;
    data.ads=c.map(function(e){return {name:d.ad.n[e.i],
      type:(d.ad.t&&d.ad.t[e.i])||'',impr:e.impr,clicks:e.clicks,
      ctr:e.impr?e.clicks/e.impr:0,conv:e.conv,spend:e.micros/1e6}});
    data.assets=data.ads.filter(function(x){return x.impr>=50}).map(function(x){
      return {asset:x.name.slice(0,40),theme:adThemeOf(x.name),ctr:x.ctr,
        cvr:x.clicks?x.conv/x.clicks:0}})}
  if(d.lp){var p=detSort(detAgg(d.lp,shift,win));mod.lp=1;
    data.landing=p.map(function(e){return {lp:d.lp.n[e.i],
      impr:e.impr,clicks:e.clicks,adsClick:e.clicks,conv:e.conv,spend:e.micros/1e6,
      cpa:e.conv?e.micros/1e6/e.conv:NaN}})}
  if(d.ca){
    var agg={},r2=d.ca.r;
    for(var i2=0;i2<r2.length;i2++){
      var row=r2[i2],dd=row[0]+shift;
      if(dd<0||dd>win-1)continue;
      var e2=agg[row[1]];if(!e2)e2=agg[row[1]]={i:row[1],conv:0,all:0};
      e2.conv+=row[2];e2.all+=row[3];
    }
    var arr=[];for(var k2 in agg)if(agg.hasOwnProperty(k2))arr.push(agg[k2]);
    arr.sort(function(x,y){return y.conv-x.conv});
    if(arr.length){data.ca=arr.map(function(e){return {name:d.ca.n[e.i],
      conv:e.conv,all:e.all}});mod.ca=1}
  }
  if(!mod.kw&&!mod.st&&!mod.ad&&!mod.lp&&!mod.ca){
    /* 有 detail 块但一个模块都没数据：清空 demo，避免把示例当成真实 */
    data.keywords=[];data.searchTerms=[];data.ads=[];data.assets=[];data.landing=[];data.ca=null;
  }
  if(mod.kw&&mod.ad&&mod.lp&&data.keywords.length&&data.ads.length&&data.landing.length){
    var mm=buildMM(data.keywords,data.ads,data.landing);if(mm)data.mm=mm}
  return true;
}

"""
if "function applyDetail(data,range)" in html:
    print("[skip] 明细聚合函数已存在，不重复插入")
else:
    sub1("/* ================= 实时 API 拉取（可选，填 REAL_API_URL 后生效） ================= */",
         DETAIL_FUNCS.lstrip("\n") + "/* ================= 实时 API 拉取（可选，填 REAL_API_URL 后生效） ================= */",
         "插入明细聚合函数")

# ---------- 4. renderAll 调用 applyDetail ----------
sub1("  var acc=accById(S.account),data=ds(acc),f=S.filters;\n  renderFilterOptions(data);",
     "  var acc=accById(S.account),data=ds(acc),f=S.filters;\n  applyDetail(data,S.range);\n  renderFilterOptions(data);",
     "renderAll 调用 applyDetail")

# ---------- 5. 关键词筛选 ----------
sub1("""  var f=S.filters,kws=data.keywords.filter(function(k){
    if(f.category&&k.kw.indexOf(f.category.toLowerCase().split(' ')[0])<0&&k.kw.indexOf(accById(S.account).p1)<0)return false;return true});""",
     """  var f=S.filters,kws=data.keywords;
  if(f.category){
    var tk=f.category.toLowerCase().split(' ')[0];
    var fl=kws.filter(function(k){return k.kw.toLowerCase().indexOf(tk)>=0});
    if(fl.length)kws=fl;
  }
  if(kws.length>50)kws=kws.slice(0,50);""",
     "关键词筛选改按文本匹配")

# ---------- 6. 搜索词改用当前数据集 ----------
sub1("function renderSearchTerms(){\n  var f=S.filters,sts=baseData(accById(S.account)).searchTerms;",
     "function renderSearchTerms(data){\n  var f=S.filters,sts=data.searchTerms;if(sts.length>50)sts=sts.slice(0,50);",
     "搜索词改用当前数据集")
sub1("  renderSearchTerms();", "  renderSearchTerms(data);", "renderAll 传入 data 给搜索词")

# ---------- 7. 广告：真实 CPA ----------
sub1("""  ads.forEach(function(a){a.cvr=safeDiv(a.conv,a.clicks);a.cpa=a.conv>0?Math.round(60+80*(0.06-a.ctr)*50+a.cvr*400):NaN;
    a.cpa=a.conv>0?Math.max(40,Math.round(140-a.ctr*800-a.cvr*900)):NaN});""",
     """  var adReal=!!(data.realMod&&data.realMod.ad);
  ads.forEach(function(a){a.cvr=safeDiv(a.conv,a.clicks);
    a.cpa=adReal?safeDiv(a.spend,a.conv)
      :(a.conv>0?Math.max(40,Math.round(140-a.ctr*800-a.cvr*900)):NaN)});""",
     "广告 CPA 改用真实花费")

# ---------- 8. 落地页：真实列 ----------
sub1("""  var html=['<thead><tr><th>落地页</th><th class="num">会话数</th><th class="num">广告点击</th><th class="num">参与度</th><th class="num">转化</th><th class="num">CVR</th><th class="num">CPA</th></tr></thead><tbody>'];
  lps.forEach(function(p){var cvr=safeDiv(p.conv,p.adsClick);
    html.push('<tr><td><b>'+esc(p.lp)+'</b></td><td class="num">'+int(p.sessions)+'</td><td class="num">'+int(p.adsClick)+'</td><td class="num">'+pct(p.engagement,0)+'</td><td class="num">'+p.conv+'</td><td class="num">'+pct(cvr)+'</td><td class="num">'+money(p.cpa)+'</td></tr>')});""",
     """  var lpReal=!!(data.realMod&&data.realMod.lp);
  var html=[lpReal
    ?'<thead><tr><th>落地页</th><th class="num">展示</th><th class="num">点击</th><th class="num">CTR</th><th class="num">转化</th><th class="num">CVR</th><th class="num">CPA</th></tr></thead><tbody>'
    :'<thead><tr><th>落地页</th><th class="num">会话数</th><th class="num">广告点击</th><th class="num">参与度</th><th class="num">转化</th><th class="num">CVR</th><th class="num">CPA</th></tr></thead><tbody>'];
  lps.forEach(function(p){var cvr=safeDiv(p.conv,p.adsClick),ctr=safeDiv(p.adsClick,p.impr);
    if(lpReal)html.push('<tr><td><b>'+esc(p.lp)+'</b></td><td class="num">'+int(p.impr)+'</td><td class="num">'+int(p.adsClick)+'</td><td class="num">'+pct(ctr)+'</td><td class="num">'+p.conv+'</td><td class="num">'+pct(cvr)+'</td><td class="num">'+money(p.cpa)+'</td></tr>');
    else html.push('<tr><td><b>'+esc(p.lp)+'</b></td><td class="num">'+int(p.sessions)+'</td><td class="num">'+int(p.adsClick)+'</td><td class="num">'+pct(p.engagement,0)+'</td><td class="num">'+p.conv+'</td><td class="num">'+pct(cvr)+'</td><td class="num">'+money(p.cpa)+'</td></tr>')});""",
     "落地页改用真实指标")

# ---------- 9. 漏斗：真实转化动作 ----------
sub1("""function renderFunnel(rows,data){
  var clicks=sumRows(rows).clicks;
  var rates=data.funnelRates,stages=[clicks];""",
     """function renderFunnel(rows,data){
  var clicks=sumRows(rows).clicks;
  if(data.ca&&data.ca.length){
    var totConv=0,totAll=0;
    data.ca.forEach(function(c){totConv+=c.conv;totAll+=c.all});
    var vals=[clicks],rates=[],names=['广告点击'];
    if(totAll>totConv+0.05){vals.push(totAll);rates.push(safeDiv(totAll,clicks));names.push('全部转化')}
    vals.push(totConv);rates.push(safeDiv(totConv,vals[vals.length-1]));names.push('主转化');
    $('funnelBox').innerHTML=svgFunnel(vals,rates,-1,names);
    var list=data.ca.map(function(c){
      return '<li><span>'+esc(c.name)+'</span><span class="v">'+num1(c.conv)+' 转化'
        +(c.all&&Math.abs(c.all-c.conv)>0.05?'（含跨设备 '+num1(c.all)+'）':'')+'</span></li>'}).join('');
    $('funnelDiag').innerHTML='<b>诊断：</b>Google Ads 真实转化：'+int(clicks)+' 点击 → '
      +num1(totConv)+' 转化，整体 CVR '+pct(safeDiv(totConv,clicks))
      +'。<ul class="mlist" style="margin-top:6px">'+list+'</ul>'
      +'<div class="hintbox">中间环节（落地页参与 / 表单开始 / MQL / SQL）不在 Google Ads 口径内，需接入 GA4 或 HubSpot 才有真实数据；本卡片当前只展示 Google Ads 侧真实转化，不再用示例率推算。</div>';
    return;
  }
  var rates=data.funnelRates,stages=[clicks];""",
     "漏斗改用真实转化动作", required=False)

# ---------- 10. svgFunnel 支持自定义阶段名 ----------
sub1("function svgFunnel(values,rates,weakIdx){",
     "function svgFunnel(values,rates,weakIdx,names){", "svgFunnel 增加阶段名参数", required=False)
sub1("""font-weight="700">'+esc(FUNNEL_STAGES[i])+'</text>'""",
     """font-weight="700">'+esc(names&&names[i]?names[i]:FUNNEL_STAGES[i])+'</text>'""",
     "svgFunnel 使用传入阶段名", required=False)

# ---------- 10b. 真实数据为空时给明确提示（不再回退到示例模板） ----------
EMPTY_TIP = ('<tbody><tr><td style="color:var(--ink2);padding:14px 8px">'
             '当前时间窗口内 Google Ads 没有该维度的真实数据'
             '（账户可能已停投，或该周期为纯 PMax / 展示广告投放）。</td></tr></tbody>')

sub1("  if(kws.length>50)kws=kws.slice(0,50);\n  var medCvr=0.03;",
     "  if(kws.length>50)kws=kws.slice(0,50);\n"
     "  if(!kws.length){$('kwTbl').innerHTML='%s';return}\n  var medCvr=0.03;" % EMPTY_TIP,
     "关键词空态", required=False)

sub1("  var f=S.filters,sts=data.searchTerms;if(sts.length>50)sts=sts.slice(0,50);",
     "  var f=S.filters,sts=data.searchTerms;if(sts.length>50)sts=sts.slice(0,50);\n"
     "  if(!sts.length){$('stTbl').innerHTML='%s';return}" % EMPTY_TIP,
     "搜索词空态", required=False)

sub1("      :(a.conv>0?Math.max(40,Math.round(140-a.ctr*800-a.cvr*900)):NaN)});",
     "      :(a.conv>0?Math.max(40,Math.round(140-a.ctr*800-a.cvr*900)):NaN)});\n"
     "  if(!ads.length){$('topAdTbl').innerHTML=$('botAdTbl').innerHTML=$('adTbl').innerHTML='%s';\n"
     "    $('assetTbl').innerHTML='%s';return}" % (EMPTY_TIP, EMPTY_TIP),
     "广告空态", required=False)

sub1("  var lps=data.landing;\n  var lpReal=",
     "  var lps=data.landing;\n"
     "  if(!lps.length){$('lpTbl').innerHTML='%s';$('mmBox').innerHTML='';return}\n"
     "  var lpReal=" % EMPTY_TIP,
     "落地页空态", required=False)

# ---------- 11. 各模块徽标 ----------
sub1("""  var tag=impOn?'':'（示例）';
  $('kwDemoTag').textContent=tag;$('stDemoTag').textContent=tag;$('adDemoTag').textContent=tag;$('lpDemoTag').textContent=tag;""",
     """  var tag=impOn?'':'（示例）',rm=data.realMod;
  function mtag(ok){return impOn?'':(ok?'（真实 · 近 '+((rm&&rm.win)||30)+' 天）':tag)}
  $('kwDemoTag').textContent=mtag(rm&&rm.kw);
  $('stDemoTag').textContent=mtag(rm&&rm.st);
  $('adDemoTag').textContent=mtag(rm&&rm.ad);
  $('lpDemoTag').textContent=mtag(rm&&rm.lp);""",
     "各模块徽标区分真实/示例", required=False)

open(PAGE, "w", encoding="utf-8").write(html)
print("已注入 REAL_DETAIL 并完成页面改造：%s（%.0f KB）" % (PAGE, len(html.encode('utf-8')) / 1024.0))
