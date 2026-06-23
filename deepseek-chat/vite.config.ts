import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Flask 后端端口（按实际需要调整）
const API_TARGET = 'http://127.0.0.1:5000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // 将所有 /api 请求代理到 Flask 后端
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
      },
      // 静态 EML 文件也代理（如果后端提供）
      '/ownthink_sample.eml': {
        target: API_TARGET,
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-react': ['react', 'react-dom'],
          'vendor-three': ['three'],
          'vendor-d3': ['d3'],
          'vendor-markdown': ['react-markdown', 'remark-gfm'],
          'vendor-highlight': ['highlight.js'],
        },
      },
    },
    chunkSizeWarningLimit: 600,
  },
})
