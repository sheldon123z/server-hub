import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:9900',
      '/ws': { target: 'ws://localhost:9900', ws: true },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-echarts': ['echarts', 'echarts-for-react'],
          'vendor-mermaid': ['mermaid'],
          'vendor-xterm': ['@xterm/xterm', '@xterm/addon-fit'],
          'vendor-markdown': ['marked', 'highlight.js', 'dompurify'],
        },
      },
    },
  },
})
