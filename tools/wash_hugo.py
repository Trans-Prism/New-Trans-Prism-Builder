#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wash_hugo.py — Hugo 上游（mtf/ftm）→ VitePress docs/。

包一层 tools/hugo2vitepress.py 的 process_wiki，再按 profile 做后处理：
- PDF 基址替换为 profile.pdf_base（转换器不管 PDF，只管短码/结构）
- 顶层 README* 归档，避免与 index.md 抢首页
用法: python wash_hugo.py --profile profiles/mtf.yaml --src <hugo-root> --dest <workdir>/docs
"""
import argparse
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hugo2vitepress import process_wiki  # noqa: E402

try:
    import yaml
except ImportError:
    yaml = None


def load_profile(path):
    if yaml is None:  # CI 若缺 pyyaml，用最小解析（只取标量键）
        data = {}
        with open(path, encoding="utf-8") as f:
            for line in f:
                m = re.match(r"^(\w+):\s*[\"']?(.*?)[\"']?\s*$", line)
                if m:
                    data[m.group(1)] = m.group(2)
        return data
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def post_pdf_base(docs_dir, pdf_base):
    if not pdf_base:
        return 0
    n = 0
    pat = re.compile(r"\((?:/static/documents/|(?:\./|\../)*)([^/\s)]+\.pdf)\)")
    for root, _, files in os.walk(docs_dir):
        for fn in files:
            if not fn.endswith(".md"):
                continue
            p = os.path.join(root, fn)
            with open(p, encoding="utf-8") as f:
                content = f.read()
            new, c = pat.subn(lambda m: f"({pdf_base}{m.group(1)})", content)
            if c:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(new)
                n += c
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--src", required=True, help="Hugo 上游根目录（含 content/ static/）")
    ap.add_argument("--dest", required=True, help="输出 VitePress docs/ 目录")
    args = ap.parse_args()

    profile = load_profile(args.profile)
    # process_wiki(src, dst) 把 content/→dst、static/→dst/public
    tmp = args.dest + ".__wash_tmp"
    process_wiki(os.path.abspath(args.src), os.path.abspath(tmp))
    # 转换器把 public/ 放到输出根：tmp/public；docs 内容在 tmp/ 直铺。
    # 目标 docs/ 结构：内容直铺 + public/ 子目录
    if os.path.exists(args.dest):
        shutil.rmtree(args.dest)
    shutil.move(tmp, args.dest)

    n = post_pdf_base(args.dest, profile.get("pdf_base", ""))
    print(f"wash_hugo done: pdf links redirected: {n}")


if __name__ == "__main__":
    main()
