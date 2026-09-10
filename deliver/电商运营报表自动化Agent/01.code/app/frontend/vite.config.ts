import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发期将 /api 代理到后端 uvicorn（默认 127.0.0.1:8000）
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
