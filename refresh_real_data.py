# -*- coding: utf-8 -*-
"""
从 Google Ads API 重新生成工作台 REAL_DATA。

修复要点（对比旧版 export_real_data.py）：
1. daysAgo 按【真实日历差】计算，不再依赖"有数据日期的排序索引"。
   旧实现里某天无数据会导致后续全部前移 —— 这正是 basic 账户
   整体错位 1 天、并丢失 2026-08-26 整天的根因。
2. 覆盖 MCC 下全部 ENABLED 账户（旧版只写死 3 个，漏了 Wheelchair / Healthcare）。
3. 保留真实渠道类型（advertising_channel_type），不再靠正则猜名字。
4. 保留设备维度，且不再把 CONNECTED_TV / OTHER 硬塞进 Desktop。
5. 丢弃全 0 行，控制体积。
"""
import sys, io, os, json, datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r"C:\Users\caleb\.workbuddy\google-ads\user-credentials.json"

import google.auth
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

DEV_TOKEN = "NbHT11svYClUr7AAjj9eWQ"
LOGIN_CID = "8021601652"
OUT = r"C:\Users\caleb\WorkBuddy\2026-09-15-10-47-36\real_data_generated.js"
META_OUT = r"C:\Users\caleb\WorkBuddy\2026-09-15-10-47-36\accounts_meta.json"

DAYS = int(os.environ.get("GADS_DAYS", "400"))

# key -> (customerId, 工作台显示名, 默认产品分类)
ACCOUNTS = [
    ("basic",     "2068692080", "Basic Medical",   "Exam Gloves"),
    ("gloves",    "4469410060", "Intco Gloves",    "Nitrile Gloves"),
    ("medical",   "8529881574", "Intco Medical",   "Medical Consumables"),
    ("wheelchair","4325844223", "Intco Wheelchair","Wheelchair"),
    ("healthcare","6921495146", "Intco Healthcare","Healthcare"),
]

CHANNEL_MAP = {
    "SEARCH": "Search", "PERFORMANCE_MAX": "PMax", "DISPLAY": "Display",
    "SHOPPING": "Shopping", "VIDEO": "Video", "MULTI_CHANNEL": "PMax",
    "DEMAND_GEN": "Demand Gen", "SMART": "Smart", "LOCAL": "Local",
    "TRAVEL": "Travel", "DISCOVERY": "Discovery", "OTHER": "Other",
}
# 与页面 DEVICES 保持一致（页面需同步扩展为 5 项）
DEVICE_MAP = {"DESKTOP": 0, "MOBILE": 1, "TABLET": 2, "CONNECTED_TV": 3, "OTHER": 4, "UNSPECIFIED": 4}


def main():
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/adwords"])
    client = GoogleAdsClient(credentials=credentials, developer_token=DEV_TOKEN,
                             login_customer_id=LOGIN_CID, use_proto_plus=True)
    svc = client.get_service("GoogleAdsService")

    today = datetime.date.today()
    data_end = today - datetime.timedelta(days=1)     # Google Ads 数据 T-1 才完整
    epoch = data_end + datetime.timedelta(days=1)      # REAL_EPOCH：day1 = data_end
    start = epoch - datetime.timedelta(days=DAYS)

    print("今天=%s  数据截止=%s  REAL_EPOCH=%s  回溯起点=%s (%d 天)"
          % (today, data_end, epoch, start, DAYS))

    gaql = """
        SELECT campaign.name, campaign.advertising_channel_type,
               segments.date, segments.device,
               metrics.impressions, metrics.clicks,
               metrics.cost_micros, metrics.conversions
        FROM campaign
        WHERE segments.date BETWEEN '%s' AND '%s'
    """ % (start, data_end)

    real = {}
    meta = {"epoch": str(epoch), "dataEnd": str(data_end), "days": DAYS, "accounts": []}

    for key, cid, label, cat in ACCOUNTS:
        # --- 账户基本信息 ---
        acc_name, currency, status = label, "CNY", "ENABLED"
        try:
            q = ("SELECT customer.id, customer.descriptive_name, customer.currency_code, "
                 "customer.status FROM customer LIMIT 1")
            for row in svc.search(customer_id=cid, query=q):
                acc_name = row.customer.descriptive_name or label
                currency = row.customer.currency_code or "CNY"
                status = row.customer.status.name
        except GoogleAdsException as e:
            print("  [%s] 读取账户信息失败: %s" % (key, e.failure.errors[0].message if e.failure.errors else e))

        # --- 明细 ---
        agg = {}          # (daysAgo, campIdx, devIdx) -> [impr, clicks, spend, conv]
        camp_spend = {}   # name -> total spend，用于稳定排序
        camp_type = {}    # name -> channel type
        rows_seen = 0
        try:
            for row in svc.search(customer_id=cid, query=gaql):
                rows_seen += 1
                cname = row.campaign.name
                chan = CHANNEL_MAP.get(row.campaign.advertising_channel_type.name,
                                       row.campaign.advertising_channel_type.name)
                camp_type.setdefault(cname, chan)
                d = datetime.date(int(row.segments.date[:4]), int(row.segments.date[5:7]),
                                  int(row.segments.date[8:10]))
                days_ago = (epoch - d).days          # ★ 真实日历差，不用索引
                if days_ago < 1 or days_ago > DAYS:
                    continue
                dev = DEVICE_MAP.get(row.segments.device.name, 4)
                spend = row.metrics.cost_micros            # ★ 存 micros 整数，零精度损失
                conv = row.metrics.conversions
                k = (days_ago, cname, dev)
                a = agg.setdefault(k, [0, 0, 0.0, 0.0])
                a[0] += row.metrics.impressions
                a[1] += row.metrics.clicks
                a[2] += spend
                a[3] += conv
                camp_spend[cname] = camp_spend.get(cname, 0.0) + spend
        except GoogleAdsException as e:
            print("  [%s] 拉取失败: %s" % (key, e.failure.errors[0].message if e.failure.errors else e))

        # 系列顺序按总花费降序（稳定、可复现）
        camps = sorted(camp_spend.keys(), key=lambda n: (-camp_spend[n], n))
        cidx = {n: i for i, n in enumerate(camps)}

        rows = []
        for (days_ago, cname, dev), a in agg.items():
            if a[0] == 0 and a[1] == 0 and a[2] == 0 and a[3] == 0:
                continue                                   # 丢弃全 0 行
            rows.append([days_ago, cidx[cname], 0, dev, 0,
                         int(a[0]), int(a[1]), int(a[2]), round(a[3], 2)])
        rows.sort(key=lambda r: (r[0], r[1], r[3]))

        real[key] = {
            "c": [[n, camp_type.get(n, "Search")] for n in camps],
            "r": rows,
            "meta": {"n": acc_name, "cid": cid, "cur": currency, "status": status, "cat": cat},
        }
        tot_spend = sum(r[7] for r in rows) / 1e6
        tot_clk = sum(r[6] for r in rows)
        print("  %-11s %-30s API行=%-6d 输出行=%-6d 系列=%-3d 点击=%-7d 花费=%-12.2f %s"
              % (key, acc_name, rows_seen, len(rows), len(camps), tot_clk, tot_spend, currency))
        meta["accounts"].append({"key": key, "cid": cid, "name": acc_name,
                                 "label": label, "cur": currency, "status": status,
                                 "cat": cat, "rows": len(rows), "camps": len(camps),
                                 "spend": round(tot_spend, 2), "clicks": tot_clk})

    # ---- 输出 JS ----
    def js_arr(a):
        return "[" + ",".join(js_arr(x) if isinstance(x, list) else
                              (('"%s"' % x) if isinstance(x, str) else str(x)) for x in a) + "]"

    parts = []
    for key in real:
        d = real[key]
        parts.append(
            '%s:{c:%s,r:%s,meta:{n:"%s",cid:"%s",cur:"%s",status:"%s",cat:"%s"}}'
            % (key, js_arr(d["c"]), js_arr(d["r"]),
               d["meta"]["n"].replace('"', "'"), d["meta"]["cid"],
               d["meta"]["cur"], d["meta"]["status"], d["meta"]["cat"])
        )
    out = "var REAL_DATA_GEN={" + ",".join(parts) + "};\n"
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(out)
    with open(META_OUT, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)

    print("\nREAL_EPOCH 应设为: %s" % epoch)
    print("已生成 %s (%.1f KB)" % (OUT, len(out.encode("utf-8")) / 1024.0))
    print("已生成 %s" % META_OUT)


if __name__ == "__main__":
    sys.exit(main())
