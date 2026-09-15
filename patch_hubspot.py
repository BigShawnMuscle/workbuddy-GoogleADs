# -*- coding: utf-8 -*-
"""把 HubSpot 真实漏斗数据注入 index.html 并改造转化漏斗卡片（幂等）。

依赖：先跑 refresh_hubspot.py 生成 hubspot_data_generated.js
用法：python patch_hubspot.py
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "index.html")
DATA = os.path.join(HERE, "hubspot_data_generated.js")

MARK = "var HUBSPOT="

with io.open(PAGE, "r", encoding="utf-8") as f:
    html = f.read()
with io.open(DATA, "r", encoding="utf-8") as f:
    blob = f.read().strip()
if not blob.startswith(MARK):
    sys.exit("hubspot_data_generated.js 格式不对，需要先跑 refresh_hubspot.py")


def sub1(old, new, label):
    """严格单次替换，锚点不唯一就报错，避免幂等破坏。"""
    global html
    n = html.count(old)
    if n != 1:
        sys.exit("[%s] 锚点出现 %d 次（期望 1 次），已中止" % (label, n))
    html = html.replace(old, new, 1)
    print("  ✓ " + label)


# ── 1. 注入 HUBSPOT 数据（先清旧，再插到 REAL_DATA 之前） ──────────────────────
html = re.sub(r"var HUBSPOT=\{.*?\};\n", "", html, flags=re.S)
anchor = "\nvar REAL_DATA="
if anchor not in html:
    sys.exit("找不到 REAL_DATA 注入点")
html = html.replace(anchor, "\n" + blob + anchor, 1)
print("  ✓ 注入 HUBSPOT（%d 字节）" % len(blob))

# ── 2. 用真实数据初始化 S.hubspot（原来只能从资料库云端取，一直是空的） ─────────
sub1(
    "cloudOpt:{},hubspot:null};",
    "cloudOpt:{},hubspot:(typeof HUBSPOT!=='undefined'&&HUBSPOT.src)||null};",
    "S.hubspot 初始化为内置真实数据",
)

# ── 3. 漏斗卡片：新增「广告系列 → 线索归因」区块 ───────────────────────────────
CAMP_BLOCK = """    <div class="hintbox" id="hsDiag" style="margin-top:12px" data-page-node-id="f8pFy7TZAxLMCAc7JgauIl"></div>
    <div class="subhead" style="margin-top:20px">Google Ads 广告系列 → HubSpot 线索归因<span class="mininote" id="hsCampTag"></span></div>
    <div class="desc">按 HubSpot 联系人携带的广告系列名与 Google Ads 广告系列归一化精确匹配；未匹配部分多为 UTM 自定义名称或自动标记流量，单独列出以免虚增。</div>
    <div class="tbl-wrap"><table class="tbl" id="hsCampTbl"></table></div>
  </div>"""
sub1(
    """    <div class="hintbox" id="hsDiag" style="margin-top:12px" data-page-node-id="f8pFy7TZAxLMCAc7JgauIl"></div>
  </div>""",
    CAMP_BLOCK,
    "漏斗卡片新增广告系列归因表",
)

# ── 4. 文案同步（去掉写死的 4.3% 与「资料库同步」说法） ────────────────────────
sub1(
    "线索质量基于 HubSpot 真实线索数据评级（付费来源 MQL→SQL 整体 4.3%，详见转化漏斗卡片）",
    "线索质量基于 HubSpot 真实线索数据评级（付费搜索广告系列级 MQL+SQL 占比，详见转化漏斗卡片）",
    "广告系列表说明去硬编码",
)
sub1(
    "与上方 Google Ads 点击漏斗拼接成完整链路；数据经 HubSpot 桥接自动同步至资料库数据表。",
    "与上方 Google Ads 点击漏斗拼接成完整链路；数据由 HubSpot Private App 直连 CRM v3 接口每日同步。",
    "HubSpot 表说明改为直连同步",
)

# ── 5. 线索质量评级改为读取 HubSpot 广告系列级真实数据 ─────────────────────────
sub1(
    "function leadQuality(role){return {brand:'高',growth:'高',steady:'中',waste:'低',content:'低',risk:'中',imported:'中'}[role]||'中'}",
    """function leadQuality(role,camp){
  var HM=hsCampMap();
  if(HM&&camp&&camp.name){
    var e=HM[normCamp(camp.name)];
    if(e&&e.lead>=3){
      var r=(e.mql+e.sql)/e.lead;
      if(r>=0.12)return '高';if(r>=0.05)return '中';return '低';
    }
  }
  return {brand:'高',growth:'高',steady:'中',waste:'低',content:'低',risk:'中',imported:'中'}[role]||'中'}""",
    "leadQuality 接入 HubSpot 广告系列数据",
)
sub1(
    "var camps=campAgg(rows,data).map(function(c){c.leadQ=leadQuality(c.role);return c});",
    "var camps=campAgg(rows,data).map(function(c){c.leadQ=leadQuality(c.role,c);return c});",
    "leadQuality 调用点传广告系列",
)

# ── 6. 新增 HubSpot 取数工具函数 + 重写 renderFunnel + 新增归因表渲染 ──────────
FUNCS = r"""/* ================= HubSpot 真实漏斗（Private App 直连 CRM v3） ================= */
/* 归一化广告系列名：Google 侧 Gloves_Eur ↔ HubSpot 侧 gloves_eur；HubSpot 部分取值带多余 {} */
function normCamp(n){return String(n||'').toLowerCase().replace(/[\s_\-\/{}]+/g,'')}
function hsShift(){
  if(typeof HUBSPOT==='undefined'||!HUBSPOT||!HUBSPOT.ep)return 0;
  return Math.max(0,Math.round((today0()-new Date(HUBSPOT.ep+'T00:00:00'))/864e5));
}
function hsSum(arr,shift,range){
  var t=0;if(!arr)return 0;
  for(var i=0;i<arr.length;i++){var d=arr[i][0]+shift;if(d>=0&&d<=range-1)t+=arr[i][1]}
  return t;
}
function hsCampMap(){
  if(typeof HUBSPOT==='undefined'||!HUBSPOT||!HUBSPOT.camp||!HUBSPOT.camp.length)return null;
  var m={};
  for(var i=0;i<HUBSPOT.camp.length;i++){
    var c=HUBSPOT.camp[i],k=normCamp(c.n);if(!k)continue;
    if(!m[k])m[k]={n:c.n,lead:0,mql:0,sql:0};
    m[k].lead+=c.lead;m[k].mql+=c.mql;m[k].sql+=c.sql;
  }
  return m;
}
/* HubSpot 线索是 Portal 级口径，无法按广告账户拆分 → 点击侧同样取 5 个账户合计，保持口径一致 */
function hsAllClicks(range){
  var t=0;
  for(var i=0;i<ACCOUNTS.length;i++){
    var d=ds(ACCOUNTS[i]);if(!d)continue;
    t+=sumRows(inWin(d.rows,S.filters,0,range-1,ACCOUNTS[i],d)).clicks;
  }
  return t;
}
function renderFunnel(rows,data){
  var acc=accById(S.account);
  var totConv=0,totAll=0;
  if(data.ca&&data.ca.length)data.ca.forEach(function(x){totConv+=x.conv;totAll+=x.all});
  var hs=(typeof HUBSPOT!=='undefined'&&HUBSPOT&&HUBSPOT.d)?HUBSPOT:null;
  if(hs){
    var sh=hsShift(),R=S.range;
    var v=hsSum(hs.d.v,sh,R),c=hsSum(hs.d.c,sh,R),l=hsSum(hs.d.l,sh,R),
        m=hsSum(hs.d.m,sh,R),s=hsSum(hs.d.s,sh,R);
    var clicks=hsAllClicks(R);
    if(v||c||m||s){
      var vals=[clicks,v,c,m,s];
      var names=['Google Ads 点击（5 账户合计）','落地页访客（可追踪）','表单提交','MQL','SQL'];
      var rates=[];
      for(var i=1;i<vals.length;i++)rates.push(safeDiv(vals[i],vals[i-1]));
      /* 最薄弱环节只在 HubSpot 内部三步里找：点击→访客 受匿名流量不可追踪影响，不参与比较 */
      var weak=1,wv=2;
      for(var i=1;i<rates.length;i++){if(rates[i]<wv){wv=rates[i];weak=i}}
      $('funnelBox').innerHTML=svgFunnel(vals,rates,weak,names);
      var advice=['落地页到表单的转化偏低：检查 CTA 位置、表单字段数量与移动端输入体验。',
        '表单提交转 MQL 偏低：核对 MQL 评分规则是否过严，或表单缺少用于分级的字段（国家 / 公司规模 / 采购意向）。',
        'MQL 转 SQL 偏低：对齐销售跟进 SLA 与 MQL 定义，避免线索在销售侧长时间无人跟进。'];
      var caList=data.ca&&data.ca.length?('<ul class="mlist" style="margin-top:6px">'+data.ca.map(function(x){
        return '<li><span>'+esc(x.name)+'</span><span class="v">'+num1(x.conv)+'</span></li>'}).join('')+'</ul>'):'';
      $('funnelDiag').innerHTML='<b>诊断：</b>近 '+R+' 天（截至 '+esc(hs.end)+'，HubSpot Portal '+esc(hs.portal)+'）'
        +'付费搜索口径新增 '+int(l)+' 个线索、'+int(m)+' 个 MQL、'+int(s)+' 个 SQL；'
        +'最薄弱环节是「'+names[weak]+' → '+names[weak+1]+'」（'+pct(rates[weak],0)+'）。'+advice[weak-1]
        +'<ul class="mlist" style="margin-top:6px">'
        +'<li>点击 → 表单提交整体 '+pct(safeDiv(c,clicks))+'（'+int(clicks)+' 次点击 → '+int(c)+' 次表单提交）</li>'
        +'<li>Google Ads 侧同期转化 '+num1(totConv)+'（当前账户 '+esc(acc.name)+'）</li>'
        +'</ul>'+caList
        +'<div class="hintbox">口径说明：HubSpot 只记录最终留资或被识别的访客，未留资的匿名点击不在 CRM 内，'
        +'因此「点击 → 访客」不是真实到达率，已排除在最薄弱环节判断之外；'
        +'SQL 之后的商机与成交需在 HubSpot 维护 Deal 才会出现在漏斗中。</div>';
      return;
    }
  }
  var clicks=sumRows(rows).clicks;
  if(data.ca&&data.ca.length){
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
      +'<div class="hintbox">HubSpot 侧尚无本窗口数据，本卡片当前只展示 Google Ads 侧真实转化。</div>';
    return;
  }
  var rates=data.funnelRates,stages=[clicks];
  for(var i=0;i<rates.length;i++)stages.push(Math.round(stages[i]*rates[i]));
  var weak=0,weakGap=0;
  for(var i=0;i<rates.length;i++){var gap=1-rates[i]/FUNNEL_BENCH[i];if(gap>weakGap){weakGap=gap;weak=i}}
  $('funnelBox').innerHTML=svgFunnel(stages,rates,weak);
  var stageNames=['广告点击 → 落地页参与','落地页参与 → 表单开始','表单开始 → 表单提交','表单提交 → 合格线索','合格线索 → SQL'];
  var advice=['流量到达落地页的参与率偏低：检查页面打开速度与首屏内容相关性。','有点击但表单启动率低：落地页 CTA 与表单位置需要前置、加引导。','表单启动后提交率低：<b>优先精简表单字段</b>（减少非必填项）、优化移动端输入体验。','提交后合格线索占比低：检查线索来源质量与表单筛选问题设置。','合格线索转 SQL 偏低：与销售跟进 SLA、线索评分规则对齐。'];
  $('funnelDiag').innerHTML='<b>诊断：</b>最薄弱环节是「'+stageNames[weak]+'」（'+pct(rates[weak],0)+'，基准 '+pct(FUNNEL_BENCH[weak],0)+'）。'+advice[weak];
}
function renderHubSpotCamp(data){
  var el=$('hsCampTbl'),tag=$('hsCampTag');
  if(!el)return;
  var HM=hsCampMap();
  if(!HM){
    el.innerHTML='<tr><td style="color:var(--ink2);padding:14px 8px">HubSpot 暂无广告系列级归因数据。</td></tr>';
    if(tag)tag.textContent='';return;
  }
  var rows=[],matched=0,total=0;
  Object.keys(HM).forEach(function(k){total+=HM[k].lead});
  (data.campaigns||[]).forEach(function(c){
    var e=HM[normCamp(c.name)];if(!e)return;
    rows.push({n:c.name,lead:e.lead,mql:e.mql,sql:e.sql});matched+=e.lead;
  });
  rows.sort(function(a,b){return b.lead-a.lead});
  var h=['<thead><tr><th>广告系列</th><th class="num">线索</th><th class="num">MQL</th><th class="num">SQL</th>'
        +'<th class="num">线索 → MQL+SQL</th></tr></thead><tbody>'];
  if(!rows.length){
    h.push('<tr><td colspan="5" style="color:var(--ink2);padding:14px 8px">当前账户的广告系列在 HubSpot 中没有匹配的线索记录。</td></tr>');
  }
  rows.slice(0,15).forEach(function(r){
    var q=safeDiv(r.mql+r.sql,r.lead);
    h.push('<tr><td><b>'+esc(r.n)+'</b></td><td class="num">'+int(r.lead)+'</td><td class="num">'+int(r.mql)
      +'</td><td class="num">'+int(r.sql)+'</td><td class="num">'+pct(q)+'</td></tr>');
  });
  h.push('</tbody>');
  el.innerHTML=h.join('');
  if(tag)tag.textContent='本账户覆盖 '+int(matched)+' / 全站 '+int(total)+' 个付费搜索线索'
    +'（'+pct(safeDiv(matched,total))+'）· 近 '+(HUBSPOT.win||180)+' 天快照';
}
"""
old_funnel_start = "function renderFunnel(rows,data){"
old_funnel_end = "\nfunction renderHubSpot(){"
i = html.find(old_funnel_start)
j = html.find(old_funnel_end, i)
if i < 0 or j < 0:
    sys.exit("找不到 renderFunnel 代码块")
html = html[:i] + FUNCS + html[j:]
print("  ✓ 重写 renderFunnel + 新增 HubSpot 归因渲染")

sub1("  renderFunnel(rows,data);\n  renderHubSpot();\n",
     "  renderFunnel(rows,data);\n  renderHubSpot();\n  renderHubSpotCamp(data);\n",
     "renderAll 挂载归因表")

with io.open(PAGE, "w", encoding="utf-8") as f:
    f.write(html)
print("\n完成：index.html 已接入 HubSpot 真实漏斗（%.1f KB）" % (len(html) / 1024))
