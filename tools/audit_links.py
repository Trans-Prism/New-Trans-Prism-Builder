#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit_links.py — dist/ 离线可用性审计（配合 pack.py 的后处理）。

检查每个 HTML 里本地 href/src：
- 目录式链接（file:// 会显示目录列表）→ 必须为 0（pack 应已补全 index.html）
- 目标不存在 → 打印清单（weixin:// 等端内 scheme 除外）
用法: python audit_links.py <dist-dir>
"""
import os
import re
import sys
from urllib.parse import unquote

SKIP_SCHEMES = (
    "http://", "https://", "//", "data:", "mailto:", "tel:",
    "javascript:", "weixin://", "tg://",
)

dist = sys.argv[1]
pat = re.compile(r'(?:href|src)="([^"]+)"')
dir_links, missing, checked = [], [], 0
for root, _, files in os.walk(dist):
    for fn in files:
        if not fn.endswith(".html"):
            continue
        p = os.path.join(root, fn)
        content = open(p, encoding="utf-8", errors="ignore").read()
        for m in pat.finditer(content):
            url = m.group(1).split("#")[0].split("?")[0]
            if not url or url.startswith(SKIP_SCHEMES):
                continue
            checked += 1
            tgt = os.path.normpath(os.path.join(root, unquote(url)))
            if url.endswith("/"):
                dir_links.append(f"{os.path.relpath(p, dist)} -> {url}")
            elif not os.path.isfile(tgt):
                missing.append(f"{os.path.relpath(p, dist)} -> {url}")
print(f"checked {checked} local refs")
print(f"DIRECTORY-STYLE links: {len(dir_links)}")
for d in dir_links[:20]:
    print("  DIR:", d)
print(f"MISSING targets: {len(missing)}")
for d in missing[:30]:
    print("  MISS:", d)
sys.exit(1 if (dir_links or missing) else 0)
