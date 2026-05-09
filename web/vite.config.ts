import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig(async () => ({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  clearScreen: false,
  build: {
    // 不要 external @tauri-apps/api，需要打包进产物
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': 'http://localhost:18765',
      '/ws': {
        target: 'ws://localhost:18765',
        ws: true,
      },
    },
    watch: {
      ignored: ['**/src-tauri/**'],
    },
  },
}))
