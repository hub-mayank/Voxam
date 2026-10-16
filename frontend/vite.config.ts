/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// One address for the whole product: /api/* goes to the backend (with WebSockets), everything else is the app.
// `npm run preview` serves the production build this way, so a tunnel to port 5173 is enough for the finals (docs/FINALS_RUNBOOK.md).
const api = { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true, ws: true, rewrite: (path: string) => path.replace(/^\/api/, '') } }

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: api },
  preview: { port: 5173, proxy: api, allowedHosts: true },
  test: { environment: 'jsdom', include: ['src/**/*.test.{ts,tsx}'] },
})
