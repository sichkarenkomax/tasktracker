import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Development only. In production the frontend is built ahead of time and
// served as static files, while Caddy proxies /api to the backend
// (docs/architecture.md, sections 6 and 47).
const backend = process.env.BACKEND_URL ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: backend, changeOrigin: true },
      '/health': { target: backend, changeOrigin: true },
      '/openapi.json': { target: backend, changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
})