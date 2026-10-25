// Plain-HTTP variant for local viewing only (no mic off-localhost). Demo uses vite.config.ts (HTTPS on the LAN).
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
export default defineConfig({
  plugins: [react()],
  server: { port: 5174, proxy: { '/api': 'http://localhost:8000', '/health': 'http://localhost:8000', '/connectors': 'http://localhost:8000', '/media': 'http://localhost:8000', '/ws': { target: 'ws://localhost:8000', ws: true } } },
})
