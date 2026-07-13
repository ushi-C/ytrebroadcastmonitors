import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  build: {
    outDir: 'dist',
    rollupOptions: {
      output: {
        entryFileNames: '[name]-[hash:8].js',
        chunkFileNames: '[name]-[hash:8].js',
        assetFileNames: '[name]-[hash:8].[ext]',
      },
    },
  },
})
