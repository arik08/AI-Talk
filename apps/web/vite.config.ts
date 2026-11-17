import { defineConfig } from 'vite';

// 개발 중에는 화면(5180)이 서버(8765)의 /api를 대신 불러 준다.
export default defineConfig({
  server: {
    host: '127.0.0.1',
    port: 5180,
    proxy: { '/api': { target: 'http://127.0.0.1:8765', changeOrigin: false } },
  },
  build: { outDir: 'dist', emptyOutDir: true },
});
