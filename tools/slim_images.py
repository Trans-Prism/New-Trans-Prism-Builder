#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""slim_images.py — 图片减负（合老 compress_wiki + compress_webp 为一）。

- docs/**（跳过 .vitepress）下 .png/.jpg/.jpeg → 最长边超 max_width 则
  LANCZOS 等比缩放 → 转 RGB → WebP(quality) 存盘 → 删原图
- 已是 .webp 且超 webp_max 则二次降维覆盖
- 同步改 md 引用并保留 ./ 前缀形态：`![a](./x.png)` → `![a](./x.webp`
  （老脚本裸 .png→.webp 会误伤正文文字，这里只改图片/附件引用位）
用法: python slim_images.py --docs <docs-dir> [--max-width 1600] [--quality 75]
"""
import argparse
import os
import re
import shutil
from urllib.parse import unquote

from PIL import Image

Image.MAX_IMAGE_PIXELS = None  # 上游有亿像素医疗图，有意关闭

BITMAP_EXTS = (".png", ".jpg", ".jpeg")
PAGE_ASSET_EXTS = BITMAP_EXTS + (".webp", ".gif", ".bmp", ".svg", ".avif")
# 只改引用位：md 图片 ![..](..)、纯文本附件链 [..](..jpg) 与 <img src="..">
# 注意表格里的图 `| ![a](./x.png) |` 后面跟的不是换行，结尾只锚 `)` 即可
RE_MD_IMG = re.compile(r"(!\[[^\]]*\]\()\s*([^)\s]+)([^)]*\))")
RE_MD_LINK = re.compile(
    r"(?<!!)(\[[^\]]*\]\()\s*([^)\s]+\.(?:png|jpe?g|gif|bmp|webp))([^)]*\))",
    re.IGNORECASE,
)
RE_HTML_SRC = re.compile(r"((?:src|href)=[\"'])(.*?)([\"'])", re.IGNORECASE)


def convert_bitmap(path, max_width, quality):
    """原图→webp 同名替换，返回新路径；失败返回 None。"""
    try:
        with Image.open(path) as img:
            if max(img.size) > max_width:
                ratio = max_width / max(img.size)
                img = img.resize(
                    (int(img.width * ratio), int(img.height * ratio)),
                    Image.Resampling.LANCZOS,
                )
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            webp = os.path.splitext(path)[0] + ".webp"
            img.save(webp, "webp", quality=quality)
        os.remove(path)
        return webp
    except Exception as e:  # noqa: BLE001
        print(f"skip {path}: {e}")
        return None


def shrink_webp(path, webp_max, quality):
    try:
        with Image.open(path) as img:
            if max(img.size) <= webp_max:
                return False
            ratio = webp_max / max(img.size)
            img = img.resize(
                (int(img.width * ratio), int(img.height * ratio)),
                Image.Resampling.LANCZOS,
            )
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            img.save(path, "webp", quality=quality)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"skip {path}: {e}")
        return False


def swap_ext(url, old, new):
    if url.lower().endswith(old.lower()):
        return url[: -len(old)] + new
    return url


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", required=True)
    ap.add_argument("--max-width", type=int, default=1600)
    ap.add_argument("--webp-max", type=int, default=2000)
    ap.add_argument("--quality", type=int, default=75)
    args = ap.parse_args()

    swaps = {}  # 目录内 old_rel_url -> new_rel_url（保持引用目录一致）
    converted, shrunk = 0, 0
    for root, _, files in os.walk(args.docs):
        if ".vitepress" in root:
            continue
        for fn in files:
            p = os.path.join(root, fn)
            low = fn.lower()
            if low.endswith(BITMAP_EXTS):
                new = convert_bitmap(p, args.max_width, args.quality)
                if new:
                    swaps[os.path.relpath(p, args.docs)] = os.path.relpath(new, args.docs)
                    converted += 1
            elif low.endswith(".webp"):
                if shrink_webp(p, args.webp_max, args.quality):
                    shrunk += 1

    # 回写 md 引用：同目录 basename 映射（./x.png → ./x.webp），跨目录用相对路径映射
    # by_base 凭两份来源，保证重跑也能修（本次 swaps + 磁盘上已存在的 .webp 索引）：
    by_base = {}
    for old_rel, new_rel in swaps.items():
        by_base.setdefault(os.path.basename(old_rel).lower(), []).append((old_rel, new_rel))
    for root, _, files in os.walk(args.docs):
        if ".vitepress" in root:
            continue
        for fn in files:
            if fn.lower().endswith(".webp"):
                rel = os.path.relpath(os.path.join(root, fn), args.docs)
                stem = os.path.splitext(fn)[0].lower()
                for ext in BITMAP_EXTS:
                    key = (stem + ext).lower()
                    entry = (os.path.join(os.path.dirname(rel), stem + ext), rel)
                    if entry not in by_base.setdefault(key, []):
                        by_base[key].append(entry)

    def fix_url(url, md_dir):
        if url.startswith(("http://", "https://", "#", "mailto:")):
            return url
        base = os.path.basename(url).lower()
        cands = by_base.get(base)
        if not cands:
            return url
        for old_rel, new_rel in cands:
            if os.path.normpath(os.path.join(md_dir, os.path.dirname(url))) == os.path.normpath(
                os.path.join(args.docs, os.path.dirname(old_rel))
            ):
                return swap_ext(url, os.path.splitext(url)[1], ".webp")
        old_rel, _ = cands[0]
        return swap_ext(url, os.path.splitext(url)[1], ".webp")

    md_fixed = 0
    for root, _, files in os.walk(args.docs):
        if ".vitepress" in root:
            continue
        for fn in files:
            if not fn.endswith(".md"):
                continue
            p = os.path.join(root, fn)
            md_dir = os.path.relpath(root, args.docs)
            with open(p, encoding="utf-8") as f:
                content = f.read()
            orig = content
            content = RE_MD_IMG.sub(
                lambda m: m.group(1) + fix_url(m.group(2).strip(), md_dir) + m.group(3),
                content,
            )
            content = RE_MD_LINK.sub(
                lambda m: m.group(1) + fix_url(m.group(2).strip(), md_dir) + m.group(3),
                content,
            )
            content = RE_HTML_SRC.sub(
                lambda m: m.group(1) + fix_url(m.group(2).strip(), md_dir) + m.group(3),
                content,
            )
            if content != orig:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(content)
                md_fixed += 1

    print(f"slim_images done: converted {converted}, shrunk {shrunk}, md fixed {md_fixed}")

    # Hugo page-bundle 兼容：同目录附件（index.md + proof.webp）被纯文本链引用时，
    # VitePress 不会打包它们（只有 ![..] 会进 bundle、public/** 会原样拷贝）。
    # 把这类文件镜像进 public/ 同位路径并改引用为绝对路径，保证离线可达。
    docs_abs = os.path.abspath(args.docs)
    public_abs = os.path.join(docs_abs, "public")
    bundled = 0
    for root, _, files in os.walk(args.docs):
        if ".vitepress" in root:
            continue
        for fn in files:
            if not fn.endswith(".md"):
                continue
            p = os.path.join(root, fn)
            with open(p, encoding="utf-8") as f:
                content = f.read()
            orig = content

            def bundle_url(url):
                nonlocal bundled
                if url.startswith(
                    ("http://", "https://", "//", "#", "mailto:", "tel:",
                     "data:", "weixin:")
                ):
                    return url
                clean = unquote(url.split("#")[0].split("?")[0].strip())
                if not clean or os.path.splitext(clean)[1].lower() not in PAGE_ASSET_EXTS:
                    return url
                # 绝对路径（/ja/.../x.webp，多为 <image src> 手写）与相对路径都兼容：
                # 只要源文件在 docs 内、public 外，就镜像进 public（绝对引用原文不动即生效）
                if clean.startswith("/"):
                    tgt = os.path.normpath(os.path.join(docs_abs, clean.lstrip("/")))
                else:
                    tgt = os.path.normpath(os.path.join(root, clean))
                if not os.path.isfile(tgt):
                    return url
                if os.path.relpath(tgt, docs_abs).startswith("public" + os.sep):
                    return url
                rel = os.path.relpath(tgt, docs_abs)
                dest = os.path.join(public_abs, rel)
                if not os.path.isfile(dest):
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    shutil.copy2(tgt, dest)
                bundled += 1
                if clean.startswith("/"):
                    return url  # 绝对路径：镜像后原文即生效
                suffix = url[len(url.split("#")[0].split("?")[0]):]
                return "/" + rel.replace(os.sep, "/") + suffix

            content = RE_MD_IMG.sub(
                lambda m: m.group(1) + bundle_url(m.group(2).strip()) + m.group(3),
                content,
            )
            content = RE_MD_LINK.sub(
                lambda m: m.group(1) + bundle_url(m.group(2).strip()) + m.group(3),
                content,
            )
            content = RE_HTML_SRC.sub(
                lambda m: m.group(1) + bundle_url(m.group(2).strip()) + m.group(3),
                content,
            )
            if content != orig:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(content)
    print(f"slim_images done: page-bundle files mirrored to public: {bundled}")


if __name__ == "__main__":
    main()
