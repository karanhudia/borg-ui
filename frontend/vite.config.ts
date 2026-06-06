import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { readFileSync } from 'node:fs'

const devBackendPort = process.env.DEV_PORT || '8083'
const proxyTarget = process.env.VITE_PROXY_TARGET || `http://localhost:${devBackendPort}`
const packageJson = JSON.parse(
  readFileSync(path.resolve(__dirname, 'package.json'), 'utf-8')
) as { version?: string }

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(packageJson.version ?? '0.0.0'),
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 7879,
    fs: {
      allow: [path.resolve(__dirname, '..')],
    },
    proxy: {
      '/api': {
        target: proxyTarget,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'build',
    sourcemap: true,
  },
})
