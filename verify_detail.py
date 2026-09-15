# -*- coding: utf-8 -*-
"""
回查 Google Ads API，校验页面「关键词 / 搜索词 / 广告 / 落地页 / 转化动作」
5 个明细模块的真实数据与账户一致。

前置：先跑 node detail_dump.js 30 生成 page_detail.json。
"""
import sys, io, os, json, datetime, re

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r"C:\Users\caleb\.workbuddy\google-ads\user-credentials.json"

import google.auth
from google.ads.googleads.client import GoogleAdsClient

DEV_TOKEN = "NbHT11svYClUr7AAjj9eWQ"
LOGIN_CID = "8021601652"
WS = r"C:\Users\caleb\WorkBuddy\2026-09-15-10-47-36"
PAGE_JSON = os.path.join(WS, "page_detail.json")

ACCOUNTS = [
    ("basic", "2068692080", "BasicMedical_EN_20251229"),
    ("gloves", "4469410060", "Intco_Gloves_EN_20240222"),
    ("medical", "8529881574", "Intco_Medical_EN_20251031"),
    ("wheelchair", "4325844223", "Intco_Wheelchair_EN_20240123"),
    ("healthcare", "6921495146", "Intco_Healthcare_EN_20240222"),
]


def short_url(u, keep=60):
    u = re.sub(r"^https?://", "", u or "")
    u = re.sub(r"^www\.", "", u)
    return u[: keep - 1] + "…" if len(u) > keep else (u or "—")


def first_headline(ad):
    try:
        hs = [h.text for h in ad.responsive_search_ad.headlines if h.text]
        if hs:
            return max(hs, key=len)
    except Exception:
        pass
    try:
        hs = [h.text for h in ad.responsive_display_ad.headlines if h.text]
        if hs:
            return max(hs, key=len)
    except Exception:
        pass
    return ""


def collect(svc, cid, gaql, keyfn):
    """聚合成 {entity: [impr, clicks, micros, conv]}。

    注意：GAQL 必须带上 segments.date。实测同一窗口下，不 SELECT segments.date 时
    Google 返回的 metrics.impressions 会更大（搜索词：1300 → 2794），
    与按日聚合的结果对不上。刷新脚本是按日取的，这里也必须按日取才能对账。
    """
    agg = {}
    for r in svc.search(customer_id=cid, query=gaql):
        k = keyfn(r)
        if not k:
            continue
        e = agg.setdefault(k, [0, 0, 0, 0.0])
        e[0] += r.metrics.impressions
        e[1] += r.metrics.clicks
        e[2] += r.metrics.cost_micros
        e[3] += r.metrics.conversions
    return agg


def cmp_list(label, api, items, keyfield, problems, acc_id):
    for it in items:
        n = it["n"]
        a = api.get(n)
        if a is None:
            problems.append("%s / %s / %s：API 查不到该实体" % (acc_id, label, n))
            continue
        p = [it["impr"], it["clicks"], it["spend"], it["conv"]]
        q = [a[0], a[1], round(a[2] / 1e6, 2), round(a[3], 2)]
        bad = []
        if p[0] != q[0]:
            bad.append("展示 %d≠%d" % (p[0], q[0]))
        if p[1] != q[1]:
            bad.append("点击 %d≠%d" % (p[1], q[1]))
        if abs(p[2] - q[2]) > 0.02:
            bad.append("花费 %.2f≠%.2f" % (p[2], q[2]))
        if abs(p[3] - q[3]) > 0.02:
            bad.append("转化 %.2f≠%.2f" % (p[3], q[3]))
        if bad:
            problems.append("%s / %s / %s：%s" % (acc_id, label, n[:40], "，".join(bad)))


def main():
    page = json.load(open(PAGE_JSON, encoding="utf-8"))
    rng = page["range"]
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/adwords"])
    client = GoogleAdsClient(credentials=credentials, developer_token=DEV_TOKEN,
                             login_customer_id=LOGIN_CID, use_proto_plus=True)
    svc = client.get_service("GoogleAdsService")

    today = datetime.date.today()
    end = today - datetime.timedelta(days=1)
    # 页面窗口：daysAgo 0..rng-1，daysAgo d 对应日期 = today - d；
    # daysAgo 0 是基准日（无数据），实际数据落在 [today-rng+1, today-1]
    start = today - datetime.timedelta(days=rng - 1)
    s, e = start.isoformat(), end.isoformat()
    print("对账窗口：%s ~ %s（%d 天）\n" % (s, e, rng))

    problems = []
    checked = 0
    for key, cid, gname in ACCOUNTS:
        blk = page["accounts"].get(key)
        if not blk:
            continue
        if not any(blk.get(m) for m in ("kw", "st", "ad", "lp", "ca")):
            print("%-11s 无明细数据（休眠账户），跳过" % key)
            continue
        W = "segments.date BETWEEN '%s' AND '%s'" % (s, e)

        if blk.get("kw"):
            api = collect(svc, cid,
                          "SELECT segments.date, ad_group_criterion.keyword.text, metrics.impressions, "
                          "metrics.clicks, metrics.cost_micros, metrics.conversions "
                          "FROM keyword_view WHERE %s AND metrics.impressions > 0" % W,
                          lambda r: (r.ad_group_criterion.keyword.text or "").strip())
            cmp_list("关键词", api, blk["kw"], "kw", problems, key)
            checked += len(blk["kw"])

        if blk.get("st"):
            api = collect(svc, cid,
                          "SELECT segments.date, search_term_view.search_term, metrics.impressions, "
                          "metrics.clicks, metrics.cost_micros, metrics.conversions "
                          "FROM search_term_view WHERE %s AND metrics.clicks > 0" % W,
                          lambda r: (r.search_term_view.search_term or "").strip())
            cmp_list("搜索词", api, blk["st"], "term", problems, key)
            checked += len(blk["st"])

        if blk.get("ad"):

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
                return nm[:70]

            api = collect(svc, cid,
                          "SELECT segments.date, ad_group_ad.ad.id, ad_group_ad.ad.name, "
                          "ad_group_ad.ad.responsive_search_ad.headlines, "
                          "ad_group_ad.ad.responsive_display_ad.headlines, "
                          "ad_group_ad.ad.image_ad.name, "
                          "metrics.impressions, metrics.clicks, metrics.cost_micros, "
                          "metrics.conversions FROM ad_group_ad WHERE %s "
                          "AND metrics.impressions > 0" % W, ad_key)
            cmp_list("广告", api, blk["ad"], "name", problems, key)
            checked += len(blk["ad"])

        if blk.get("lp"):
            api = collect(svc, cid,
                          "SELECT segments.date, landing_page_view.unexpanded_final_url, metrics.impressions, "
                          "metrics.clicks, metrics.cost_micros, metrics.conversions "
                          "FROM landing_page_view WHERE %s AND metrics.clicks > 0" % W,
                          lambda r: short_url(r.landing_page_view.unexpanded_final_url))
            cmp_list("落地页", api, blk["lp"], "lp", problems, key)
            checked += len(blk["lp"])

        if blk.get("ca"):
            agg = {}
            for r in svc.search(customer_id=cid, query=(
                    "SELECT segments.date, segments.conversion_action_name, metrics.conversions, "
                    "metrics.all_conversions FROM campaign WHERE %s "
                    "AND metrics.conversions > 0" % W)):
                n = (r.segments.conversion_action_name or "").strip() or "未命名转化"
                cur = agg.setdefault(n, [0, 0])
                cur[0] += r.metrics.conversions
                cur[1] += r.metrics.all_conversions or 0
            for it in blk["ca"]:
                a = agg.get(it["n"])
                checked += 1
                if a is None:
                    problems.append("%s / 转化动作 / %s：API 查不到" % (key, it["n"]))
                elif abs(a[0] - it["conv"]) > 0.02 or abs(a[1] - it["all"]) > 0.02:
                    problems.append("%s / 转化动作 / %s：页面 %.2f/%.2f ≠ API %.2f/%.2f"
                                    % (key, it["n"], it["conv"], it["all"], a[0], a[1]))

        n_kw = len(blk.get("kw") or [])
        print("%-11s 已校验 关键词%d 搜索词%d 广告%d 落地页%d 转化动作%d"
              % (key, n_kw, len(blk.get("st") or []), len(blk.get("ad") or []),
                 len(blk.get("lp") or []), len(blk.get("ca") or [])))

    print("\n共校验 %d 项" % checked)
    if problems:
        print("不一致 %d 项：" % len(problems))
        for p in problems[:40]:
            print("  ✗", p)
        sys.exit(1)
    print("全部一致 ✓")


if __name__ == "__main__":
    main()
