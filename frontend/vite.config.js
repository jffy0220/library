import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,          // listen on 0.0.0.0 so LAN devices can reach it
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',  // FastAPI local-only
        changeOrigin: true,
        secure: false
      }
    }
  }
})
