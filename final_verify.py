# -*- coding: utf-8 -*-
"""终检：页面重算值 vs Google Ads API（同一窗口、同一口径）。"""
import sys, io, os, json, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r"C:\Users\caleb\.workbuddy\google-ads\user-credentials.json"
import google.auth
from google.ads.googleads.client import GoogleAdsClient

WS = r"C:\Users\caleb\WorkBuddy\2026-09-15-10-47-36"
DEV_TOKEN, LOGIN_CID = "NbHT11svYClUr7AAjj9eWQ", "8021601652"

page = json.load(open(os.path.join(WS, "page_kpi.json"), encoding="utf-8"))
today = datetime.date.today()
# 页面窗口 = daysAgo 0..29 → 今天往前 29 天的数据（day0=今天无数据）
end = today - datetime.timedelta(days=1)
start = today - datetime.timedelta(days=29)

creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/adwords"])
client = GoogleAdsClient(credentials=creds, developer_token=DEV_TOKEN,
                         login_customer_id=LOGIN_CID, use_proto_plus=True)
svc = client.get_service("GoogleAdsService")
q = """
    SELECT customer.id, metrics.impressions, metrics.clicks,
           metrics.cost_micros, metrics.conversions
    FROM campaign
    WHERE segments.date BETWEEN '%s' AND '%s'
""" % (start, end)

print("核对窗口: %s ~ %s（页面「近 30 天」实际有数据的区间）\n" % (start, end))
print("%-11s %-12s %10s %12s %10s %10s  %s" % ("账户", "CID", "指标", "API", "页面", "差异", "结果"))
print("-" * 78)

ok_all = True
for key, p in page.items():
    if not p:
        continue
    cid = p["cid"]
    tot = {"impr": 0, "clicks": 0, "spend": 0.0, "conv": 0.0}
    for row in svc.search(customer_id=cid, query=q):
        tot["impr"] += row.metrics.impressions
        tot["clicks"] += row.metrics.clicks
        tot["spend"] += row.metrics.cost_micros / 1e6
        tot["conv"] += row.metrics.conversions
    for i, metric in enumerate(["impr", "clicks", "spend", "conv"]):
        a, b = tot[metric], p[metric]
        d = round(a - b, 2)
        good = abs(d) < 0.05
        if not good:
            ok_all = False
        print("%-11s %-12s %10s %12.2f %10.2f %10.2f  %s"
              % (key if i == 0 else "", cid if i == 0 else "", metric, a, b, d,
                 "OK" if good else "不一致"))
    print("-" * 78)

print("\n结论: %s" % ("全部一致 ✓" if ok_all else "仍存在不一致 ✗"))
