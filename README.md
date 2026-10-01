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
| Oyama HRT Tracker | `SmirnovaOyama/Oyama-s-HRT-Tracker` | Vite SPA | 自带 | `hrt_tracker_update-{date}.zip` |
| TransMTF HRT Tracker | `TransmtfTeam/Transmtf-HRT-Tracker` | React + Tailwind | 自带 | `transmtf_tracker_update-{date}.zip` |

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

---

## 🙏 鸣谢与上游致谢 (Acknowledgments)

本项目（New-Trans-Prism-Builder）基于并衍生自多个优秀的开源知识库与社区项目。在此向所有为跨性别群体健康知识普及、生活指导和数字化工具建设做出杰出贡献的上游社区和开发者团队致以最诚挚的敬意与感谢：

- **[Project Trans](https://github.com/project-trans)**：
  - [MtF.wiki](https://github.com/project-trans/MtF-wiki) — 跨性别女性医学与生活指南
  - [FtM.wiki](https://github.com/project-trans/FtM-wiki) — 跨性别男性医学与生活指南
  - [RLE.wiki](https://github.com/project-trans/RLE-wiki) — 真实生活体验指南
  - [@project-trans/vitepress-theme-project-trans](https://github.com/project-trans/vitepress-theme-project-trans) — 优雅的 VitePress 知识库主题
- **[KitsuMio / MioMtFWiki](https://github.com/KitsuMio/MioMtFWiki)**：
  - [MioMtFWiki](https://github.com/KitsuMio/MioMtFWiki) — 全面的 MtF HRT 与性别重置指南
- **[SmirnovaOyama / Oyama's HRT Tracker](https://github.com/SmirnovaOyama/Oyama-s-HRT-Tracker)**：
  - 极为实用的 HRT 用药记录与药代动力学（PK）模拟计算工具
- **[TransmtfTeam / Transmtf HRT Tracker](https://github.com/TransmtfTeam/Transmtf-HRT-Tracker)**：
  - 基于 React + Tailwind 的现代化跨性别 HRT 记录与健康管理平台

没有上述上游社区和贡献者们的无私奉献与持续产出，就没有 Trans Prism 专业、完整且温暖的内容基石！

---

## ⚖️ 开源许可 (License)

- **Builder 原创构建代码与流水线工具**：[Apache License 2.0](LICENSE.txt)
- **知识库主题 `@project-trans/vitepress-theme-project-trans`**：[MIT License](https://github.com/project-trans/vitepress-theme-project-trans/blob/main/LICENSE)（Copyright (c) 2024 Project Trans）
- **MtF / FtM / RLE Wiki 衍生内容**：遵循 [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) 许可协议
- **MioMtF Wiki 衍生内容**：遵循 [CC BY-ND 4.0](https://creativecommons.org/licenses/by-nd/4.0/) 许可协议
- **Oyama HRT Tracker 衍生工具**：遵循 [MIT License](https://opensource.org/licenses/MIT)
- **TransMTF HRT Tracker 衍生工具**：遵循 [MIT License](https://opensource.org/licenses/MIT)

知识库内容作为**独立于构建流水线的模块**随产物分发，不并入本仓库原创代码；
本项目已就内置知识库内容取得 Project Trans 与 MioMtFWiki 的授权。

完整条款见 [`LICENSE.txt`](LICENSE.txt)。
