#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""slim_pdfs.py — PDF 链接外置（老 nuke_pdfs.py 泛化）。

把 docs/** 下 md 里本地 .pdf 引用改写到 profile.pdf_base + 文件名，
几十 MB 的 PDF 不进离线包。pdf_base 为空则跳过（如 mio）。
用法: python slim_pdfs.py --docs <docs-dir> --pdf-base https://xxx/documents/
"""
import argparse
import os
import re

RE_MD = re.compile(r"\[([^\]]+)\]\([^)]*?([^/)\s]+\.pdf)\)")
RE_HTML = re.compile(r"href=[\"'][^\"']*?([^/\"']+\.pdf)[\"']")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", required=True)
    ap.add_argument("--pdf-base", default="")
    args = ap.parse_args()
    if not args.pdf_base:
        print("slim_pdfs skipped: empty pdf_base")
        return
    base = args.pdf_base.rstrip("/") + "/"
    n = 0
    for root, _, files in os.walk(args.docs):
        if ".vitepress" in root:
            continue
        for fn in files:
            if not fn.endswith(".md"):
                continue
            p = os.path.join(root, fn)
            with open(p, encoding="utf-8") as f:
                content = f.read()
            content, c1 = RE_MD.subn(lambda m: f"[{m.group(1)}]({base}{m.group(2)})", content)
            content, c2 = RE_HTML.subn(lambda m: f'href="{base}{m.group(1)}"', content)
            if c1 + c2:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(content)
                n += c1 + c2
    print(f"slim_pdfs done: redirected {n} links to {base}")

    # 链接已全部外链，本地 PDF 不再进包（VitePress 会把 public/** 原样拷进 dist）
    freed = 0
    for root, _, files in os.walk(args.docs):
        if ".vitepress" in root:
            continue
        for fn in files:
            if fn.lower().endswith(".pdf"):
                p = os.path.join(root, fn)
                freed += os.path.getsize(p)
                os.remove(p)
    print(f"slim_pdfs done: deleted local PDFs, freed {freed/1048576:.1f}MB")


if __name__ == "__main__":
    main()
