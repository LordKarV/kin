import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import basicSsl from '@vitejs/plugin-basic-ssl'

// Phones open https://<LAN-IP>:5174 and accept the self-signed certificate once: getUserMedia needs a secure context.
// /rtc reaches the local `livekit-server --dev` through this origin, so an HTTPS page can open its websocket.
export default defineConfig({
  plugins: [react(), basicSsl()],
  server: {
    host: true,
    port: 5174,
    allowedHosts: true,
    proxy: {
      '/api': 'http://localhost:8000',
      '/media': 'http://localhost:8000',
      '/rtc': { target: 'ws://localhost:7880', ws: true, changeOrigin: true },
    },
  },
})
