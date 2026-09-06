#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wash_vitepress.py — VitePress 上游（rle/mio）轻洗。

只做 MkDocs 时代残留翻译 + 炸弹拆除，保留 Vue 特性（<script setup> 不动，
新链本来就是 VitePress，不需要像 fix_vite_syntax.py 那样物理删除）：
- 删 front-matter 的 `icon:` 行（缺 SVG 会告警刷屏）
- 删独占一行的 `hide: true/false`（旧 YAML 炸弹习惯带过来的）
- 删 `<HomeContent>` 自定义标签（RLE 旧残留）
- `_index.md → index.md` 归一
用法: python wash_vitepress.py --docs <docs-dir>
"""
import argparse
import os
import re

RE_ICON = re.compile(r"^icon:\s*.*$", re.MULTILINE)
RE_HIDE = re.compile(r"^\s*hide:\s*(true|false)\s*$", re.MULTILINE | re.IGNORECASE)
RE_HOME = re.compile(r"</?HomeContent\s*/?>", re.IGNORECASE)


def wash_file(path):
    with open(path, encoding="utf-8") as f:
        content = f.read()
    orig = content
    content = RE_ICON.sub("", content)
    content = RE_HIDE.sub("", content)
    content = RE_HOME.sub("", content)
    if content != orig:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", required=True)
    args = ap.parse_args()

    touched, renamed = 0, 0
    for root, _, files in os.walk(args.docs):
        if ".vitepress" in root:
            continue
        for fn in files:
            p = os.path.join(root, fn)
            if fn == "_index.md":
                os.rename(p, os.path.join(root, "index.md"))
                p = os.path.join(root, "index.md")
                renamed += 1
                fn = "index.md"
            if fn.endswith(".md") and wash_file(p):
                touched += 1
    print(f"wash_vitepress done: washed {touched} files, renamed {renamed} _index.md")


if __name__ == "__main__":
    main()
