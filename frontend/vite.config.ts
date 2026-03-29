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
        manualChunks(id: string) {
          if (id.includes('echarts')) return 'vendor-echarts'
          if (id.includes('mermaid')) return 'vendor-mermaid'
          if (id.includes('@xterm')) return 'vendor-xterm'
          if (id.includes('marked') || id.includes('highlight.js') || id.includes('dompurify'))
            return 'vendor-markdown'
        },
      },
    },
  },
})
