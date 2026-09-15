# -*- coding: utf-8 -*-
"""从 HubSpot 拉取真实线索漏斗数据 → hubspot_data_generated.js + hubspot_meta.json

数据源：HubSpot CRM v3 API（Private App token 直连，不经 MCP，便于自动化每日刷新）

产出三层：
  1. src    —— 各 Original Source 全量 Lifecycle Stage 分布（页面「HubSpot 线索质量」表）
  2. d      —— Google 付费搜索口径的按天漏斗序列（访客 / 表单提交 / 线索 / MQL / SQL）
  3. camp   —— 广告系列级线索归因（付费搜索 source_data_1 → Google Ads 广告系列名）
  4. deals  —— Deal pipeline 汇总

运行：
    python refresh_hubspot.py            # 默认近 180 天
    GADS_HS_DAYS=90 python refresh_hubspot.py

token 来源优先级：环境变量 HUBSPOT_ACCESS_TOKEN > ~/.workbuddy/mcp.json（不写进仓库）
"""
import json
import os
import sys
import time
import datetime
import collections
import re

import requests

BASE = "https://api.hubapi.com"
TIMEOUT = 30

# Google Ads 流量在 HubSpot 里的来源标识。
# 注意：ADS 精确匹配恒为 0，真实数据落在 PAID_SEARCH / PAID_SOCIAL 子类；
# PAID_SOCIAL 是 Facebook / LinkedIn，不属于 Google Ads，漏斗口径只取 PAID_SEARCH + ADS。
GOOGLE_SOURCES = ["PAID_SEARCH", "ADS"]
PAID_SOURCES = ["PAID_SEARCH", "PAID_SOCIAL", "ADS"]

STAGE_LEAD = "lead"
STAGE_PRE = "3632360147"          # 自定义阶段：pre-leads
STAGE_MQL = "marketingqualifiedlead"
STAGE_SQL = "salesqualifiedlead"
DEEP_STAGES = [STAGE_MQL, STAGE_SQL, "opportunity", "customer"]

SOURCE_ROWS = [
    ("付费广告（聚合）", PAID_SOURCES),
    ("付费搜索 PAID_SEARCH", ["PAID_SEARCH"]),
    ("付费社媒 PAID_SOCIAL", ["PAID_SOCIAL"]),
    ("线下导入 OFFLINE", ["OFFLINE"]),
    ("自然搜索 ORGANIC_SEARCH", ["ORGANIC_SEARCH"]),
    ("直接流量 DIRECT_TRAFFIC", ["DIRECT_TRAFFIC"]),
    ("推荐流量 REFERRALS", ["REFERRALS"]),
]


def load_token() -> str:
    tok = os.environ.get("HUBSPOT_ACCESS_TOKEN", "").strip()
    if tok:
        return tok
    mcp = os.path.join(os.path.expanduser("~"), ".workbuddy", "mcp.json")
    with open(mcp, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg["mcpServers"]["hubspot-bridge"]["env"]["HUBSPOT_ACCESS_TOKEN"]


TOKEN = load_token()
HDR = {
    "Authorization": "Bearer " + TOKEN,
    "Content-Type": "application/json",
    "User-Agent": "WorkBuddy-HubSpot-Refresh/1.0",
}


def req(method, url, **kw):
    """带退避重试的请求。HubSpot 偶发 400「There was a problem with the request」是限流，重试即可。"""
    last = None
    for attempt in range(5):
        try:
            r = requests.request(method, url, headers=HDR, timeout=TIMEOUT, **kw)
        except requests.RequestException as e:
            last = "network: %s" % e
            time.sleep(1 + attempt * 2)
            continue
        if r.ok:
            return r.json()
        if r.status_code in (429, 500, 502, 503, 504) or (
            r.status_code == 400 and "problem with the request" in r.text
        ):
            time.sleep(1 + attempt * 2)
            last = "%s %s" % (r.status_code, r.text[:120])
            continue
        raise RuntimeError("HubSpot %s %s: %s" % (r.status_code, url, r.text[:300]))
    raise RuntimeError("HubSpot 请求反复失败 %s: %s" % (url, last))


def count(filters) -> int:
    body = {"filterGroups": [{"filters": filters}], "limit": 1}
    return req("post", BASE + "/crm/v3/objects/contacts/search", json=body).get("total", 0)


def search_all(filters, props, path="/crm/v3/objects/contacts/search", cap=20000):
    out, after = [], None
    while len(out) < cap:
        body = {"filterGroups": [{"filters": filters}], "properties": props, "limit": 100}
        if after:
            body["after"] = after
        data = req("post", BASE + path, json=body)
        out.extend(data.get("results", []))
        nxt = (data.get("paging") or {}).get("next") or {}
        if not nxt.get("after"):
            break
        after = nxt["after"]
    return out


def src_filter(values):
    return (
        {"propertyName": "hs_analytics_source", "operator": "IN", "values": values}
        if len(values) > 1
        else {"propertyName": "hs_analytics_source", "operator": "EQ", "value": values[0]}
    )


def ms(dt):
    return int(dt.timestamp() * 1000)


LOCAL_TZ = datetime.datetime.now().astimezone().tzinfo

# 与页面 normCamp() 保持一致：小写 + 去掉 空格 _ - / { }
_NORM = re.compile(r"[\s_\-/{}]+")


def norm_camp(n):
    return _NORM.sub("", str(n or "").lower())


def day_of(v):
    """HubSpot 时间字段 → 本地日期（与 ms() 的本地时区口径一致）；空值返回 None。

    HubSpot 返回的是 UTC（...Z），直接截取前 10 位会得到 UTC 日期，
    与用本地时间构造的 ms() 边界对不上，会在窗口边界上差 1~2 条。
    """
    if not v:
        return None
    try:
        if "T" in v:
            dt = datetime.datetime.strptime(v[:19], "%Y-%m-%dT%H:%M:%S")
            return dt.replace(tzinfo=datetime.timezone.utc).astimezone(LOCAL_TZ).date()
        return datetime.datetime.fromtimestamp(int(v) / 1000, LOCAL_TZ).date()
    except (ValueError, TypeError):
        return None


def main():
    days = int(os.environ.get("GADS_HS_DAYS", "180"))
    today = datetime.date.today()          # 与 Google Ads 刷新脚本口径一致（本地日期）
    data_end = today - datetime.timedelta(days=1)
    epoch = data_end + datetime.timedelta(days=1)   # == today，与 REAL_EPOCH 同义
    start = epoch - datetime.timedelta(days=days - 1)

    def ago(d):
        return (epoch - d).days

    print("HubSpot 漏斗窗口：%s ~ %s（%d 天），epoch=%s" % (start, data_end, days, epoch))

    # ── 1. 拉取 Google 付费搜索来源全量联系人（口径统一后才分区间聚合） ───────────
    # 注意：不再分批按 createdate 过滤。全量拉回后在内存里按 7/30/90/180 分别聚合，
    # 保证漏斗每一层都来自「同一个同期群」，否则链式转化率没有意义。
    cohort = search_all(
        [src_filter(GOOGLE_SOURCES)],
        ["createdate", "lifecyclestage", "hs_analytics_num_visits",
         "first_conversion_date", "hs_analytics_source_data_1", "hs_lead_status"],
    )
    print("  付费搜索口径 全量联系人：%d" % len(cohort))

    # 阶段层级（本 portal 实测无 opportunity / customer，保留以防后续启用）
    STAGES_ABOVE_LEAD = [STAGE_LEAD, STAGE_PRE, STAGE_MQL, STAGE_SQL, "opportunity", "customer"]
    STAGES_ABOVE_MQL = [STAGE_MQL, STAGE_SQL, "opportunity", "customer"]
    STAGES_ABOVE_SQL = [STAGE_SQL, "opportunity", "customer"]

    def rec(c):
        """把一条联系人解析成漏斗可判定的结构"""
        p = c.get("properties", {}) or {}
        try:
            visits = int(float(p.get("hs_analytics_num_visits") or 0))
        except (TypeError, ValueError):
            visits = 0
        return {
            "d": day_of(p.get("createdate")),
            "stage": p.get("lifecyclestage") or "",
            "visitor": visits > 0,
            "conv": bool(p.get("first_conversion_date")),
            "camp": (p.get("hs_analytics_source_data_1") or "").strip(),
        }

    people = [rec(c) for c in cohort]
    print("  有可追踪访问 %d / 有转化记录 %d / 阶段非空 %d"
          % (sum(1 for x in people if x["visitor"]),
             sum(1 for x in people if x["conv"]),
             sum(1 for x in people if x["stage"])))

    # 按天新增序列（页面趋势用：只保留「新增联系人」一条线，其余层按窗口预聚合）
    dl = collections.Counter()
    for x in people:
        if x["d"] and start <= x["d"] <= data_end:
            dl[ago(x["d"])] += 1

    # ── 2. 同期群嵌套漏斗（每窗口单独算，保证 SQL ⊆ MQL ⊆ 线索 ⊆ 表单提交） ─────
    # 口径：全部以「有转化记录」为前提再叠加生命周期阶段，保证 v ≥ c ≥ l ≥ m ≥ s 严格单调。
    # 有 358 条 Lead+ 但无转化记录（销售手动创建 / 导入 / 线下），若混入会让漏斗倒挂，故不计入。
    def lv(x, stages):
        return x["conv"] and x["stage"] in stages

    WINDOWS = sorted(set([7, 30, 90, days]))
    funnel = {}
    for R in WINDOWS:
        lo = epoch - datetime.timedelta(days=R - 1)
        sub = [x for x in people if x["d"] and lo <= x["d"] <= data_end]
        funnel[str(R)] = {
            "v": sum(1 for x in sub if x["visitor"]),
            "c": sum(1 for x in sub if x["conv"]),
            "l": sum(1 for x in sub if lv(x, STAGES_ABOVE_LEAD)),
            "m": sum(1 for x in sub if lv(x, STAGES_ABOVE_MQL)),
            "s": sum(1 for x in sub if lv(x, STAGES_ABOVE_SQL)),
            "n": len(sub),
        }
        print("  近%3d天同期群 %5d 人 → 访客 %5d / 表单 %4d / 线索 %4d / MQL %3d / SQL %3d"
              % (R, funnel[str(R)]["n"], funnel[str(R)]["v"], funnel[str(R)]["c"],
                 funnel[str(R)]["l"], funnel[str(R)]["m"], funnel[str(R)]["s"]))

    # ── 3. 广告系列级归因（同样用嵌套口径：lead=已进入线索体系） ────────────────
    # key 必须与页面 normCamp() 完全一致：HubSpot 的 EQ 过滤对文本不区分大小写，
    # 若按原样字符串分组，脚本值 / 页面合并值 / API 回查值三者会对不上。
    camp = {}
    camp_total = 0
    for x in people:
        if not x["d"] or not (start <= x["d"] <= data_end):
            continue
        name = x["camp"]
        if not name:
            continue
        camp_total += 1
        k = norm_camp(name)
        if not k:
            continue
        e = camp.get(k)
        if not e:
            e = camp[k] = {"n": name, "lead": 0, "mql": 0, "sql": 0}
        if lv(x, STAGES_ABOVE_LEAD):
            e["lead"] += 1
        if lv(x, STAGES_ABOVE_MQL):
            e["mql"] += 1
        if lv(x, STAGES_ABOVE_SQL):
            e["sql"] += 1

    # 口径自检：确认各层是否严格嵌套（漏斗不能出现下一层比上一层大）
    _sub = [x for x in people if x["d"] and (epoch - datetime.timedelta(days=days - 1)) <= x["d"] <= data_end]
    _L = lambda f: sum(1 for x in _sub if f(x))
    print("\n  [口径自检] 同期群 %d 人：" % len(_sub))
    print("    有访问 %d | 有转化 %d | 阶段Lead+ %d | 阶段MQL+ %d | 阶段SQL+ %d"
          % (_L(lambda x: x["visitor"]), _L(lambda x: x["conv"]),
             _L(lambda x: x["stage"] in STAGES_ABOVE_LEAD),
             _L(lambda x: x["stage"] in STAGES_ABOVE_MQL),
             _L(lambda x: x["stage"] in STAGES_ABOVE_SQL)))
    print("    计入漏斗（有转化∩阶段）：线索 %d / MQL %d / SQL %d；Lead+但无转化（不计入）%d"
          % (_L(lambda x: x["conv"] and x["stage"] in STAGES_ABOVE_LEAD),
             _L(lambda x: x["conv"] and x["stage"] in STAGES_ABOVE_MQL),
             _L(lambda x: x["conv"] and x["stage"] in STAGES_ABOVE_SQL),
             _L(lambda x: x["stage"] in STAGES_ABOVE_LEAD and not x["conv"])))

    # ── 4. 各来源全量 Lifecycle Stage 分布（页面线索质量表） ────────────────────
    print("  按来源统计全量生命周期分布：")
    src_rows = []
    for label, values in SOURCE_ROWS:
        f = src_filter(values)
        total = count([f])
        lead = count([f, {"propertyName": "lifecyclestage", "operator": "EQ", "value": STAGE_LEAD}])
        pre = count([f, {"propertyName": "lifecyclestage", "operator": "EQ", "value": STAGE_PRE}])
        mql = count([f, {"propertyName": "lifecyclestage", "operator": "EQ", "value": STAGE_MQL}])
        sql = count([f, {"propertyName": "lifecyclestage", "operator": "EQ", "value": STAGE_SQL}])
        src_rows.append({
            "source": label,
            "total": total,
            "lead": lead,
            "pre": pre,
            "mql": mql,
            "sql": sql,
            "l2m": round(mql / (lead + pre) * 100, 1) if (lead + pre) else 0.0,
            "m2s": round(sql / mql * 100, 1) if mql else 0.0,
            "ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        print("    %-24s 联系人 %6d | Lead %5d | Pre %5d | MQL %4d | SQL %3d"
              % (label, total, lead, pre, mql, sql))

    # ── 5. Deals ──────────────────────────────────────────────────────────────
    deals = search_all([], ["dealstage", "amount", "createdate", "closedate", "dealname"],
                       path="/crm/v3/objects/deals/search")
    by_stage = collections.Counter()
    won_n = won_amt = 0.0
    for d in deals:
        p = d.get("properties", {})
        st = p.get("dealstage") or "unknown"
        by_stage[st] += 1
        if st == "closedwon":
            won_n += 1
            try:
                won_amt += float(p.get("amount") or 0)
            except ValueError:
                pass
    print("  Deals：%d（Closed Won %d，金额 %.2f）" % (len(deals), won_n, won_amt))

    # ── 6. 输出 ───────────────────────────────────────────────────────────────
    # 显示名用原始取值（v["n"]），key 只用于合并同类变体
    camp_rows = sorted(
        ({"n": v["n"], "lead": v["lead"], "mql": v["mql"], "sql": v["sql"]} for v in camp.values()),
        key=lambda x: -x["lead"],
    )[:40]

    payload = {
        "ep": epoch.isoformat(),
        "end": data_end.isoformat(),
        "portal": "242572787",
        "win": days,
        "ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "src": src_rows,
        "d": {"l": sorted([[k, n] for k, n in dl.items() if 0 <= k < days])},
        "funnel": funnel,
        "wins": WINDOWS,
        "camp": camp_rows,
        "campTotal": camp_total,          # 窗口内带广告系列名的联系人数
        "cohortInWin": sum(1 for x in people if x["d"] and start <= x["d"] <= data_end),
        "deals": {
            "total": len(deals),
            "by_stage": dict(by_stage),
            "won": {"count": won_n, "amount": round(won_amt, 2)},
        },
    }

    here = os.path.dirname(os.path.abspath(__file__))
    js = os.path.join(here, "hubspot_data_generated.js")
    with open(js, "w", encoding="utf-8") as f:
        f.write("var HUBSPOT=" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n")
    meta = os.path.join(here, "hubspot_meta.json")
    with open(meta, "w", encoding="utf-8") as f:
        json.dump({
            "epoch": epoch.isoformat(),
            "data_end": data_end.isoformat(),
            "days": days,
            "cohort_contacts": len(cohort),
            "funnel": funnel,
            "sources": {r["source"]: r for r in src_rows},
            "deals": payload["deals"],
            "top_campaigns": camp_rows[:10],
        }, f, ensure_ascii=False, indent=2)

    f0 = funnel[str(days)]
    print("\n近 %d 天漏斗：新增 %d → 访客 %d / 表单提交 %d / 线索 %d / MQL %d / SQL %d"
          % (days, f0["n"], f0["v"], f0["c"], f0["l"], f0["m"], f0["s"]))
    print("输出：%s（%.1f KB）" % (os.path.basename(js), os.path.getsize(js) / 1024))


if __name__ == "__main__":
    sys.exit(main())
