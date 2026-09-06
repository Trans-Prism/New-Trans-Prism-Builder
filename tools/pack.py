#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pack.py — dist/ → ZIP + 体积预算门禁。

- 把 <workdir>/docs/.vitepress/dist 打成 {zip_prefix}-{date}.zip
- 超 profile.budget_mb 直接 exit 1（CI 失败，不推 R2）
- 打印 dist/ 内 Top20 大文件，方便追体积回归
用法: python pack.py --profile profiles/mtf.yaml --workdir <out> [--date 2026-09-03]
"""
import argparse
import datetime
import os
import re
import zipfile

import yaml


def relativize_html_for_file_protocol(dist_dir: str):
    """dist/ HTML 离线双兼容后处理（file:// 直接打开 + shelf 本地 HTTP 托管）。

    1. 绝对引用 /assets/... → 按页面深度改相对路径（./ / ../ / ../../ …）
    2. 目录式链接（./ / ../../ / .../gov/）→ 若对应目录有 index.html 则补全，
       file:// 下浏览器不会解析目录 URL，不补就会显示目录列表
    3. slug页链接（./puth.html）→ 若同名目录有 index.html 则改过去
       （Hugo ref slug  CID  _index.md 的情况）
    4. 删主题注入的 favicon/manifest 引用（离线包不带这些文件，留着白 404）
    5. 删上游已失效的内容死链：目标文件不存在、也没有同名 index 的 <a>，
       退化成纯文本（不断用户阅读，只是不再点进 404）
    幂等：跑多遍结果一致。
    """
    re_attr = re.compile(r'((?:href|src)=["\'])/(?!/)([^"\']*["\'])')
    re_link = re.compile(r'((?:href|src)=")([^"]+)(")')
    re_icon = re.compile(
        r'\s*<link[^>]*rel="(?:apple-touch-icon|icon|manifest)"[^>]*>', re.IGNORECASE)
    count, fixed_dir, fixed_slug, stripped = 0, 0, 0, 0
    for root, _, files in os.walk(dist_dir):
        for fn in files:
            if not fn.endswith(".html"):
                continue
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, dist_dir)
            depth = rel.count(os.sep)
            prefix = "./" if depth == 0 else ("../" * depth)

            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            orig = content
            content = re_attr.sub(rf"\1{prefix}\2", content)

            def fix(m):
                nonlocal fixed_dir, fixed_slug
                attr, url, quote = m.group(1), m.group(2), m.group(3)
                if url.startswith(("http://", "https://", "//", "data:", "mailto:", "tel:")):
                    return m.group(0)
                path = url.split("#")[0].split("?")[0]
                if path.endswith("/"):
                    idx = os.path.normpath(os.path.join(root, path, "index.html"))
                    if os.path.isfile(idx):
                        fixed_dir += 1
                        return attr + url.replace(path, os.path.relpath(idx, root), 1) + quote
                    return m.group(0)
                if path.endswith(".html"):
                    tgt = os.path.normpath(os.path.join(root, path))
                    if not os.path.isfile(tgt):
                        idx = os.path.normpath(os.path.join(root, path[:-5], "index.html"))
                        if os.path.isfile(idx):
                            fixed_slug += 1
                            return attr + url.replace(path, os.path.relpath(idx, root), 1) + quote
                return m.group(0)

            content = re_link.sub(fix, content)
            content, n_strip = re_icon.subn("", content)
            stripped += n_strip

            def unwrap(m):
                nonlocal fixed_slug
                _pre, url, _post, inner = m.group(1), m.group(2), m.group(3), m.group(4)
                if url.startswith(("http://", "https://", "//", "data:", "mailto:", "tel:")):
                    return m.group(0)
                path = url.split("#")[0].split("?")[0]
                if path.endswith("/"):
                    idx = os.path.normpath(os.path.join(root, path, "index.html"))
                    if os.path.isfile(idx):
                        return m.group(0)  # 已在 fix() 处理过
                elif path.endswith(".html"):
                    if os.path.isfile(os.path.normpath(os.path.join(root, path))):
                        return m.group(0)
                    if os.path.isfile(os.path.normpath(os.path.join(root, path[:-5], "index.html"))):
                        return m.group(0)
                else:
                    return m.group(0)
                fixed_slug += 1
                return inner

            content = re.sub(r'(<a\b[^>]*href=")([^"]+)("[^>]*>)((?:(?!</a>).)*)</a>',
                             unwrap, content, flags=re.DOTALL)
            if content != orig:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(content)
                count += 1
    print(f"relativized {count} HTML files "
          f"(dir-links fixed: {fixed_dir}, slug-pages fixed: {fixed_slug}, "
          f"icon tags stripped: {stripped})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--date", default="")
    ap.add_argument("--outdir", default=".",
                    help="ZIP 输出目录（默认当前目录；CI 靠它落到仓库根）")
    args = ap.parse_args()
    with open(args.profile, encoding="utf-8") as f:
        profile = yaml.safe_load(f)
    dist = os.path.join(args.workdir, "docs", ".vitepress", "dist")
    assert os.path.isdir(dist), f"dist not found: {dist}"
    relativize_html_for_file_protocol(dist)
    date = args.date or (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime("%Y-%m-%d")
    folder = f"{profile['zip_prefix']}-{date}"
    os.makedirs(args.outdir, exist_ok=True)
    zip_name = os.path.join(args.outdir, folder + ".zip")

    big = []
    for root, _, files in os.walk(dist):
        for fn in files:
            p = os.path.join(root, fn)
            big.append((os.path.getsize(p), os.path.relpath(p, dist)))
    big.sort(reverse=True)
    print("Top20 in dist/:")
    for sz, rel in big[:20]:
        print(f"  {sz/1048576:7.1f}MB  {rel}")

    with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for root, _, files in os.walk(dist):
            for fn in files:
                p = os.path.join(root, fn)
                z.write(p, os.path.join(folder, os.path.relpath(p, dist)))
    mb = os.path.getsize(zip_name) / 1048576
    budget = float(profile.get("budget_mb", 9999))
    print(f"packed {zip_name}: {mb:.1f}MB (budget {budget:.0f}MB)")
    print(f"TAG_NAME={profile['tag_prefix']}-{date}")
    if mb > budget:
        print(f"OVER BUDGET: {mb:.1f} > {budget:.0f} MB")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
