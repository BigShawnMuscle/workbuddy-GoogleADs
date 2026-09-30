# -*- coding: utf-8 -*-
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r"C:\Users\caleb\.workbuddy\google-ads\user-credentials.json"
import google.auth
from google.ads.googleads.client import GoogleAdsClient
creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/adwords"])
c = GoogleAdsClient(credentials=creds, developer_token="NbHT11svYClUr7AAjj9eWQ",
                    login_customer_id="8021601652", use_proto_plus=True)
svc = c.get_service("GoogleAdsService")
for q in [
  "SELECT campaign.name, campaign.status, campaign.start_date_time, campaign.end_date_time FROM campaign LIMIT 3",
  "SELECT campaign.name, campaign.status, campaign.serving_status FROM campaign LIMIT 3",
]:
    try:
        rows = list(svc.search(customer_id="2068692080", query=q))
        print("[OK]", q.split("SELECT ")[1])
        for r in rows:
            print("   ", r.campaign.name, r.campaign.status.name,
                  getattr(r.campaign, "start_date_time", ""), getattr(r.campaign, "end_date_time", ""),
                  getattr(r.campaign, "serving_status", ""))
    except Exception as e:
        print("[FAIL]", q.split("SELECT ")[1], "->", str(e)[:200])
