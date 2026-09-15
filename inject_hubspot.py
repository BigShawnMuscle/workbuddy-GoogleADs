# -*- coding: utf-8 -*-
"""把 hubspot_data_generated.js 里的数据幂等注入 index.html

与 patch_hubspot.py 的页面结构改造解耦：本脚本只负责刷新 HUBSPOT 数据块，
可在每日自动化里安全重复执行。
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "index.html")
SRC = os.path.join(HERE, "hubspot_data_generated.js")

if not os.path.exists(SRC):
    sys.exit("缺少 %s，请先运行 refresh_hubspot.py" % SRC)

with io.open(SRC, encoding="utf-8") as f:
    block = f.read().strip()
if not block.endswith(";"):
    block += ";"

with io.open(PAGE, encoding="utf-8") as f:
    html = f.read()

# 清掉旧块（含此前 patch 注入的版本），再插到 REAL_DATA 之前
html, n = re.subn(r"var HUBSPOT=\{[^\n]*\};\n", "", html)
anchor = "\nvar REAL_DATA="
if anchor not in html:
    sys.exit("找不到 REAL_DATA 锚点，已中止")
if n > 1:
    sys.exit("清除了 %d 处 HUBSPOT 块（期望 <=1），已中止" % n)

html = html.replace(anchor, "\n" + block + anchor, 1)
with io.open(PAGE, "w", encoding="utf-8") as f:
    f.write(html)

print("已注入 HUBSPOT（%.1f KB，清除旧块 %d 处），index.html = %.1f KB"
      % (len(block) / 1024.0, n, len(html) / 1024.0))
