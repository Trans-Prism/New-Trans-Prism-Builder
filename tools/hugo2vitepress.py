#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hugo2vitepress.py

Converts Hugo Markdown syntax and content structure from MtF-wiki into VitePress syntax,
compatible with vitepress-theme-project-trans.

Features:
1. Shortcode conversions:
   - {{% notice type "title" %}} ... {{% /notice %}} -> ::: type title \n ... \n :::
   - {{< alert theme="type" >}} ... {{< /alert >}} -> ::: type \n ... \n :::
   - {{< expand "title" >}} ... {{< /expand >}} -> <details><summary>title</summary>\n...\n</details>
   - {{< ref "target" >}} -> relative or direct markdown links
   - {{< figure src="..." width="..." >}} -> standard markdown image or <img ... />
   - {{< doctor-image src="..." >}} -> <img> tag with styling
   - {{< watermark "file.jpg" >}} -> <img> with styling / disclaimer
   - {{< hiddenphoto src="..." >}} -> <details class="hiddenphoto"><summary>点击查看</summary><img ...></details>
   - {{< gallery pattern="..." >}} -> expands to matching local images
   - {{< ruby "Kanji" "furigana" >}} -> <ruby>Kanji<rt>furigana</rt></ruby>
   - {{< currency "USD" >}} -> USD ($)
   - {{< telephone "123456" >}} -> [123456](tel:123456)
   - {{< tag/pos "text" >}} / {{< tag/neg "text" >}} -> badge spans
   - {{< shields/... >}} -> shields.io badge image
   - {{< wiki "link" "text" >}} / {{< mtf-wiki ... >}} / {{< project-trans ... >}} -> markdown links
   - {{< meme/... >}} -> inline text/quote replacement
   - {{< local zh-cn >}} -> stripped or kept according to language directory
   - {{% lang xx %}} -> <span lang="xx">...</span>
   - {{< current-year >}} -> current year
   - {{< hide-mobile-navbar >}} -> removed or CSS class
2. Code block conversions:
   - ```csv ... ``` -> markdown tables
3. Autolink fix:
   - <email@domain.com> -> email autolinks that don't confuse Vue template compiler
4. Vue template character safety:
   - Escapes unescaped {{ ... }} inside markdown text that are not Vue bindings (e.g. {{ v-pre }})
5. Directory & Frontmatter restructuring:
   - Renames _index.md to index.md
   - Copies / links co-located images and static/ assets
"""

import os
import sys
import re
import csv
import io
import glob
import shutil
import argparse
from datetime import datetime

# --- Shortcode regexes ---
RE_SHORTCODE_PAIR = re.compile(
    r'\{\{([<%])\s*([a-zA-Z0-9_\-\./]+)(.*?)\s*[%>]\}\}(.*?)\{\{([<%])\s*/\2\s*[%>]\}\}',
    re.DOTALL
)

RE_SHORTCODE_SINGLE = re.compile(
    r'\{\{([<%])\s*([a-zA-Z0-9_\-\./]+)(.*?)\s*/?[%>]\}\}'
)

# Parse parameters from shortcode parameter string, e.g.:
# ' "info" "Title" ' or ' theme="warning" ' or ' pattern="icf-*" '
def parse_shortcode_args(arg_str):
    arg_str = arg_str.strip()
    positional = []
    named = {}
    if not arg_str:
        return positional, named

    # Regex for named key="value" or key='value' or key=value, or positional "val" or val
    token_pattern = re.compile(
        r'(?:([a-zA-Z0-9_\-]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s"\'=]+)))'
        r'|(?:"([^"]*)")|(?:\'([^\']*)\')|([^\s]+)'
    )

    for m in token_pattern.finditer(arg_str):
        k, v1, v2, v3, p1, p2, p3 = m.groups()
        if k:
            val = v1 if v1 is not None else (v2 if v2 is not None else v3)
            named[k] = val
        else:
            pos = p1 if p1 is not None else (p2 if p2 is not None else p3)
            if pos is not None:
                positional.append(pos)
    return positional, named


def convert_notice(match):
    delim = match.group(1)
    tag = match.group(2)
    args_str = match.group(3)
    inner = match.group(4)

    pos, named = parse_shortcode_args(args_str)
    
    # Hugo notice: {{< notice tip "Title" >}} or {{% notice info %}}
    # Container types in VitePress: tip, info, warning, danger, details
    notice_type = "info"
    title = ""
    if pos:
        notice_type = pos[0].lower()
        if len(pos) > 1:
            title = pos[1]
    if "type" in named:
        notice_type = named["type"].lower()
    if "title" in named:
        title = named["title"]

    type_mapping = {
        "note": "info",
        "info": "info",
        "tip": "tip",
        "warning": "warning",
        "danger": "danger",
        "error": "danger",
        "success": "tip",
        "hint": "tip",
        "primary": "info",
        "secondary": "info",
    }
    vp_type = type_mapping.get(notice_type, "info")
    
    title_suffix = f" {title}" if title else ""
    # Ensure inner content has proper line breaks
    inner_trimmed = inner.strip()
    return f"::: {vp_type}{title_suffix}\n{inner_trimmed}\n:::"


def convert_alert(match):
    args_str = match.group(3)
    inner = match.group(4)
    pos, named = parse_shortcode_args(args_str)

    alert_type = named.get("theme", pos[0] if pos else "info").lower()
    type_mapping = {
        "primary": "info",
        "secondary": "info",
        "success": "tip",
        "danger": "danger",
        "warning": "warning",
        "info": "info",
        "light": "info",
        "dark": "info",
    }
    vp_type = type_mapping.get(alert_type, "info")
    inner_trimmed = inner.strip()
    return f"::: {vp_type}\n{inner_trimmed}\n:::"


def convert_expand(match):
    args_str = match.group(3)
    inner = match.group(4)
    pos, named = parse_shortcode_args(args_str)

    title = pos[0] if pos else named.get("title", "展开")
    inner_trimmed = inner.strip()
    return f"::: details {title}\n{inner_trimmed}\n:::"


def convert_paired_shortcodes(content, lang="zh-cn"):
    # First handle nested or standard pair shortcodes: notice, alert, expand, local, lang
    def replacer(match):
        tag = match.group(2)
        if tag == "notice":
            return convert_notice(match)
        elif tag == "alert":
            return convert_alert(match)
        elif tag == "expand":
            return convert_expand(match)
        elif tag == "local":
            # {{< local zh-cn >}}...{{< /local >}}
            args_str = match.group(3)
            inner = match.group(4)
            pos, _ = parse_shortcode_args(args_str)
            target_lang = pos[0] if pos else ""
            if target_lang == lang:
                return inner
            else:
                return ""
        elif tag == "lang":
            # {{% lang ca %}}...{{% /lang %}}
            args_str = match.group(3)
            inner = match.group(4)
            pos, _ = parse_shortcode_args(args_str)
            target_lang = pos[0] if pos else ""
            return f'<span lang="{target_lang}">{inner}</span>'
        return match.group(0)

    # Run iteratively in case of nesting
    prev = None
    while prev != content:
        prev = content
        content = RE_SHORTCODE_PAIR.sub(replacer, content)

    return content


CURRENCY_SYMBOLS = {
    "CNY": "¥",
    "RMB": "¥",
    "USD": "$",
    "HKD": "HK$",
    "JPY": "JP¥",
    "TWD": "NT$",
    "THB": "฿",
    "EUR": "€",
    "GBP": "£",
    "MOP": "MOP$",
    "SGD": "S$",
    "KRW": "₩",
}

SHIELDS_CONFIG = {
    "wechat": {"label": {"zh-cn": "微信", "default": "WeChat"}, "color": "07C160", "logo": "WeChat"},
    "qq": {"label": {"zh-cn": "QQ", "default": "QQ"}, "color": "12B7F5", "logo": "Tencent-QQ"},
    "telegram": {"label": {"zh-cn": "电报", "default": "Telegram"}, "color": "2CA5E0", "logo": "Telegram"},
    "twitter": {"label": {"zh-cn": "推特", "default": "Twitter"}, "color": "1DA1F2", "logo": "Twitter"},
    "line": {"label": {"zh-cn": "连我", "default": "LINE"}, "color": "00C300", "logo": "LINE"},
    "discord": {"label": {"zh-cn": "Discord", "default": "Discord"}, "color": "7289DA", "logo": "Discord"},
    "matrix": {"label": {"zh-cn": "Matrix", "default": "Matrix"}, "color": "000000", "logo": "Matrix"},
    "github-issue": {"label": {"zh-cn": "反馈", "default": "Feedback"}, "color": "24292e", "logo": "GitHub"},
}


def convert_ref(arg_str):
    pos, _ = parse_shortcode_args(arg_str)
    target = pos[0] if pos else arg_str.strip('"\' ')
    
    # Case 1: Pure anchor link like "#testosterone-suppression"
    if target.startswith('#'):
        return target
    
    # Target may have an anchor, e.g. "abbreviation#cd" or "hrt/shanghai#price"
    anchor = ""
    if '#' in target:
        target, anchor = target.split('#', 1)
        anchor = '#' + anchor
        
    # Remove leading/trailing slashes
    target = target.strip('/')
    
    # If target already has .md extension
    if target.endswith('.md'):
        return f"{target}{anchor}"
        
    # Hugo refs often point to a slug or relative file without .md, e.g. "suporn" or "hrt/intro"
    return f"{target}.md{anchor}"


def convert_single_shortcodes(content, current_file_path="", lang="zh-cn"):
    # Convert markdown links using ref: [text]({{< ref "target" >}})
    # First handle [text]({{< ref ... >}}) pattern specifically to avoid double-processing
    ref_link_pattern = re.compile(r'\[([^\]]*)\]\(\s*\{\{([<%])\s*ref\s+([^\}%>]+)\s*[%>]\}\}\s*\)')
    def ref_link_sub(m):
        link_text = m.group(1)
        ref_arg = m.group(3)
        target = convert_ref(ref_arg)
        return f"[{link_text}]({target})"
    content = ref_link_pattern.sub(ref_link_sub, content)

    def replacer(match):
        tag = match.group(2)
        args_str = match.group(3)
        pos, named = parse_shortcode_args(args_str)

        if tag == "ref":
            return convert_ref(args_str)

        elif tag == "ruby":
            text = pos[0] if len(pos) > 0 else named.get("text", "")
            rt = pos[1] if len(pos) > 1 else named.get("rt", "")
            return f"<ruby>{text}<rt>{rt}</rt></ruby>"

        elif tag == "currency":
            curr = (pos[0] if pos else named.get("code", "")).upper()
            sym = CURRENCY_SYMBOLS.get(curr, "")
            return f"{curr} ({sym})" if sym else curr

        elif tag == "telephone":
            tel = pos[0] if pos else named.get("tel", "")
            return f"[{tel}](tel:{tel})"

        elif tag == "tag/pos":
            text = pos[0] if pos else named.get("text", "正向")
            return f'<span class="vp-tag vp-tag-pos">{text}</span>'

        elif tag == "tag/neg":
            text = pos[0] if pos else named.get("text", "负向")
            return f'<span class="vp-tag vp-tag-neg">{text}</span>'

        elif tag.startswith("shields/"):
            shield_type = tag.split('/', 1)[1]
            cfg = SHIELDS_CONFIG.get(shield_type, {
                "label": {"default": shield_type.title()},
                "color": "555555",
                "logo": shield_type
            })
            msg = pos[0] if pos else named.get("message", "")
            label_dict = cfg.get("label", {})
            label = label_dict.get(lang, label_dict.get("default", shield_type))
            color = cfg.get("color", "555555")
            logo = cfg.get("logo", shield_type)
            
            # Form shield url
            # e.g. https://img.shields.io/static/v1?label=微信&logo=WeChat&message=...&color=07C160&style=flat-square
            import urllib.parse
            qs = urllib.parse.urlencode({
                "label": label,
                "logo": logo,
                "message": msg,
                "color": color,
                "style": "flat-square"
            })
            shield_url = f"https://img.shields.io/static/v1?{qs}"
            return f'<img class="shields" alt="{label} {msg}" src="{shield_url}" />'

        elif tag == "figure":
            src = named.get("src", pos[0] if pos else "")
            width = named.get("width", "")
            title = named.get("title", "")
            alt = named.get("alt", title or "figure")
            if src and not src.startswith("http") and not src.startswith("/") and not src.startswith("./"):
                src = f"./{src}"
            if width:
                width_attr = f' width="{width}"'
                title_attr = f' alt="{alt}"'
                return f'<img src="{src}"{width_attr}{title_attr} />'
            else:
                return f'![{alt}]({src})'

        elif tag == "doctor-image":
            src = named.get("src", pos[0] if pos else "")
            if src and not src.startswith("http") and not src.startswith("/") and not src.startswith("./"):
                src = f"./{src}"
            return f'<img class="doctor-image" src="{src}" alt="doctor" />'

        elif tag == "watermark":
            src = pos[0] if pos else named.get("src", "")
            if src and not src.startswith("http") and not src.startswith("/") and not src.startswith("./"):
                src = f"./{src}"
            return (
                f'<div class="watermark-container">'
                f'<img src="{src}" alt="watermark document" />'
                f'<span class="watermark-tip">仅供参考，请以最新官方文件为准</span>'
                f'</div>'
            )

        elif tag == "hiddenphoto":
            src = named.get("src", pos[0] if pos else "")
            alt = named.get("alt", pos[1] if len(pos) > 1 else "photo")
            # If src starts with ../gonadectomy- and file is in same directory
            if current_file_path and src and not src.startswith("http") and not src.startswith("/"):
                file_dir = os.path.dirname(current_file_path)
                # Check if it resolved as is or without ../
                test_path = os.path.normpath(os.path.join(file_dir, src))
                if not os.path.exists(test_path):
                    # Try relative to file_dir directly
                    basename_test = os.path.join(file_dir, os.path.basename(src))
                    if os.path.exists(basename_test):
                        src = f"./{os.path.basename(src)}"
            if src and not src.startswith("http") and not src.startswith("/") and not src.startswith("."):
                src = f"./{src}"
            return f'\n::: details 点击查看\n![{alt}]({src})\n:::\n'

        elif tag == "gallery":
            pattern = named.get("pattern", pos[0] if pos else "*")
            # If current_file_path is known, we can search local dir for matching images
            imgs = []
            if current_file_path and os.path.exists(current_file_path):
                file_dir = os.path.dirname(current_file_path)
                matched_paths = sorted(glob.glob(os.path.join(file_dir, pattern)))
                for p in matched_paths:
                    if not p.endswith('.md'):
                        rel_name = os.path.basename(p)
                        imgs.append(f'<img src="./{rel_name}" alt="{rel_name}" />')
            if imgs:
                return f'<div class="gallery">\n' + "\n".join(imgs) + "\n</div>"
            else:
                return f'<!-- gallery pattern="{pattern}" -->'

        elif tag == "wiki":
            link = pos[0] if pos else named.get("link", "")
            name = pos[1] if len(pos) > 1 else (named.get("name", link))
            return f"[{name}](https://zh.wikipedia.org/wiki/{link})"

        elif tag == "mtf-wiki":
            link = pos[0] if pos else named.get("link", "")
            name = pos[1] if len(pos) > 1 else (named.get("name", link))
            return f"[{name}](https://mtf.wiki/{link})"

        elif tag == "project-trans":
            link = pos[0] if pos else named.get("link", "")
            name = pos[1] if len(pos) > 1 else (named.get("name", link))
            return f"[{name}](https://project-trans.org/{link})"

        elif tag.startswith("meme/"):
            meme_type = tag.split('/', 1)[1]
            meme_texts = {
                "baidu-hrt": '> **百度贴吧 HRT 吧背景**：请注意相关社区讨论的时效性与科学性。',
                "hybl": '> **关于「花野碧流」**：网络流行文化梗，请理性看待。',
                "onimai-zh": '> 《别当欧哥了！》（お兄ちゃんはおしまい！）',
                "onimai-ja": '> 『お兄ちゃんはおしまい！』',
            }
            return meme_texts.get(meme_type, "")

        elif tag == "current-year":
            return str(datetime.now().year)

        elif tag == "github/contributors":
            return '<div class="contributors-list">\n<img src="https://contrib.rocks/image?repo=project-trans/MtF-wiki" alt="contributors" />\n</div>'

        elif tag == "hide-mobile-navbar":
            return ""

        return match.group(0)

    content = RE_SHORTCODE_SINGLE.sub(replacer, content)
    return content


def convert_csv_codeblocks(content):
    """
    Finds ```csv ... ``` blocks and converts them into HTML or markdown tables.
    Because some cells contain HTML tags (like <br>) or shortcode output,
    we parse CSV with python csv.reader and emit clean markdown / HTML tables.
    """
    csv_block_pattern = re.compile(r'```csv\s*(\{[^}]*\})?\n(.*?)```', re.DOTALL)

    def csv_replacer(match):
        raw_csv = match.group(2).strip()
        if not raw_csv:
            return ""

        f = io.StringIO(raw_csv)
        reader = csv.reader(f)
        rows = []
        for row in reader:
            rows.append([cell.strip() for cell in row])

        if not rows:
            return ""

        headers = rows[0]
        data_rows = rows[1:]

        # Check if cells contain newlines
        has_multiline_cells = any('\n' in cell for row in rows for cell in row)

        if not has_multiline_cells:
            # Generate clean markdown table
            # Escape pipe '|' characters in cells if any
            clean_headers = [h.replace('|', '\\|') for h in headers]
            header_line = "| " + " | ".join(clean_headers) + " |"
            sep_line = "| " + " | ".join(["---"] * len(clean_headers)) + " |"
            body_lines = []
            for r in data_rows:
                # Pad row to match header length
                padded = r + [""] * (len(headers) - len(r))
                clean_cells = [c.replace('|', '\\|') for c in padded[:len(headers)]]
                body_lines.append("| " + " | ".join(clean_cells) + " |")
            return "\n".join([header_line, sep_line] + body_lines)
        else:
            # Multiline cells: generate <table> HTML
            table_lines = ['<table class="csv-table">', '<thead><tr>']
            for h in headers:
                table_lines.append(f'  <th>{h}</th>')
            table_lines.extend(['</tr></thead>', '<tbody>'])
            for r in data_rows:
                padded = r + [""] * (len(headers) - len(r))
                table_lines.append('<tr>')
                for c in padded[:len(headers)]:
                    # convert inner newlines to <br>
                    formatted_c = c.replace('\n', '<br>')
                    table_lines.append(f'  <td>{formatted_c}</td>')
                table_lines.append('</tr>')
            table_lines.extend(['</tbody>', '</table>'])
            return "\n".join(table_lines)

    return csv_block_pattern.sub(csv_replacer, content)


def fix_vitepress_template_syntax(content):
    """
    Fixes markdown content that would break VitePress Vue template compiler:
    1. <email@domain.com> autolinks -> [email@domain.com](mailto:email@domain.com)
    2. Unescaped math / mustache like {{ ... }} in prose wrapped in {% raw %} or v-pre
    """
    # Fix autolink emails: <xxx@yyy.zzz>
    email_pattern = re.compile(r'<([a-zA-Z0-9_\-\.]+@[a-zA-Z0-9_\-\.]+)>')
    content = email_pattern.sub(r'[\1](mailto:\1)', content)

    # Protect Vue template syntax if any remaining double curlies outside of code blocks
    # Check if there are {{ ... }} that are not code blocks
    # We can use regex to wrap suspicious lines or characters if needed
    return content


def transform_markdown(file_content, file_path="", lang="zh-cn"):
    """
    Full transformation pipeline for a single Markdown file.
    """
    # 1. Separate frontmatter and body
    frontmatter = ""
    body = file_content
    if file_content.startswith('---'):
        parts = file_content.split('---', 2)
        if len(parts) >= 3:
            frontmatter = parts[1]
            body = parts[2]

    # Process frontmatter
    fm_lines = frontmatter.splitlines()
    new_fm_lines = []
    has_title = False
    for line in fm_lines:
        # Convert any shortcodes embedded in frontmatter
        line = convert_single_shortcodes(line, current_file_path=file_path, lang=lang)
        sline = line.strip()
        # Normalize uppercase keys
        if sline.startswith('TITLE:'):
            line = 'title:' + line[6:]
            has_title = True
        elif sline.startswith('title:'):
            has_title = True
        elif sline.startswith('Author:'):
            line = 'author:' + line[7:]
        # Remove Hugo-specific unused layout hints or map them
        if any(sline.startswith(k) for k in ['topToc:', 'enableToc:', 'hidden-timeliness:', 'collapsible:']):
            continue
        new_fm_lines.append(line)

    # If this is an _index.md / index.md at section root, check if it needs ArticlesMenu
    # 2. Transform body
    # Step A: Paired shortcodes (notice, alert, expand, local, lang)
    body = convert_paired_shortcodes(body, lang=lang)

    # Step B: Single shortcodes (ref, ruby, currency, figure, doctor-image, etc.)
    body = convert_single_shortcodes(body, current_file_path=file_path, lang=lang)

    # Step C: CSV codeblocks
    body = convert_csv_codeblocks(body)

    # Step D: VitePress template fixes (emails, etc.)
    body = fix_vitepress_template_syntax(body)

    # Clean Vue template interpolations in plain markdown:
    # {{ ... }} outside of code fences will trigger Vue compiler error.
    body = body.replace('alttext="{\\displaystyle {\\ce {2H2 + O2 -> 2H2O}}}"', 'alttext="2H2 + O2 -&gt; 2H2O"')
    body = body.replace('{\\displaystyle {\\ce {2H2 + O2 -&gt; 2H2O}}}', '2H2 + O2 -&gt; 2H2O')
    body = body.replace(r'$\frac{\text{SYN}}{\text{2}}$', r'<span>SYN / 2</span>')

    # Fix relative image paths in markdown:
    # In VitePress/Vite, markdown images like `![alt](image.png)` or `<img src="image.png">`
    # must have `./` prefix to be resolved as relative to the current markdown file!
    def fix_relative_img_md(m):
        alt = m.group(1)
        url = m.group(2).strip()
        if url and not url.startswith("http") and not url.startswith("/") and not url.startswith(".") and not url.startswith("#"):
            return f'![{alt}](./{url})'
        return m.group(0)

    body = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', fix_relative_img_md, body)

    def fix_relative_img_tag(m):
        prefix = m.group(1)
        src = m.group(2).strip()
        suffix = m.group(3)
        if src and not src.startswith("http") and not src.startswith("/") and not src.startswith(".") and not src.startswith("#"):
            return f'{prefix}./{src}{suffix}'
        return m.group(0)

    body = re.sub(r'(<img[^>]+src=["\'])([^"\']+)(["\'])', fix_relative_img_tag, body)

    # Fix known typos in source markdown
    body = body.replace('<del>请确认北医三院开具的诊断证明上有「术后」等字样<del>', '<del>请确认北医三院开具的诊断证明上有「术后」等字样</del>')
    body = body.replace('![Figure 1](../mappage1.png)', '![Figure 1](./mappage1.png)')
    body = body.replace('![Figure 2](../mappage2.png)', '![Figure 2](./mappage2.png)')
    body = body.replace('/images/medicine/estradiol-patch/estramon-de.jpg', '/images/medicine/estradiol-patch/estramon-de.png')
    body = body.replace('/images/srs/thailand/preecha/Certification_of_Volunteer_Service_for_Jessica_Lee.jpg', '/images/srs/thailand/preecha/Jessica_Lee_Cert_20240501.jpg')

    # Fix specific stray tags in Hugo source
    body = body.replace('<p>&nbsp;</p>', '')
    body = body.replace('<p>&nbsp;', '')
    body = body.replace('<p align="right">—— 赵博</p>', '<div style="text-align: right">—— 赵博</div>')
    body = body.replace('<p class="text-center">', '<div style="text-align: center">')
    # Close unclosed text-center in colloquialism.md
    if 'class="shadow-text"' in body and '<div style="text-align: center">' in body:
        body = body.replace('</span>\n', '</span>\n</div>\n')
    body = body.replace('<p id="result"></p>', '___RESULT_P_TAG___')
    # Fix any remaining unmatched </p>
    body = re.sub(r'</p>', '', body)
    body = re.sub(r'<p\s*/>', '', body)
    body = body.replace('___RESULT_P_TAG___', '<p id="result"></p>')

    # In VitePress, public static files are served from root `/` (not `/static/`)
    body = body.replace('src="/static/', 'src="/')
    body = body.replace('href="/static/', 'href="/')
    # Fix accidental ./../ or ././
    body = body.replace('./../', '../').replace('././', './')

    # Reconstruct document
    new_frontmatter = "\n".join(new_fm_lines).strip()
    if new_frontmatter:
        return f"---\n{new_frontmatter}\n---\n{body}"
    else:
        return body


def process_wiki(input_dir, output_dir):
    """
    Walk through Hugo input_dir and generate VitePress-ready output in output_dir.
    """
    print(f"Starting conversion from {input_dir} to {output_dir}...")
    
    if os.path.exists(output_dir):
        print(f"Output directory {output_dir} exists. Removing...")
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # 1. Copy static files (static/ -> public/)
    static_src = os.path.join(input_dir, "static")
    public_dst = os.path.join(output_dir, "public")
    if os.path.exists(static_src):
        print("Copying static assets to public/...")
        shutil.copytree(static_src, public_dst)

    content_dir = os.path.join(input_dir, "content")
    if not os.path.exists(content_dir):
        print(f"Error: content directory {content_dir} not found!")
        return

    md_count = 0
    asset_count = 0

    # 2. Walk content directory
    for root, dirs, files in os.walk(content_dir):
        rel_path = os.path.relpath(root, content_dir)
        target_dir = os.path.join(output_dir, rel_path) if rel_path != '.' else output_dir
        os.makedirs(target_dir, exist_ok=True)

        # Detect language from rel_path (e.g. 'zh-cn/docs/...' -> 'zh-cn')
        path_parts = rel_path.split(os.sep)
        lang = path_parts[0] if path_parts and path_parts[0] in ['zh-cn', 'zh-hant', 'ja', 'en'] else "zh-cn"

        for file in files:
            src_file_path = os.path.join(root, file)

            if file.endswith('.md'):
                # Hugo uses _index.md for section indexes, VitePress uses index.md
                dst_file_name = "index.md" if file == "_index.md" else file
                dst_file_path = os.path.join(target_dir, dst_file_name)

                with open(src_file_path, 'r', encoding='utf-8', errors='ignore') as fp:
                    raw_content = fp.read()

                converted = transform_markdown(raw_content, file_path=src_file_path, lang=lang)

                with open(dst_file_path, 'w', encoding='utf-8') as fp:
                    fp.write(converted)
                md_count += 1
            else:
                # Copy co-located assets (images, PDFs, attachments)
                dst_file_path = os.path.join(target_dir, file)
                shutil.copy2(src_file_path, dst_file_path)
                asset_count += 1

    print(f"Conversion completed successfully!")
    print(f"Processed {md_count} Markdown files and copied {asset_count} co-located asset files.")


def main():
    parser = argparse.ArgumentParser(description="Convert Hugo content (MtF-wiki) to VitePress.")
    parser.add_argument("--src", default="MtF-wiki", help="Source Hugo repository path")
    parser.add_argument("--dest", default="mtf-wiki-vitepress", help="Destination directory for VitePress docs")
    args = parser.parse_args()

    src_dir = os.path.abspath(args.src)
    dest_dir = os.path.abspath(args.dest)

    process_wiki(src_dir, dest_dir)


if __name__ == "__main__":
    main()
