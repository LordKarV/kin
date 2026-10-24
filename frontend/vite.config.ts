import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev proxy: the UI talks to FastAPI on :8000 for REST and WebSockets.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/connectors': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
})
