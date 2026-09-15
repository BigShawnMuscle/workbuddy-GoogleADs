# -*- coding: utf-8 -*-
"""
拉取工作台「关键词 / 搜索词 / 广告 / 落地页 / 转化动作」5 个模块的真实明细数据。

与 refresh_real_data.py 的差别：
- 后者只拉 campaign × date × device 的汇总行（KPI/趋势/系列用）；
- 本脚本拉实体级明细（keyword_view / search_term_view / ad_group_ad /
  landing_page_view / conversion_action），供页面下半部分看板使用。

输出 real_detail_generated.js（var REAL_DETAIL = {...}）+ detail_meta.json。

结构（每个账户）：
{
  win: 120,                                  # 覆盖窗口天数
  kw: {n:[关键词...], m:[匹配类型...], r:[[daysAgo, idx, impr, clicks, micros, conv], ...]},
  st: {n:[搜索词...], r:[[daysAgo, idx, impr, clicks, micros, conv], ...]},
  ad: {n:[广告名...], r:[同上]},
  lp: {n:[落地页URL...], r:[同上]},
  ca: {n:[转化动作名...], r:[[daysAgo, idx, conv, allConv], ...]}
}

体积控制：窗口默认 120 天 + 每模块按总花费取 Top N + 丢弃全 0 行。
"""
import sys, io, os, json, datetime, re

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r"C:\Users\caleb\.workbuddy\google-ads\user-credentials.json"

import google.auth
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

DEV_TOKEN = "NbHT11svYClUr7AAjj9eWQ"
LOGIN_CID = "8021601652"
WS = r"C:\Users\caleb\WorkBuddy\2026-09-15-10-47-36"
OUT = os.path.join(WS, "real_detail_generated.js")
META_OUT = os.path.join(WS, "detail_meta.json")

DAYS = int(os.environ.get("GADS_DETAIL_DAYS", "120"))
TOP = {
    "kw": int(os.environ.get("GADS_TOP_KW", "60")),
    "st": int(os.environ.get("GADS_TOP_ST", "60")),
    "ad": int(os.environ.get("GADS_TOP_AD", "30")),
    "lp": int(os.environ.get("GADS_TOP_LP", "30")),
    "ca": int(os.environ.get("GADS_TOP_CA", "12")),
}

ACCOUNTS = [
    ("basic", "2068692080", "BasicMedical_EN_20251229"),
    ("gloves", "4469410060", "Intco_Gloves_EN_20240222"),
    ("medical", "8529881574", "Intco_Medical_EN_20251031"),
    ("wheelchair", "4325844223", "Intco_Wheelchair_EN_20240123"),
    ("healthcare", "6921495146", "Intco_Healthcare_EN_20240222"),
]

MATCH_CN = {"EXACT": "Exact", "PHRASE": "Phrase", "BROAD": "Broad", "UNSPECIFIED": "—", "UNKNOWN": "—"}


def search(svc, cid, q):
    """执行 GAQL 并分页取回全部行。"""
    # 本环境 google-ads-python 的 search() 直接迭代 GoogleAdsRow
    return list(svc.search(customer_id=cid, query=q))


def try_search(svc, cid, q, label):
    """字段可能不被 API 版本支持，失败时返回 None 而不是中断整体流程。"""
    try:
        return search(svc, cid, q)
    except GoogleAdsException as e:
        msg = ""
        for err in e.failure.errors:
            msg = err.message
            break
        print("  [跳过] %s：%s" % (label, msg[:120]))
        return None
    except Exception as e:  # noqa
        print("  [跳过] %s：%s" % (label, str(e)[:120]))
        return None


def acc_rows(svc, cid, query, keyfn, valfn, days_ago, top, label, conv_only=False):
    """
    通用：查询 → 聚合成 {key: {day: [impr, clicks, micros, conv]}} → 取 Top N。
    keyfn(row) 返回实体名；valfn(row) 返回 [impr, clicks, micros, conv]。
    """
    rows = try_search(svc, cid, query, label)
    if rows is None:
        return None
    agg = {}
    for r in rows:
        k = keyfn(r)
        if not k:
            continue
        d = days_ago(str(r.segments.date))
        if d is None or d < 0 or d >= DAYS:
            continue
        v = valfn(r)
        e = agg.setdefault(k, {})
        cur = e.get(d)
        if cur is None:
            e[d] = list(v)
        else:
            for i in range(len(v)):
                cur[i] += v[i]
    # 按总花费（或转化数）排序取 Top N
    def total(e):
        return sum(x[2] for x in e.values()) if not conv_only else sum(x[2] for x in e.values()) * 1e6 + sum(x[3] for x in e.values())
    names = sorted(agg.keys(), key=lambda k: -total(agg[k]))[:top]
    idx = {n: i for i, n in enumerate(names)}
    out = []
    for n in names:
        for d, v in sorted(agg[n].items()):
            if v[0] == 0 and v[1] == 0 and v[2] == 0 and v[3] == 0:
                continue
            out.append([d, idx[n], int(v[0]), int(v[1]), int(v[2]), round(v[3], 2)])
    return names, out


def first_headline(ad):
    """从 RSA / RDA 里取一条可读的标题作为广告名。"""
    try:
        rsa = ad.responsive_search_ad
        hs = [h.text for h in rsa.headlines if h.text]
        if hs:
            return max(hs, key=len)
    except Exception:
        pass
    try:
        rda = ad.responsive_display_ad
        hs = [h.text for h in rda.headlines if h.text]
        if hs:
            return max(hs, key=len)
    except Exception:
        pass
    try:
        if ad.image_ad.name:
            return ad.image_ad.name
    except Exception:
        pass
    return ""


def short_url(u, keep=60):
    u = re.sub(r"^https?://", "", u or "")
    u = re.sub(r"^www\.", "", u)
    if len(u) > keep:
        u = u[: keep - 1] + "…"
    return u or "—"


def main():
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/adwords"])
    client = GoogleAdsClient(credentials=credentials, developer_token=DEV_TOKEN,
                             login_customer_id=LOGIN_CID, use_proto_plus=True)
    svc = client.get_service("GoogleAdsService")

    today = datetime.date.today()
    data_end = today - datetime.timedelta(days=1)
    epoch = data_end + datetime.timedelta(days=1)
    start = epoch - datetime.timedelta(days=DAYS - 1)
    s_start, s_end = start.isoformat(), data_end.isoformat()

    def days_ago(ds):
        try:
            return (epoch - datetime.date.fromisoformat(ds)).days
        except Exception:
            return None

    print("明细窗口：%s ~ %s（%d 天），REAL_EPOCH=%s" % (s_start, s_end, DAYS, epoch))

    detail, meta = {}, {}
    for key, cid, gname in ACCOUNTS:
        print("\n=== %s (%s) %s ===" % (key, cid, gname))
        blk = {"win": DAYS}

        # ---- 关键词 ----
        q = ("SELECT ad_group_criterion.criterion_id, ad_group_criterion.keyword.text, "
             "ad_group_criterion.keyword.match_type, segments.date, "
             "metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions "
             "FROM keyword_view WHERE segments.date BETWEEN '%s' AND '%s' "
             "AND metrics.impressions > 0" % (s_start, s_end))
        matches = {}

        def kw_key(r):
            t = (r.ad_group_criterion.keyword.text or "").strip()
            if not t:
                return ""
            matches[t] = MATCH_CN.get(r.ad_group_criterion.keyword.match_type.name, "—")
            return t

        res = acc_rows(svc, cid, q, kw_key,
                       lambda r: [r.metrics.impressions, r.metrics.clicks,
                                  r.metrics.cost_micros, r.metrics.conversions],
                       days_ago, TOP["kw"], "关键词")
        if res:
            names, rows = res
            blk["kw"] = {"n": names, "m": [matches.get(n, "—") for n in names], "r": rows}
            print("  关键词 %d 个 / %d 行" % (len(names), len(rows)))

        # ---- 搜索词 ----
        q = ("SELECT search_term_view.search_term, segments.date, "
             "metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions "
             "FROM search_term_view WHERE segments.date BETWEEN '%s' AND '%s' "
             "AND metrics.clicks > 0" % (s_start, s_end))
        res = acc_rows(svc, cid, q,
                       lambda r: (r.search_term_view.search_term or "").strip(),
                       lambda r: [r.metrics.impressions, r.metrics.clicks,
                                  r.metrics.cost_micros, r.metrics.conversions],
                       days_ago, TOP["st"], "搜索词")
        if res:
            names, rows = res
            blk["st"] = {"n": names, "r": rows}
            print("  搜索词 %d 个 / %d 行" % (len(names), len(rows)))

        # ---- 广告 ----
        q = ("SELECT ad_group_ad.ad.id, ad_group_ad.ad.type, ad_group_ad.ad.name, "
             "ad_group_ad.ad.responsive_search_ad.headlines, "
             "ad_group_ad.ad.responsive_display_ad.headlines, "
             "ad_group_ad.ad.image_ad.name, "
             "segments.date, metrics.impressions, metrics.clicks, "
             "metrics.cost_micros, metrics.conversions "
             "FROM ad_group_ad WHERE segments.date BETWEEN '%s' AND '%s' "
             "AND metrics.impressions > 0" % (s_start, s_end))
        labels = {}

        def ad_key(r):
            ad = r.ad_group_ad.ad
            try:
                nm = (ad.name or "").strip()
            except Exception:
                nm = ""
            if not nm:
                nm = first_headline(ad)
            if not nm:
                nm = "Ad #%s" % ad.id
            nm = nm[:70]
            labels[nm] = ad.type_.name if ad.type_ else ""
            return nm

        res = acc_rows(svc, cid, q, ad_key,
                       lambda r: [r.metrics.impressions, r.metrics.clicks,
                                  r.metrics.cost_micros, r.metrics.conversions],
                       days_ago, TOP["ad"], "广告")
        if res:
            names, rows = res
            blk["ad"] = {"n": names, "t": [labels.get(n, "") for n in names], "r": rows}
            print("  广告 %d 个 / %d 行" % (len(names), len(rows)))

        # ---- 落地页 ----
        q = ("SELECT landing_page_view.unexpanded_final_url, segments.date, "
             "metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions "
             "FROM landing_page_view WHERE segments.date BETWEEN '%s' AND '%s' "
             "AND metrics.clicks > 0" % (s_start, s_end))
        res = acc_rows(svc, cid, q,
                       lambda r: short_url(r.landing_page_view.unexpanded_final_url),
                       lambda r: [r.metrics.impressions, r.metrics.clicks,
                                  r.metrics.cost_micros, r.metrics.conversions],
                       days_ago, TOP["lp"], "落地页")
        if res:
            names, rows = res
            blk["lp"] = {"n": names, "r": rows}
            print("  落地页 %d 个 / %d 行" % (len(names), len(rows)))

        # ---- 转化动作（分动作，用于漏斗）----
        q = ("SELECT segments.conversion_action_name, segments.date, "
             "metrics.conversions, metrics.all_conversions "
             "FROM campaign WHERE segments.date BETWEEN '%s' AND '%s' "
             "AND metrics.conversions > 0" % (s_start, s_end))
        rows = try_search(svc, cid, q, "转化动作")
        if rows:
            agg = {}
            for r in rows:
                n = (r.segments.conversion_action_name or "").strip() or "未命名转化"
                d = days_ago(str(r.segments.date))
                if d is None or d < 0 or d >= DAYS:
                    continue
                e = agg.setdefault(n, {})
                cur = e.get(d, [0, 0])
                e[d] = [cur[0] + r.metrics.conversions, cur[1] + (r.metrics.all_conversions or 0)]
            names = sorted(agg.keys(), key=lambda k: -sum(x[0] for x in agg[k].values()))[:TOP["ca"]]
            idx = {n: i for i, n in enumerate(names)}
            out = []
            for n in names:
                for d, v in sorted(agg[n].items()):
                    if v[0] == 0 and v[1] == 0:
                        continue
                    out.append([d, idx[n], round(v[0], 2), round(v[1], 2)])
            blk["ca"] = {"n": names, "r": out}
            print("  转化动作 %d 个 / %d 行" % (len(names), len(out)))

        detail[key] = blk
        meta[key] = {"cid": cid, "gname": gname,
                     "modules": [k for k in ("kw", "st", "ad", "lp", "ca") if k in blk]}

    js = "var REAL_DETAIL=" + json.dumps(detail, ensure_ascii=False,
                                         separators=(",", ":")) + ";\n"
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(js)
    with open(META_OUT, "w", encoding="utf-8") as f:
        json.dump({"epoch": epoch.isoformat(), "data_end": data_end.isoformat(),
                   "win": DAYS, "accounts": meta}, f, ensure_ascii=False, indent=2)

    print("\n已写出 %s（%.1f KB）" % (OUT, len(js.encode("utf-8")) / 1024.0))
    for k in detail:
        print("  %-11s %s" % (k, ",".join(meta[k]["modules"]) or "无数据"))


if __name__ == "__main__":
    main()
