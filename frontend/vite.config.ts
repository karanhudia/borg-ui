import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// Base path for deployment (e.g., "/borg" for example.com/borg/)
const BASE_PATH = process.env.VITE_BASE_PATH || '/'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  base: BASE_PATH,  // Configure base path for assets
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 7879,
    proxy: {
      [`${BASE_PATH === '/' ? '' : BASE_PATH}/api`]: {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'build',
    sourcemap: true,
  },
}) 