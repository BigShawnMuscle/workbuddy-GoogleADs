# -*- coding: utf-8 -*-
"""把重新拉取的真实数据注入 index.html，并修复数据层逻辑。"""
import io, os, re, json, sys, subprocess

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
WS = r"C:\Users\caleb\WorkBuddy\2026-09-15-10-47-36"
PAGE = os.path.join(WS, "repo", "index.html")
NODE = r"C:\Users\caleb\.workbuddy\binaries\node\versions\22.22.2-2\node.exe"

with open(PAGE, encoding="utf-8") as f:
    html = f.read()

meta = json.load(open(os.path.join(WS, "accounts_meta.json"), encoding="utf-8"))
EPOCH = meta["epoch"]          # 2026-09-15
DATA_END = meta["dataEnd"]     # 2026-09-14

# ---------- 1. 生成 REAL_DATA（经 node 转成严格 JSON，避免转义问题） ----------
conv_js = r"""
const fs=require('fs');
eval(fs.readFileSync('real_data_generated.js','utf8'));
fs.writeFileSync('real_data.json', JSON.stringify(REAL_DATA_GEN));
console.log('ok');
"""
with open(os.path.join(WS, "conv.js"), "w", encoding="utf-8") as f:
    f.write(conv_js)
subprocess.run([NODE, "conv.js"], cwd=WS, check=True)
real_json = open(os.path.join(WS, "real_data.json"), encoding="utf-8").read()

print("REAL_DATA JSON %.1f KB" % (len(real_json.encode("utf-8")) / 1024.0))

# ---------- 2. 替换 REAL_DATA 块 ----------
start = html.index("var REAL_DATA=")
ob = html.index("{", start)
depth, k = 0, ob
while True:                       # 花括号配平，兼容单行 / 多行两种写法
    if html[k] == "{":
        depth += 1
    elif html[k] == "}":
        depth -= 1
        if depth == 0:
            break
    k += 1
end = k + 1
while end < len(html) and html[end] in "; \r\n":   # 吃掉结尾分号与换行
    end += 1
html = html[:start] + "var REAL_DATA=" + real_json + ";\n" + html[end:]
print("[ok] 替换 REAL_DATA")

# ---------- 3. REAL_EPOCH / 数据截止 ----------
html = re.sub(r"var REAL_EPOCH='[\d-]+';", "var REAL_EPOCH='%s';" % EPOCH, html)
if "var REAL_DATA_END=" in html:
    html = re.sub(r"var REAL_DATA_END='[\d-]+';", "var REAL_DATA_END='%s';" % DATA_END, html)
else:
    html = html.replace("var REAL_EPOCH='%s';" % EPOCH,
                        "var REAL_EPOCH='%s';\nvar REAL_DATA_END='%s';" % (EPOCH, DATA_END), 1)
print("[ok] REAL_EPOCH=%s  REAL_DATA_END=%s" % (EPOCH, DATA_END))

# ---------- 3b. 花费以 micros 整数存储，加载时换算，避免逐行四舍五入误差 ----------
old_rows = "for(var i=0;i<rd.r.length;i++){var r=rd.r[i];rows[i]=[r[0]+shift,r[1],r[2],r[3],r[4],r[5],r[6],r[7],r[8]];}"
new_rows = "for(var i=0;i<rd.r.length;i++){var r=rd.r[i];rows[i]=[r[0]+shift,r[1],r[2],r[3],r[4],r[5],r[6],r[7]/1e6,r[8]];}"
if old_rows in html:  # 首次改造；后续运行页面已是 micros 版本
    html = html.replace(old_rows, new_rows, 1)
    html = html.replace("if(oldR)for(var k=0;k<oldR.length;k++)curSpend+=oldR[k][7]||0;",
                        "if(oldR)for(var k=0;k<oldR.length;k++)curSpend+=(oldR[k][7]||0)/1e6;", 1)
    html = html.replace(
        "/* ================= 内置真实数据（rows=[距epoch天数,系列,组,设备,动作,展示,点击,花费,转化]） ================= */",
        "/* ================= 内置真实数据（rows=[距epoch天数,系列,组,设备,动作,展示,点击,花费(micros),转化]，加载时 /1e6 换算） ================= */", 1)
    print("[ok] 花费改用 micros 整数，零精度损失")
else:
    assert new_rows in html, "realData 行构建既非旧版也非 micros 版"
    print("[skip] 花费已是 micros 整数存储")

# ---------- 4. 设备维度补齐 ----------
html = html.replace("var DEVICES=['Desktop','Mobile','Tablet'];",
                    "var DEVICES=['Desktop','Mobile','Tablet','Connected TV','Other'];")
print("[ok] DEVICES 扩展为 5 项")

# ---------- 4b. 设备下拉补齐 Connected TV / Other ----------
old_dev = '<option value="Tablet" data-page-node-id="xGJEVV9OAslpGtaCDv76sT">Tablet 平板端</option>'
new_dev = (old_dev +
           '<option value="Connected TV" data-page-node-id="devCTv">Connected TV 联网电视</option>'
           '<option value="Other" data-page-node-id="devOther">Other 其他</option>')
if old_dev in html and 'devCTv' not in html:
    html = html.replace(old_dev, new_dev, 1)
    print("[ok] 设备下拉补齐 5 项")
elif 'devCTv' in html:
    print("[skip] 设备下拉已补齐")
else:
    print("[warn] 设备下拉锚点未匹配")

# ---------- 5. 账户列表：补齐 MCC 下全部 5 个 ENABLED 账户 ----------
short_name = {"basic": "Basic Medical", "gloves": "Intco Gloves", "medical": "Intco Medical",
              "wheelchair": "Intco Wheelchair", "healthcare": "Intco Healthcare"}
by_key = {a["key"]: a for a in meta["accounts"]}


def fmt_cid(c):
    return "%s-%s-%s" % (c[:3], c[3:6], c[6:])


def camp_block(label, cat, terms):
    b, g, n, s = terms
    return """[
   {name:'Search - %s - Brand',type:'Search',market:'United States',brand:'Brand',cat:'%s',role:'brand'},
   {name:'Search - %s - US',type:'Search',market:'United States',brand:'Non-brand',cat:'%s',role:'growth'},
   {name:'PMax - %s - US',type:'PMax',market:'United States',brand:'Non-brand',cat:'%s',role:'waste'},
   {name:'Search - %s - DE',type:'Search',market:'Germany',brand:'Non-brand',cat:'%s',role:'steady'},
   {name:'Display - %s Remarketing - Global',type:'Display',market:'Global',brand:'Non-brand',cat:'%s',role:'content'},
   {name:'Search - %s OEM - US',type:'Search',market:'United States',brand:'Non-brand',cat:'%s',role:'risk'}]""" \
        % (label, cat, b, cat, label, cat, g, cat, label, cat, n, cat)



ACCOUNT_DEFS = [
    ("basic", "Basic Medical", 0.85, 480, "basic medical",
     ("Exam Nitrile Gloves", "Face Masks", "Protective Apparel", "Wound Care")),
    ("gloves", "Intco Gloves", 1.15, 620, "intco gloves",
     ("Nitrile Gloves", "Vinyl Gloves", "Disposable Gloves", "Latex Gloves")),
    ("medical", "Intco Medical", 0.95, 540, "intco medical",
     ("Medical Consumables", "Face Masks", "Surgical Gloves", "Protective Suits")),
    ("wheelchair", "Intco Wheelchair", 1.00, 1800, "intco wheelchair",
     ("Wheelchair", "Rollator", "Walking Aid", "Commode Chair")),
    ("healthcare", "Intco Healthcare", 1.00, 900, "intco healthcare",
     ("Healthcare Supplies", "Mobility Aid", "Rehab Equipment", "Home Care")),
]

parts = []
for key, label, scale, aov, bt, terms in ACCOUNT_DEFS:
    m = by_key.get(key, {})
    cid = m.get("cid", "")
    gname = m.get("name", label)
    cat = m.get("cat", terms[0])
    parts.append(
        " {id:'%s',name:'%s',gname:'%s',cid:'%s',scale:%s,aov:%s,brandTerm:'%s',"
        "p1:'%s',p2:'%s',p3:'%s',p4:'%s',cat:'%s',\n  campaigns:%s}"
        % (key, label, gname, fmt_cid(cid), scale, aov, bt,
           terms[0].lower(), terms[1].lower(), terms[2].lower(), terms[3].lower(),
           cat, camp_block(label, terms[0], terms))
    )
new_accounts = "var ACCOUNTS=[\n" + ",\n".join(parts) + "\n];"

a_start = html.index("var ACCOUNTS=[")
a_end = html.index("\n];", a_start) + 3
html = html[:a_start] + new_accounts + html[a_end:]
print("[ok] ACCOUNTS 补齐为 %d 个" % len(ACCOUNT_DEFS))

# ---------- 6. realCamp：支持 [name,type] 且带真实产品分类 ----------
old_camp = """function realCamp(n){
  var t='Search';
  if(/pmax/i.test(n))t='PMax';else if(/demand/i.test(n))t='Demand Gen';else if(/video/i.test(n))t='Video';"""
new_camp = """function realCamp(x,cat){
  var n=Array.isArray(x)?x[0]:x;
  var t=Array.isArray(x)?x[1]:null;
  if(!t){
    t='Search';
    if(/pmax/i.test(n))t='PMax';else if(/demand/i.test(n))t='Demand Gen';else if(/video/i.test(n))t='Video';
  }"""
if old_camp in html:  # 首次改造；后续运行页面已是新版
    html = html.replace(old_camp, new_camp, 1)
    html = html.replace(
        "return {name:n,type:t,market:m,brand:/brand/i.test(n)?'Brand':'Non-brand',cat:'—',role:'real'};",
        "return {name:n,type:t,market:m,brand:/brand/i.test(n)?'Brand':'Non-brand',cat:cat||'—',role:'real'};", 1)
    print("[ok] realCamp 支持真实渠道类型与分类")
else:
    print("[skip] realCamp 已支持渠道类型与分类")

# ---------- 7. realData：campaigns 用真实类型；带出 meta ----------
old_rd = "campaigns:rd.c.map(realCamp),actions:ACTIONS,devices:DEVICES,"
new_rd = "campaigns:rd.c.map(function(x){return realCamp(x,rd.meta&&rd.meta.cat)}),actions:ACTIONS,devices:DEVICES,"
if old_rd in html:
    html = html.replace(old_rd, new_rd, 1)

old_tail = "landing:base.landing,mm:base.mm,funnelRates:base.funnelRates,real:true,realEpoch:REAL_EPOCH}};"
new_tail = ("landing:base.landing,mm:base.mm,funnelRates:base.funnelRates,real:true,"
            "realEpoch:REAL_EPOCH,realEnd:REAL_DATA_END,meta:rd.meta||null}};")
if old_tail in html:
    html = html.replace(old_tail, new_tail, 1)
print("[ok] realData 带入 meta / realEnd")

# ---------- 8. 徽标显示数据截止日，便于与后台核对 ----------
old_badge = "else if(!demo){db.className='badge bd-live';db.textContent='真实数据'}"
new_badge = """else if(!demo){
    var stale=Math.round((today0()-new Date(REAL_DATA_END+'T00:00:00'))/864e5);
    if(stale>3){db.className='badge bd-demo';db.textContent='数据已滞后 '+stale+' 天（截至 '+REAL_DATA_END+'）'}
    else{db.className='badge bd-live';db.textContent='真实数据 · 截至 '+REAL_DATA_END}
  }"""
if old_badge in html:
    html = html.replace(old_badge, new_badge, 1)
print("[ok] 徽标显示数据截止日")

# ---------- 9. 账户下拉附带 Google Ads 真实账户名，便于核对 ----------
old_sel = "$('accSel').innerHTML=ACCOUNTS.map(function(a){return '<option value=\"'+a.id+'\">'+esc(a.name)+'（'+a.cid+'）</option>'}).join('');"
new_sel = "$('accSel').innerHTML=ACCOUNTS.map(function(a){return '<option value=\"'+a.id+'\">'+esc(a.name)+'（'+a.cid+'） · '+esc(a.gname||a.name)+'</option>'}).join('');"
if old_sel in html:
    html = html.replace(old_sel, new_sel, 1)
    print("[ok] 账户下拉显示 Google Ads 真实账户名")
else:
    print("[warn] 账户下拉语句未匹配，跳过")

with open(PAGE, "w", encoding="utf-8") as f:
    f.write(html)
print("\n已写入 %s  (%.1f KB)" % (PAGE, len(html.encode("utf-8")) / 1024.0))
