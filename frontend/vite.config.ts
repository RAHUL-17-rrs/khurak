import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

const API = process.env.KHURAK_API ?? 'http://127.0.0.1:8765'
// Hosted (VITE_STATIC=1) builds serve /audio as static files; only the full app proxies it.
const PROXY = {
  '/api': { target: API, changeOrigin: true },
  ...(process.env.VITE_STATIC === '1' ? {} : { '/audio': { target: API, changeOrigin: true } }),
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: PROXY,
  },
  preview: { proxy: PROXY },
})
