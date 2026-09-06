# New-Trans-Prism-Builder 🏭✨

**VitePress 内容构建与分发引擎** — 把 4 个 Wiki 上游洗成 VitePress 站点（3 个套
`@project-trans/vitepress-theme-project-trans`，Mio 用自带主题），减负后
`vitepress build`，打 ZIP 推 Cloudflare R2，供 Trans Prism App 热更新。

这是 `Trans-Prism-Builder`（MkDocs/Material HTML 链）的继任者，两条链
 R2 路径互相隔离：老链 `builder/`，新链 `vp-builder/`（tag/ZIP 命名与老链一致，
 App 切 `vp-builder/latest/` 通道即可）。

## 处理的项目

| 项目 | 上游 | 源码形态 | 主题 | 产物 |
|------|------|---------|------|------|
| MtF Wiki | `project-trans/MtF-wiki` | Hugo | project-trans | `mtf-wiki-site-{date}.zip` |
| FtM Wiki | `project-trans/FtM-wiki` | Hugo | project-trans | `ftm-wiki-site-{date}.zip` |
| RLE Wiki | `project-trans/RLE-wiki` | VitePress | project-trans（复用上游配置） | `rle-wiki-site-{date}.zip` |
| MioMtF Wiki | `KitsuMio/MioMtFWiki` | VitePress | 自带（DefaultTheme+自研CSS） | `miomtfwiki-site-{date}.zip` |

## 流水线

```
fetch → wash → slim → build → pack → release → R2（只留两版）
```

| 步骤 | 工具 | 说明 |
|------|------|------|
| wash（Hugo） | `tools/wash_hugo.py`（包 `hugo2vitepress.py`） | 短码→VitePress 容器、`_index→index`、`static→public` |
| wash（VitePress） | `tools/wash_vitepress.py` | 去 `icon:/hide:` 炸弹、`<HomeContent>` 残留 |
| slim | `tools/slim_images.py` + `tools/slim_pdfs.py` | WebP 降维、PDF 外链化，`profiles/*.yaml` 配 `pdf_base`/`budget_mb` |
| build | `tools/build_vp.py` + `templates/` | 生成 `package.json/.vitepress`（mtf/ftm），复用上游配置（rle），改写 `base:'./'`（mio） |
| pack | `tools/pack.py` | `dist/`→ZIP，超 `budget_mb` 直接 fail |
| 分发 | `sync_vp_to_r2.yml` | R2 `vp-builder/releases/{tag}/` + `vp-builder/latest/`，**每个前缀只留最新+上一个两版** |

离线约定：构建期 `base: '/'` + `cleanUrls: false`，打包期由 `tools/pack.py`（`relativize_html_for_file_protocol`）做深度感知相对化（`./`, `../`, `../../`）与目录 URL 显式 `.html` 补全，完美双兼容本地 `file://` 双击直开与 Trans Prism App 内部 Shelf HTTP 服务器加载。

质量把关：每个项目打包后必须经 `tools/audit_links.py` 严格校验，确保 0 目录型未解析链接、0 本地引用 404，且产物体积在 `budget_mb` 门限以内。
