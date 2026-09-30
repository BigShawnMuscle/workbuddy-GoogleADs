# -*- coding: utf-8 -*-
"""核对：① 账户内全部系列（含暂停/结束，无日期分段）② 按日汇总以验证窗口差一天"""
import sys, io, os, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r"C:\Users\caleb\.workbuddy\google-ads\user-credentials.json"
import google.auth
from google.ads.googleads.client import GoogleAdsClient

DEV_TOKEN, LOGIN_CID = "NbHT11svYClUr7AAjj9eWQ", "8021601652"
creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/adwords"])
client = GoogleAdsClient(credentials=creds, developer_token=DEV_TOKEN,
                         login_customer_id=LOGIN_CID, use_proto_plus=True)
svc = client.get_service("GoogleAdsService")

ACCTS = {"basic": "2068692080", "gloves": "4469410060", "medical": "8529881574"}
q_inv = """
  SELECT campaign.id, campaign.name, campaign.status,
         campaign.advertising_channel_type, campaign_budget.amount_micros
  FROM campaign ORDER BY campaign.name
"""
for k, cid in ACCTS.items():
    print("==== %s (%s) 全部系列 ====" % (k, cid))
    for row in svc.search(customer_id=cid, query=q_inv):
        c = row.campaign
        bud = row.campaign_budget.amount_micros / 1e6
        print("   %-40s %-10s %-14s 预算=%.2f" % (c.name[:40], str(c.status).split('.')[-1],
                                                   str(c.advertising_channel_type).split('.')[-1], bud))

print("\n==== basic 按日汇总 2026-08-25 ~ 2026-09-30 ====")
q_day = """
  SELECT segments.date, metrics.impressions, metrics.clicks,
         metrics.cost_micros, metrics.conversions
  FROM customer WHERE segments.date BETWEEN '2026-08-25' AND '2026-09-30'
"""
rows = list(svc.search(customer_id="2068692080", query=q_day))
rows.sort(key=lambda r: r.segments.date)
tot = {}
for r in rows:
    d = r.segments.date
    tot[d] = (r.metrics.impressions, r.metrics.clicks, r.metrics.cost_micros / 1e6, r.metrics.conversions)
    print("   %s  impr=%-8d clicks=%-6d spend=%-10.2f conv=%.2f" % (d, *tot[d]))
def win(a, b):
    s = [0.0, 0, 0.0, 0.0]
    for d, v in tot.items():
        if a <= d <= b:
            s[0] += v[0]; s[1] += v[1]; s[2] += v[2]; s[3] += v[3]
    return s
a = win('2026-09-01', '2026-09-29')   # 页面当前口径
b = win('2026-08-31', '2026-09-29')   # 后台「过去30天」口径
c = win('2026-08-31', '2026-09-30')
print("\n窗口对比(impr/clicks/spend/conv)：")
print("  页面 09-01~09-29 : %d / %d / %.2f / %.2f" % tuple(a))
print("  后台 08-31~09-29 : %d / %d / %.2f / %.2f" % tuple(b))
print("  差异(后台-页面)  : %d / %d / %.2f / %.2f" % tuple(b[i]-a[i] for i in range(4)))
print("  含09-30(应为空)  : %d / %d / %.2f / %.2f" % tuple(c))
