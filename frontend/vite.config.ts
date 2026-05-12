import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const BACKEND_PORT = parseInt(process.env.VITE_BACKEND_PORT || '8000', 10);

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true, // 端口被占用时直接报错，避免静默降级导致浏览器连接旧进程
    proxy: {
      '/api': {
        target: `http://localhost:${BACKEND_PORT}`,
        changeOrigin: true,
      },
    },
  },
});
