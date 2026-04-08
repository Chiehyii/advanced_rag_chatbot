import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/chat': 'http://127.0.0.1:8000',
      '/feedback': 'http://127.0.0.1:8000',
      '/api': 'http://127.0.0.1:8000',
      '/metadata_schema.json': 'http://127.0.0.1:8000',
    }
  }
})
