import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import basicSsl from '@vitejs/plugin-basic-ssl'

// One backend (:8000) + one Vite dev server (:5173) serve BOTH laptops. Laptop B opens https://<laptop-A-LAN-IP>:5173
// and accepts the self-signed certificate once: getUserMedia/AudioWorklet need a secure context off localhost.
export default defineConfig({
  plugins: [react(), basicSsl()],
  server: {
    host: true,
    port: 5173,
    allowedHosts: true,
    proxy: {
      '/api': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/connectors': 'http://localhost:8000',
      '/media': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
})
