import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'
import UnoCSS from 'unocss/vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  // The desktop shell loads the bundle from disk (file://), where absolute
  // "/assets/..." URLs do not resolve. `vite build --mode desktop` switches to
  // relative URLs; the browser build keeps "/".
  base: mode === 'desktop' ? './' : '/',
  plugins: [
    vue(),
    vueDevTools(),
    UnoCSS(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
}))
