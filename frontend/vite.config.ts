import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

const devBackendPort = process.env.DEV_PORT || '8083'
const proxyTarget = process.env.VITE_PROXY_TARGET || `http://localhost:${devBackendPort}`

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 7879,
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
