# -*- coding: utf-8 -*-
"""HubSpot 接入对账：用与采集脚本不同的 API 路径回查，确认页面数字与 CRM 一致

回查项：
  1. 各窗口同期群人数（count 接口 vs 全量拉取后聚合）
  2. 漏斗各层（count 接口 + 属性非空过滤 vs 全量聚合）
  3. 线索质量表各来源总数
  4. 广告系列归因 Top1
用法：python verify_hubspot.py
"""
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import refresh_hubspot as R

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "hubspot_data_generated.js"), encoding="utf-8") as f:
    raw = f.read()
DATA = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])

CONTACTS = "%s/crm/v3/objects/contacts/search" % R.BASE
ok = fail = 0


def check(label, expect, actual, tol=0):
    global ok, fail
    good = abs(expect - actual) <= tol
    if good:
        ok += 1
    else:
        fail += 1
    print("  %-46s 页面 %-8s API %-8s %s" % (label, expect, actual, "OK" if good else "✗ 不一致"))
    return good


def count_with(props_not_empty, filters):
    """用 search 接口直接计数：属性非空用 HAS_PROPERTY"""
    fs = list(filters)
    for p in props_not_empty:
        fs.append({"propertyName": p, "operator": "HAS_PROPERTY"})
    return R.count(fs)


def between(prop, lo, hi):
    return [
        {"propertyName": prop, "operator": "GTE", "value": str(R.ms(
            datetime.datetime.combine(lo, datetime.time.min)))},
        {"propertyName": prop, "operator": "LTE", "value": str(R.ms(
            datetime.datetime.combine(hi, datetime.time.max)))},
    ]


def main():
    today = datetime.date.today()
    data_end = today - datetime.timedelta(days=1)
    epoch = data_end + datetime.timedelta(days=1)
    src = R.src_filter(R.GOOGLE_SOURCES)
    print("=== HubSpot 对账（截至 %s，epoch=%s）===\n" % (data_end, epoch))

    # 1. 窗口同期群人数
    print("[1] 同期群人数")
    for w in DATA["wins"]:
        lo = epoch - datetime.timedelta(days=int(w) - 1)
        api = R.count(between("createdate", lo, data_end) + [src])
        check("近 %s 天付费搜索新增联系人" % w, DATA["funnel"][str(w)]["n"], api)

    # 2. 漏斗各层（180 天窗口）
    print("\n[2] 漏斗分层（近 %s 天）" % DATA["wins"][-1])
    w = str(DATA["wins"][-1])
    lo = epoch - datetime.timedelta(days=int(w) - 1)
    win = between("createdate", lo, data_end) + [src]
    F = DATA["funnel"][w]
    # 采集侧判定是 num_visits > 0，回查也必须 > 0（HAS_PROPERTY 会把 "0" 也算进去）
    check("访客（hs_analytics_num_visits > 0）", F["v"],
          R.count(win + [{"propertyName": "hs_analytics_num_visits", "operator": "GT", "value": "0"}]))
    check("表单提交（first_conversion_date 非空）", F["c"],
          count_with(["first_conversion_date"], win))
    for key, stages, label in (
        ("l", ["lead", "3632360147", "marketingqualifiedlead", "salesqualifiedlead",
               "opportunity", "customer"], "线索 Lead+"),
        ("m", ["marketingqualifiedlead", "salesqualifiedlead", "opportunity", "customer"], "MQL+"),
        ("s", ["salesqualifiedlead", "opportunity", "customer"], "SQL+"),
    ):
        api = R.count(win + [{"propertyName": "first_conversion_date", "operator": "HAS_PROPERTY"},
                             {"propertyName": "lifecyclestage", "operator": "IN", "values": stages}])
        check("%s ∩ 有转化记录" % label, F[key], api)

    # 3. 单调性
    print("\n[3] 漏斗单调性（v ≥ c ≥ l ≥ m ≥ s）")
    for w in DATA["wins"]:
        f = DATA["funnel"][str(w)]
        seq = [f["v"], f["c"], f["l"], f["m"], f["s"]]
        mono = all(seq[i] >= seq[i + 1] for i in range(len(seq) - 1))
        print("  %-46s %s %s" % ("近 %s 天" % w, " → ".join(str(x) for x in seq),
                                 "OK" if mono else "✗ 倒挂"))
        ok_i, fail_i = (1, 0) if mono else (0, 1)
        globals()["ok"], globals()["fail"] = ok + ok_i, fail + fail_i

    # 4. 线索质量表各来源总数
    print("\n[4] 线索质量表（各来源联系人总数）")
    for row in DATA["src"]:
        values = dict(R.SOURCE_ROWS).get(row["source"])
        if not values:
            continue
        check("%s 联系人" % row["source"], row["total"], R.count([R.src_filter(values)]))

    # 5. 广告系列 Top1
    print("\n[5] 广告系列归因 Top1")
    # 不用 EQ 回查：HubSpot 的文本 EQ 不区分大小写且会命中变体，与归一化口径不可比。
    # 改为拉回同样条件的记录、本地按 norm_camp 分组，与采集侧逻辑完全一致。
    rows = R.search_all(win + [
        {"propertyName": "first_conversion_date", "operator": "HAS_PROPERTY"},
        {"propertyName": "lifecyclestage", "operator": "IN",
         "values": ["lead", "3632360147", "marketingqualifiedlead", "salesqualifiedlead",
                    "opportunity", "customer"]}],
        ["createdate", "lifecyclestage", "first_conversion_date", "hs_analytics_source_data_1"])
    tally = {}
    for c in rows:
        p = c.get("properties", {}) or {}
        k = R.norm_camp((p.get("hs_analytics_source_data_1") or "").strip())
        if k:
            tally[k] = tally.get(k, 0) + 1
    for row in DATA["camp"][:5]:
        check("%s（窗口内∩有转化∩Lead+）" % row["n"][:30], row["lead"],
              tally.get(R.norm_camp(row["n"]), 0))

    print("\n=== 对账结果：通过 %d 项，失败 %d 项 ===" % (ok, fail))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
