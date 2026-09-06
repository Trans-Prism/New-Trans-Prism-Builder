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


# FtM 重度使用 Hugo shortcode（MtF 几乎不用）：转换器原样透传，Vue 构建直接炸。
# 这里按 FtM 主题的 shortcode 语义转成标准 md（无 shortcode 的站是 no-op）。
SC_OPEN = r"\{\{[<%]\s*"
SC_CLOSE = r"\s*[>%]\}\}"


def page_index(docs_dir):
    """slug → (relpath, title)：兼容 Hugo GetPage 的常用写法。"""
    pages = {}

    def title_of(path):
        title = None
        with open(path, encoding="utf-8", errors="ignore") as f:
            head = f.read(1500)
        m = re.search(r"^linkTitle:\s*[\"']?(.+?)[\"']?\s*$", head,
                      re.MULTILINE)
        if not m:
            m = re.search(r"^title:\s*[\"']?(.*?)[\"']?\s*$", head,
                          re.MULTILINE)
        if m:
            title = m.group(1).strip()
        return title or os.path.splitext(os.path.basename(path))[0]

    for root, _, files in os.walk(docs_dir):
        for fn in files:
            if not fn.endswith(".md"):
                continue
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, docs_dir).replace(os.sep, "/")
            noext = rel[:-3]
            title = title_of(p)
            if fn in ("index.md", "_index.md"):
                key = os.path.dirname(rel)
                key = "" if key == "." else key
                pages.setdefault(key, (rel, title))
                if key:
                    pages.setdefault(os.path.basename(key), (rel, title))
            else:
                pages.setdefault(noext, (rel, title))
                pages.setdefault(os.path.splitext(fn)[0], (rel, title))
    return pages


def load_abbr(src_root):
    """data/abbreviation.<lang>.yaml → {KEY: {title, origin, href}}。"""
    data_dir = os.path.join(src_root, "data")
    if not os.path.isdir(data_dir):
        return {}
    best, cand = {}, None
    for fn in os.listdir(data_dir):
        if fn.startswith("abbreviation.") and fn.endswith((".yaml", ".yml")):
            cand = os.path.join(data_dir, fn)
            if "zh-cn" in fn or "zh_cn" in fn:
                best = cand
                break
    target = best or cand
    if not target or yaml is None:
        return {}
    with open(target, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def convert_shortcodes(docs_dir, src_root):
    pages = page_index(docs_dir)
    abbr = load_abbr(src_root)
    stats = {"page": 0, "ref": 0, "wiki": 0, "abbr": 0, "box": 0,
             "figure": 0, "mol": 0, "miss": []}

    def resolve(slug):
        slug = slug.strip().strip("/")
        return pages.get(slug)

    for root, _, files in os.walk(docs_dir):
        for fn in files:
            if not fn.endswith(".md"):
                continue
            p = os.path.join(root, fn)
            with open(p, encoding="utf-8") as f:
                content = f.read()
            orig = content

            # {{< page "slug" >}} → [title](relpath)
            def sub_page(m):
                hit = resolve(m.group(1))
                if not hit:
                    stats["miss"].append(f"{os.path.relpath(p, docs_dir)}: page {m.group(1)}")
                    return m.group(1)
                rel, title = hit
                relurl = os.path.relpath(rel, os.path.dirname(
                    os.path.relpath(p, docs_dir)) or ".").replace(os.sep, "/")
                stats["page"] += 1
                return f"[{title}]({relurl})"
            content = re.sub(SC_OPEN + r"page\s+\"([^\"]+)\"" + SC_CLOSE, sub_page, content)

            # {{< ref "slug#anchor" >}} → slug#anchor（常嵌在 [t](...) 里当 URL）
            def sub_ref(m):
                stats["ref"] += 1
                return m.group(1).strip()
            content = re.sub(SC_OPEN + r"(?:ref|relref)\s+\"([^\"]+)\"" + SC_CLOSE, sub_ref, content)

            # {{< wiki "Name|text" lang >}} → [text](https://lang.wikipedia.org/wiki/Name)
            def sub_wiki(m):
                parts = m.group(1).split("|")
                name = parts[0].strip()
                text = parts[1].strip() if len(parts) > 1 else name
                lang = (m.group(2) or "zh").strip()
                stats["wiki"] += 1
                return f"[{text}](https://{lang}.wikipedia.org/wiki/{name.replace(' ', '_')})"
            content = re.sub(SC_OPEN + r"wiki\s+\"([^\"]+)\"(?:\s+(\w+))?" + SC_CLOSE, sub_wiki, content)

            # {{< abbr KEY >}} → <abbr title="origin">title</abbr>（KEY 可带引号）
            def sub_abbr(m):
                key = m.group(1).strip()
                hit = abbr.get(key)
                stats["abbr"] += 1
                if not hit:
                    return key
                title = hit.get("title", key)
                origin = hit.get("origin", "")
                tag = f"<abbr title=\"{origin}\">{title}</abbr>"
                if hit.get("href"):
                    return f"[{tag}]({hit['href']})"
                return tag
            content = re.sub(SC_OPEN + r"abbr\s+\"?([A-Za-z0-9_-]+)\"?" + SC_CLOSE, sub_abbr, content)

            # message/notification/text 块：留 inner，message 加标题引用。
            # 块可嵌套（text 常在 message 里），循环到无变化，最内层自然先被外层带走、
            # 后续轮次再解开（成嵌套引用，渲染正常）。
            def sub_box(m):
                kind, title, inner = m.group(1), m.group(2), m.group(3)
                stats["box"] += 1
                lines = inner.strip().split("\n")
                if kind == "message" and title:
                    lines = [f"**{title.strip()}**", ""] + lines
                return "\n".join("> " + ln if ln.strip() else ">" for ln in lines)
            box_pat = re.compile(
                SC_OPEN + r"(message|notification|text)\b([^\n>]*?)" + SC_CLOSE
                + r"(.*?)"
                + SC_OPEN + r"/\1" + SC_CLOSE,
                flags=re.DOTALL)
            for _ in range(5):
                content, c = box_pat.subn(sub_box, content)
                if not c:
                    break

            # 转换器把 wiki 短码洗坏了：[en](https://zh.wikipedia.org/wiki/Name|text)
            # （文本拿了 lang 参数、URL 带空格/管道）。复原为 [text](https://lang.../Name)。
            def sub_wikifix(m):
                lang, host, rest = m.group(1), m.group(2), m.group(3)
                if "|" not in rest:
                    return m.group(0)  # 无管道即正常链接，不碰
                name, text = rest.split("|", 1)
                name = name.strip().replace(" ", "_")
                stats["wiki"] += 1
                return f"[{text.strip()}](https://{lang}.wikipedia.org/wiki/{name})"
            content = re.sub(
                r"\[([a-z]{2,3})\]\((https://[a-z-]+\.wikipedia\.org/wiki/)([^)]+)\)",
                sub_wikifix, content)

            # {{< figure src title >}} → ![title](src)
            def sub_fig(m):
                kv = dict(re.findall(r"(\w+)\s*=\s*\"([^\"]*)\"", m.group(0)))
                stats["figure"] += 1
                return f"![{kv.get('title', '')}]({kv.get('src', '')})"
            content = re.sub(SC_OPEN + r"figure\b[^>]*?" + SC_CLOSE, sub_fig, content)

            # {{< mol "F" >}} → 原式（去下标花活，保构建）
            def sub_mol(m):
                stats["mol"] += 1
                return m.group(1)
            content = re.sub(SC_OPEN + r"mol\s+\"([^\"]+)\"" + SC_CLOSE, sub_mol, content)

            if content != orig:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(content)
    print(f"wash_hugo done: shortcodes "
          f"page={stats['page']} ref={stats['ref']} wiki={stats['wiki']} "
          f"abbr={stats['abbr']} box={stats['box']} figure={stats['figure']} mol={stats['mol']}")
    for m in stats["miss"][:15]:
        print(f"  shortcode-miss: {m}")
    if len(stats["miss"]) > 15:
        print(f"  ... +{len(stats['miss']) - 15} more")


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
    convert_shortcodes(args.dest, os.path.abspath(args.src))


if __name__ == "__main__":
    main()
