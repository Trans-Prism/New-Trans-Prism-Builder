#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_vp.py — 按 profile 生成可构建的 VitePress 工程（不执行 pnpm build）。

- mtf/ftm（theme: project-trans）：docs/ 已由 wash 备好；生成 package.json、
  docs/.vitepress/{config.ts,theme/index.ts,theme/style.css}、uno.config.ts
- rle（reuse_upstream_config）：上游 docs/ 整体拷入 workdir，主题版本 pin 到
  THEME_VERSION（改 package.json 依赖行即可）
- mio（theme: self）：上游 docs/ 拷入；config.ts 里 base 改写为 ./；
  删 strip_scripts 里的外链 script（如 umami）
输出 workdir/ 即 pnpm 工程根，CI 随后 `pnpm install && pnpm build`。
用法: python build_vp.py --profile profiles/mtf.yaml --docs <docs-dir> --workdir <out>
"""
import argparse
import json
import os
import re
import shutil
import subprocess

THEME_VERSION = "^0.9.1761114650"  # 与 RLE-wiki 在用版本对齐
TEMPLATES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates")


def load_profile(path):
    import yaml
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def render(tmpl, mapping):
    with open(os.path.join(TEMPLATES, tmpl), encoding="utf-8") as f:
        s = f.read()
    for k, v in mapping.items():
        s = s.replace("{{" + k + "}}", v)
    return s


def sidebar_json(roots):
    blocks = []
    for r in roots:
        clean_r = r.strip("/")
        if not clean_r:
            # 根目录全局单侧边栏（FtM 等单语言全站通栏模式）
            scan_path = ""
            resolve_path = "/"
        else:
            scan_path = clean_r
            resolve_path = f"/{clean_r}/"
        blocks.append(
            "  {\n    ...baseConfig,\n"
            f'    scanStartPath: {json.dumps(scan_path)},\n'
            f'    resolvePath: {json.dumps(resolve_path)},\n'
            "    sortMenusByFrontmatterOrder: true,\n  }"
        )
    return "[\n" + ",\n".join(blocks) + "\n]"


def git_seed(workdir):
    """主题带的 git-changelog 插件要求工程在 git 仓库里；本地 /tmp 构建时现建一个。

    CI 里 workdir 本就在 checkout 内，git init 无影响（已有仓库则跳过）。"""
    if subprocess.run(["git", "rev-parse", "--git-dir"], cwd=workdir,
                      capture_output=True).returncode == 0:
        return
    env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")
    subprocess.run(["git", "init", "-q"], cwd=workdir, check=True, env=env)
    subprocess.run(["git", "add", "-A"], cwd=workdir, check=True, env=env)
    subprocess.run(["git", "-c", "user.name=vp", "-c", "user.email=vp@local",
                    "commit", "-qm", "seed"], cwd=workdir, check=True, env=env)


def scaffold_project_theme(profile, docs_dir, workdir):
    if os.path.exists(workdir):
        shutil.rmtree(workdir)
    os.makedirs(workdir)
    shutil.copytree(docs_dir, os.path.join(workdir, "docs"))
    vp = os.path.join(workdir, "docs", ".vitepress")
    os.makedirs(os.path.join(vp, "theme"), exist_ok=True)
    with open(os.path.join(workdir, "package.json"), "w", encoding="utf-8") as f:
        f.write(render("package.json.tmpl", {"NAME": profile["name"], "THEME_VERSION": THEME_VERSION}))
    with open(os.path.join(vp, "config.ts"), "w", encoding="utf-8") as f:
        f.write(render("vp_config.ts.tmpl", {
            "NAV_JSON": json.dumps(profile.get("nav", []), ensure_ascii=False, indent=2),
            "SIDEBAR_JSON": sidebar_json(profile.get("sidebar_roots", [])),
            "SITE_TITLE": profile["site_title"],
            "SITE_DESC": profile.get("site_description", ""),
            "REPO_LINK": profile.get("github_repo_link", ""),
            "INCLUDE_JSON": json.dumps(profile.get("include_langs", ["zh-cn"]), ensure_ascii=False),
        }))
    shutil.copy(os.path.join(TEMPLATES, "theme_index.ts"), os.path.join(vp, "theme", "index.ts"))
    open(os.path.join(vp, "theme", "style.css"), "a", encoding="utf-8").close()
    shutil.copy(os.path.join(TEMPLATES, "uno.config.ts"), os.path.join(workdir, "uno.config.ts"))
    shutil.copy(os.path.join(TEMPLATES, "vite.config.ts"), os.path.join(workdir, "docs", "vite.config.ts"))
    # 上游 Hugo 多语言站没有根首页，补一个跳首个 sidebar 根目录的落地页
    #（否则 dist/ 缺 index.html，App 离线无入口）
    # 注意必须跳显式 index.html 文件：file:// 下浏览器不会解析目录 URL，
    # 跳 ./zh-cn/docs/ 会直接显示目录列表而不是页面
    index_md = os.path.join(workdir, "docs", "index.md")
    if not os.path.exists(index_md):
        roots = profile.get("sidebar_roots", ["zh-cn"])
        with open(index_md, "w", encoding="utf-8") as f:
            f.write(
                "---\ntitle: Home\n---\n\n"
                f'<meta http-equiv="refresh" content="0; url=./{roots[0]}/index.html" />\n\n'
                f'正在跳转…如未自动跳转请点击 [{roots[0]}](./{roots[0]}/index.html)\n'
            )
    git_seed(workdir)
    print(f"scaffolded {profile['name']} with project-trans theme")


def passthrough_upstream(profile, upstream_root, docs_sub, workdir):
    """rle/mio：上游 docs/ 整体拷入；mio 改写 base + 剥外链 script。"""
    src = os.path.join(upstream_root, docs_sub)
    if os.path.exists(workdir):
        shutil.rmtree(workdir)
    os.makedirs(workdir)
    shutil.copytree(src, os.path.join(workdir, "docs"),
                    ignore=shutil.ignore_patterns("node_modules", "dist", ".vitepress/cache"))
    # 上游工程根文件（package.json/lock/uno.config）一并拷入，否则 workdir 不是可构建工程
    for fn in ("package.json", "pnpm-lock.yaml", "uno.config.ts"):
        p = os.path.join(upstream_root, fn)
        if os.path.isfile(p):
            shutil.copy(p, os.path.join(workdir, fn))
    # 主题版本 pin（仅 rle 有该依赖）
    pkg = os.path.join(workdir, "package.json")
    if os.path.exists(pkg) and profile.get("theme") == "project-trans":
        with open(pkg, encoding="utf-8") as f:
            content = f.read()
        content = re.sub(
            r'"@project-trans/vitepress-theme-project-trans":\s*"[^"]+"',
            f'"@project-trans/vitepress-theme-project-trans": "{THEME_VERSION}"',
            content,
        )
        with open(pkg, "w", encoding="utf-8") as f:
            f.write(content)
    cfg = os.path.join(workdir, "docs", ".vitepress", "config.ts")
    if not os.path.exists(cfg):
        return
    with open(cfg, encoding="utf-8") as f:
        content = f.read()
    orig = content
    if profile.get("base_overwrite"):
        content = re.sub(r"base:\s*['\"][^'\"]*['\"]", f"base: '{profile['base_overwrite']}'", content)
        for s in profile.get("strip_scripts", []):
            content = re.sub(
                r"\s*\[[^\]]*src[^\]]*" + re.escape(s) + r"[^\]]*\],?", "", content
            )
    # 离线 file:// 不解析目录 URL：上游在线站 cleanUrls:true 全是无后缀链接，
    # 离线包强制 .html 后缀（pack 的审计会验证 0 缺失）
    if profile.get("clean_urls") is False:
        content = re.sub(r"cleanUrls:\s*true", "cleanUrls: false", content)
        if "cleanUrls" not in content:
            content = content.replace(
                "export default withThemeContext(themeConfig, genConfig)",
                "const __offlineConfig = withThemeContext(themeConfig, genConfig)\n"
                "__offlineConfig.cleanUrls = false\n"
                "export default __offlineConfig",
            )
    if content != orig:
        with open(cfg, "w", encoding="utf-8") as f:
            f.write(content)
    git_seed(workdir)
    print(f"passthrough {profile['name']} from {src}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--docs", default="", help="wash 产出的 docs/（hugo 系）")
    ap.add_argument("--upstream", default="", help="上游根目录（vitepress 系直通）")
    ap.add_argument("--workdir", required=True)
    args = ap.parse_args()
    profile = load_profile(args.profile)
    if profile.get("reuse_upstream_config"):
        passthrough_upstream(profile, args.upstream,
                             "docs" if profile["name"] != "mio" else "docs", args.workdir)
    else:
        scaffold_project_theme(profile, args.docs, args.workdir)


if __name__ == "__main__":
    main()
