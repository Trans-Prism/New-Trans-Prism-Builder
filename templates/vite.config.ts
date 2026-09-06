import { defineConfig } from 'vite'

// 主题依赖的 nolebase 插件 dist 里是裸 .vue，必须全部打进 SSR 包，
// 否则 Node 原生 import 会报 Unknown file extension ".vue"。
//（抄自 RLE-wiki/docs/vite.config.ts，去掉了 RLE 专属的 /api proxy）
export default defineConfig({
  ssr: { noExternal: true },
})
