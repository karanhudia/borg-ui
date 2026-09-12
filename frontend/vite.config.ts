import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

const devBackendPort = process.env.DEV_PORT || '8083'
const proxyTarget = process.env.VITE_PROXY_TARGET || `http://localhost:${devBackendPort}`

// Hostnames allowed to reach the dev server, comma-separated. Vite rejects
// unknown Host headers to block DNS rebinding, which also rejects tunnel
// domains (Cloudflare, ngrok). Set VITE_ALLOWED_HOSTS to your tunnel host.
// Empty array is Vite's default: localhost only.
const allowedHosts = (process.env.VITE_ALLOWED_HOSTS || '')
  .split(',')
  .map((host) => host.trim())
  .filter(Boolean)

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 7879,
    allowedHosts,
    fs: {
      allow: [path.resolve(__dirname, '..')],
    },
    proxy: {
      '/api': {
        target: proxyTarget,
        changeOrigin: true,
        // Agents hold a session on /api/agents/session. Without ws the proxy
        // passes the plain HTTP calls but drops the upgrade, so an agent
        // enrolls and heartbeats yet never shows as online.
        ws: true,
      },
      // The agent installer and its binaries are served from the backend root,
      // not under /api, so without this the SPA fallback answers curl with
      // index.html and the piped `| sudo bash` chokes on `<!doctype html>`.
      '/agent': {
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
